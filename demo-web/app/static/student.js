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

const listen = { context: null, processor: null, stream: null, chunks: [], checking: false, homeworkId: null, scanner: null };
const flow = { step: "join", mode: "", attendanceId: "", band: "ultrasonic", proof: "both" };

function showStep(name) {
  ["join", "mode", "class", "lesson"].forEach((step) => {
    const node = document.querySelector("#step-" + step);
    if (node) node.hidden = step !== name;
  });
  flow.step = name;
}

function saveFlow() {
  sessionStorage.setItem("zoomoodle-student-flow", JSON.stringify({
    step: flow.step,
    mode: flow.mode,
    attendanceId: flow.attendanceId,
    band: flow.band,
    proof: flow.proof,
    room: roomInput.value.trim(),
  }));
}

function identity() {
  const studentId = document.querySelector("#sid").value.trim() || flow.attendanceId;
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

const ERROR_TEXT = {
  unknown_room: "That room is not on this server.",
  room_closed: "This room is closed. Ask the lecturer if a new one is open.",
  missing_identity: "Enter your student id first.",
  device_mismatch: "This device does not match the one that opened the challenge.",
  challenge_used: "That challenge was already used. Try again.",
  challenge_expired: "That challenge expired. Try again.",
  bad_mode: "The check-in mode was not accepted.",
  bad_zone: "Pick a seat zone first.",
  bad_signature: "The device signature was rejected.",
  missing_code: "Enter the on-screen code.",
  bad_token: "That code is not valid right now.",
  reused_token: "This device already used that code.",
  unknown_poll: "That poll is no longer available.",
  bad_option: "Pick one of the poll options.",
  already_answered: "You already answered this poll.",
  missing_comment: "Enter your student id and a comment first.",
  missing_homework: "Enter your student id and paste an answer first.",
  unknown_submission: "That homework submission was not found.",
  expected_json: "The server could not read that request.",
};

function explain(error, fallback) {
  if (!error) return fallback;
  const text = String(error);
  if (Object.prototype.hasOwnProperty.call(ERROR_TEXT, text)) return ERROR_TEXT[text];
  if (text.indexOf(" ") !== -1) return text;
  return fallback;
}

function setResult(message, ok) {
  const node = document.querySelector("#check-result");
  node.textContent = message;
  node.className = ok ? "ok" : "bad";
}

function setCommentResult(message, ok) {
  const node = document.querySelector("#comment-result");
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
    setResult(explain(opened.error, "Could not open a challenge."), false);
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
    setResult(explain(body.error, "Check-in was rejected."), false);
    return;
  }
  const extra = body.external_token ? " Remote token: " + body.external_token : "";
  const flags = body.flags && body.flags.length ? " Flags: " + body.flags.join(", ") : "";
  const issued = body.attendance_id ? " Server id " + body.attendance_id + "." : "";
  setResult("Checked in (" + body.mode + "), confidence " + body.confidence + "." + flags + extra + issued, true);
  if (body.attendance_id) enterLesson("in_class", body.attendance_id);
}

document.querySelector("#typed").addEventListener("click", () => {
  checkIn("in_class", document.querySelector("#code").value.trim()).catch((err) => setResult(err.message, false));
});

document.querySelector("#join-continue").addEventListener("click", async () => {
  const room = roomInput.value.trim();
  const note = document.querySelector("#join-status");
  if (!room) {
    note.textContent = "Enter the room code.";
    return;
  }
  const response = await fetch("/api/rooms/" + encodeURIComponent(room));
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    note.textContent = explain(body.error, "That room was not found.");
    return;
  }
  flow.band = body.audio_band || "ultrasonic";
  flow.proof = body.proof || "both";
  sessionStorage.setItem("zoomoodle-room", room);
  document.querySelector("#mode-room").textContent = "Room " + body.id + (body.title ? " · " + body.title : "");
  showStep("mode");
  saveFlow();
});

document.querySelector("#choose-class").addEventListener("click", () => {
  showStep("class");
  saveFlow();
});

document.querySelector("#remote").addEventListener("click", async () => {
  const room = roomInput.value.trim();
  const response = await fetch("/api/rooms/" + encodeURIComponent(room) + "/remote-join", { method: "POST" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    document.querySelector("#join-status").textContent = explain(body.error, "Could not join remotely.");
    return;
  }
  enterLesson("remote", body.marker);
});

document.querySelector("#listen").addEventListener("click", async () => {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    listen.context = listen.context || new Ctx();
    if (listen.context.state === "suspended") await listen.context.resume();
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
      const band = ZooFSK.bandOf(flow.band);
      const power = ZooFSK.goertzel(latest, 0, latest.length, (band.f0 + band.f1) / 2, rate);
      const width = Math.max(0, Math.min(100, Math.log10(power + 1) * 8));
      document.querySelector("#level").style.width = width + "%";
      document.querySelector("#level-text").textContent = "Listening… " + rate + " Hz, " + band.label;
      if (listen.checking) return;
      const merged = new Float32Array(total);
      let offset = 0;
      listen.chunks.forEach((chunk) => {
        merged.set(chunk, offset);
        offset += chunk.length;
      });
      const report = ZooFSK.inspect(merged, rate, flow.band);
      document.querySelector("#tone-diagnostics").textContent =
        "Listening… " + Math.round(band.f0) + " Hz " + Math.round(report.power0) +
        " · " + Math.round(band.f1) + " Hz " + Math.round(report.power1) +
        " · preamble " + (report.preamble < 0 ? 0 : report.preamble) +
        (report.bits ? " · bits " + report.bits.slice(0, 24) : "");
      const decoded = report.bytes;
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
      const message = response.ok ? "Answer recorded." : explain(payload.error, "Could not record the answer.");
      box.insertAdjacentHTML("beforeend", "<p class=\"" + (response.ok ? "note" : "bad") + "\">" + escapeHtml(message) + "</p>");
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
  setCommentResult(response.ok ? "Comment sent." : explain(body.error, "Could not send the comment."), response.ok);
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
    document.querySelector("#review").textContent = explain(body.error, "Submit failed.");
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
  out.textContent = response.ok ? JSON.stringify(body, null, 2) : explain(body.error, "Review failed.");
});

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
  }[ch]));
}

function enterLesson(mode, attendanceId) {
  flow.mode = mode;
  flow.attendanceId = attendanceId || "";
  document.querySelector("#attendance-id").textContent = flow.attendanceId || "—";
  document.querySelector("#lesson-status").textContent = mode === "remote"
    ? "You are remote. This marker means you are not checked in as being in class."
    : "You are in class. The attendance id below came from the server.";
  const zonesNode = document.querySelector("#zones");
  const holder = document.querySelector("#lesson-zones");
  if (zonesNode && holder && zonesNode.parentElement !== holder) holder.appendChild(zonesNode);
  showStep("lesson");
  saveFlow();
}

document.querySelector("#scan").addEventListener("click", async () => {
  if (!("BarcodeDetector" in window)) {
    setResult("This browser cannot scan a QR code. Type the short code instead.", false);
    return;
  }
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    listen.context = listen.context || new Ctx();
    if (listen.context.state === "suspended") await listen.context.resume();
    listen.scanner = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
    const video = document.querySelector("#scanner");
    video.srcObject = listen.scanner;
    video.hidden = false;
    const detector = new BarcodeDetector({ formats: ["qr_code"] });
    const timer = window.setInterval(async () => {
      const codes = await detector.detect(video);
      if (!codes.length) return;
      window.clearInterval(timer);
      const raw = codes[0].rawValue || "";
      const found = raw.match(/[A-Z2-7]{8,}/);
      document.querySelector("#code").value = found ? found[0] : raw.trim();
      listen.scanner.getTracks().forEach((track) => track.stop());
      video.hidden = true;
      checkIn("in_class", document.querySelector("#code").value.trim()).catch((err) => setResult(err.message, false));
    }, 400);
  } catch (err) {
    setResult(err.message, false);
  }
});

(function restoreFlow() {
  if (params.get("code")) document.querySelector("#code").value = params.get("code");
  let saved = null;
  try { saved = JSON.parse(sessionStorage.getItem("zoomoodle-student-flow") || "null"); } catch (_err) { saved = null; }
  const urlRoom = params.get("room") || "";
  if (!saved || (urlRoom && saved.room && saved.room !== urlRoom)) return;
  if (saved.room) roomInput.value = saved.room;
  flow.band = saved.band || flow.band;
  flow.proof = saved.proof || flow.proof;
  if (saved.step === "lesson" && saved.attendanceId) enterLesson(saved.mode || "in_class", saved.attendanceId);
  else if (saved.step === "class" || saved.step === "mode") showStep(saved.step);
}());

loadPoll();
setInterval(() => loadPoll().catch(() => {}), 4000);
