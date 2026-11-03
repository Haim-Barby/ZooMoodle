const zones = ["front-left", "front-right", "middle-left", "middle-right", "back-left", "back-right"];
const zoneBox = document.querySelector("#zones");
let seat = sessionStorage.getItem("zoomoodle-seat") || "";
zones.forEach((zone) => {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = zone.replace("-", " ");
  button.dataset.zone = zone;
  if (zone === seat) button.classList.add("selected");
  button.addEventListener("click", () => {
    seat = zone;
    sessionStorage.setItem("zoomoodle-seat", seat);
    zoneBox.querySelectorAll("button").forEach((item) => item.classList.toggle("selected", item.dataset.zone === seat));
  });
  zoneBox.appendChild(button);
});

const params = new URLSearchParams(window.location.search);
const roomInput = document.querySelector("#room");
roomInput.value = params.get("room") || sessionStorage.getItem("zoomoodle-room") || "";
document.querySelector("#name").value = sessionStorage.getItem("zoomoodle-name") || "";
document.querySelector("#sid").value = sessionStorage.getItem("zoomoodle-sid") || "";

const listen = { context: null, processor: null, stream: null, chunks: [], checking: false, homeworkId: null };

function identity() {
  const studentId = document.querySelector("#sid").value.trim();
  const studentName = document.querySelector("#name").value.trim();
  const room = roomInput.value.trim();
  sessionStorage.setItem("zoomoodle-sid", studentId);
  sessionStorage.setItem("zoomoodle-name", studentName);
  sessionStorage.setItem("zoomoodle-room", room);
  return { studentId, studentName, room };
}

async function device() {
  const stored = localStorage.getItem("zoomoodle-device");
  if (stored) return JSON.parse(stored);
  const pair = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
  const pub = await crypto.subtle.exportKey("jwk", pair.publicKey);
  const priv = await crypto.subtle.exportKey("jwk", pair.privateKey);
  const record = { pub: pub, priv: priv };
  localStorage.setItem("zoomoodle-device", JSON.stringify(record));
  return record;
}

async function deviceId(jwk) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(jwk.x + "." + jwk.y));
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 16);
}

async function sign(record, challengeId, nonce) {
  const key = await crypto.subtle.importKey(
    "jwk",
    record.priv,
    { name: "ECDSA", namedCurve: "P-256" },
    false,
    ["sign"]
  );
  const payload = new TextEncoder().encode(challengeId + "|" + nonce);
  const signature = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, payload);
  const bytes = new Uint8Array(signature);
  let text = "";
  bytes.forEach((b) => { text += String.fromCharCode(b); });
  return btoa(text);
}

function setResult(message, ok) {
  const node = document.querySelector("#check-result");
  node.textContent = message;
  node.className = ok ? "ok" : "bad";
}

async function checkIn(mode, tokenCode) {
  const who = identity();
  if (!who.room || !who.studentId) {
    setResult("Enter the room and your student id first.", false);
    return;
  }
  if (!seat) {
    setResult("Pick a seat zone first.", false);
    return;
  }
  const keys = await device();
  const id = await deviceId(keys.pub);
  const challenge = await fetch("/api/rooms/" + encodeURIComponent(who.room) + "/challenge", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      student_id: who.studentId,
      student_name: who.studentName,
      device_id: id,
      public_jwk: { kty: keys.pub.kty, crv: keys.pub.crv, x: keys.pub.x, y: keys.pub.y },
    }),
  });
  const opened = await challenge.json();
  if (!challenge.ok) {
    setResult(opened.error || "Could not open a challenge.", false);
    return;
  }
  const signature = await sign(keys, opened.challenge_id, opened.nonce);
  const response = await fetch("/api/rooms/" + encodeURIComponent(who.room) + "/checkin", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      challenge_id: opened.challenge_id,
      signature: signature,
      mode: mode,
      token_code: tokenCode || null,
      seat_zone: seat,
      student_name: who.studentName,
    }),
  });
  const body = await response.json();
  if (!response.ok) {
    setResult(body.error || "Check-in was rejected.", false);
    return;
  }
  const extra = body.external_token ? " Remote token: " + body.external_token : "";
  const flags = body.flags && body.flags.length ? " Flags: " + body.flags.join(", ") : "";
  setResult("Checked in (" + body.mode + "), confidence " + body.confidence + "." + flags + extra, true);
}

document.querySelector("#typed").addEventListener("click", () => {
  checkIn("in_class", document.querySelector("#code").value.trim()).catch((err) => setResult(err.message, false));
});

document.querySelector("#remote").addEventListener("click", () => {
  checkIn("remote", null).catch((err) => setResult(err.message, false));
});

document.querySelector("#listen").addEventListener("click", async () => {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    listen.context = listen.context || new Ctx();
    listen.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
    });
    const source = listen.context.createMediaStreamSource(listen.stream);
    const processor = listen.context.createScriptProcessor(4096, 1, 1);
    listen.chunks = [];
    listen.checking = false;
    processor.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0);
      listen.chunks.push(new Float32Array(input));
      const rate = listen.context.sampleRate;
      const keep = rate * 3;
      let total = listen.chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      while (total > keep && listen.chunks.length > 1) {
        total -= listen.chunks.shift().length;
      }
      const latest = input;
      const power = ZooFSK.goertzel(latest, 0, latest.length, 18500, rate);
      const width = Math.max(0, Math.min(100, Math.log10(power + 1) * 8));
      document.querySelector("#level").style.width = width + "%";
      document.querySelector("#level-text").textContent = "Listening at " + rate + " Hz. Ultrasound energy indicator: " + Math.round(width);
      if (listen.checking) return;
      const merged = new Float32Array(total);
      let offset = 0;
      listen.chunks.forEach((chunk) => {
        merged.set(chunk, offset);
        offset += chunk.length;
      });
      const decoded = ZooFSK.decode(merged, rate);
      if (decoded) {
        listen.checking = true;
        const code = ZooFSK.base32(decoded);
        document.querySelector("#code").value = code;
        checkIn("in_class", code).finally(() => { listen.checking = false; });
      }
    };
    source.connect(processor);
    processor.connect(listen.context.destination);
    listen.processor = processor;
    listen.source = source;
  } catch (err) {
    setResult(err.message, false);
  }
});

document.querySelector("#stop").addEventListener("click", () => {
  if (listen.processor) listen.processor.disconnect();
  if (listen.source) listen.source.disconnect();
  if (listen.stream) listen.stream.getTracks().forEach((track) => track.stop());
  document.querySelector("#level-text").textContent = "Microphone is off.";
});

async function loadPoll() {
  const room = roomInput.value.trim();
  if (!room) return;
  const response = await fetch("/api/rooms/" + encodeURIComponent(room) + "/polls");
  if (!response.ok) return;
  const body = await response.json();
  const polls = body.polls || [];
  if (!polls.length) {
    document.querySelector("#poll").textContent = "No poll yet.";
    return;
  }
  const poll = polls[polls.length - 1];
  const box = document.querySelector("#poll");
  box.innerHTML = "<p><strong>" + escapeHtml(poll.question) + "</strong></p>";
  poll.options.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = option;
    button.addEventListener("click", async () => {
      const who = identity();
      const response = await fetch("/api/rooms/" + encodeURIComponent(who.room) + "/polls/" + poll.id + "/answers", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ student_id: who.studentId, option: option, seat_zone: seat }),
      });
      const payload = await response.json();
      box.insertAdjacentHTML("beforeend", "<p class=\"note\">" + escapeHtml(payload.error || "Answer recorded.") + "</p>");
    });
    box.appendChild(button);
  });
}

document.querySelector("#send-comment").addEventListener("click", async () => {
  const who = identity();
  const response = await fetch("/api/rooms/" + encodeURIComponent(who.room) + "/comments", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      student_id: who.studentId,
      student_name: who.studentName,
      text: document.querySelector("#comment").value,
    }),
  });
  const body = await response.json();
  setResult(body.error || "Comment sent.", response.ok);
});

document.querySelector("#send-homework").addEventListener("click", async () => {
  const who = identity();
  const response = await fetch("/api/rooms/" + encodeURIComponent(who.room) + "/homework", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      student_id: who.studentId,
      student_name: who.studentName,
      text: document.querySelector("#homework").value,
    }),
  });
  const body = await response.json();
  if (!response.ok) {
    document.querySelector("#review").textContent = body.error || "Submit failed.";
    return;
  }
  listen.homeworkId = body.id;
  document.querySelector("#review").textContent = "Submitted as " + body.id + ".";
});

document.querySelector("#review-homework").addEventListener("click", async () => {
  const who = identity();
  const out = document.querySelector("#review");
  if (!listen.homeworkId) {
    out.textContent = "Submit the homework first.";
    return;
  }
  out.textContent = "Asking the agent…";
  const response = await fetch("/api/rooms/" + encodeURIComponent(who.room) + "/agent/homework", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ submission_id: listen.homeworkId, audience: "student" }),
  });
  const body = await response.json();
  out.textContent = response.ok ? JSON.stringify(body, null, 2) : (body.error || "Review failed.");
});

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
  }[ch]));
}

loadPoll();
setInterval(() => loadPoll().catch(() => {}), 4000);
