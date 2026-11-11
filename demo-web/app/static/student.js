const zones = [
  "front-left", "front-center", "front-right",
  "middle-left", "middle-center", "middle-right",
  "back-left", "back-center", "back-right",
];
const zoneBox = document.querySelector("#zones");
let seat = sessionStorage.getItem("zoomoodle-seat") || "";
zones.forEach((zone) => {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = zone.replace("-", " ");
  button.dataset.zone = zone;
  button.setAttribute("aria-pressed", zone === seat ? "true" : "false");
  if (zone === seat) button.classList.add("selected");
  button.addEventListener("click", () => {
    seat = zone;
    sessionStorage.setItem("zoomoodle-seat", seat);
    zoneBox.querySelectorAll("button").forEach((item) => {
      const on = item.dataset.zone === seat;
      item.classList.toggle("selected", on);
      item.setAttribute("aria-pressed", on ? "true" : "false");
    });
  });
  zoneBox.appendChild(button);
});

const params = new URLSearchParams(window.location.search);
const roomInput = document.querySelector("#room");
roomInput.value = params.get("room") || sessionStorage.getItem("zoomoodle-room") || "";
document.querySelector("#name").value = sessionStorage.getItem("zoomoodle-name") || "";
document.querySelector("#sid").value = sessionStorage.getItem("zoomoodle-sid") || "";

const listen = { context: null, processor: null, stream: null, chunks: [], checking: false, scanner: null };
const flow = { step: "join", mode: "", attendanceId: "", band: "ultrasonic", proof: "both", title: "" };

function showStep(name) {
  ["join", "mode", "identity", "class", "lesson"].forEach((step) => {
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
    title: flow.title || "",
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
  missing_identity: "This browser could not create a device key. Reload the page and try again.",
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
  missing_question: "Enter a question first.",
  already_upvoted: "You already upvoted that question.",
  bad_session: "The session signature was rejected.",
  session_expired: "That request was too old. Check the phone clock and try again.",
  session_replay: "That request was already used. Try again.",
  session_revoked: "This lesson is closed. Your session key no longer works.",
  session_required: "Check in again. This action needs your session key.",
  session_mismatch: "That action does not match this phone's session.",
  identity_rejected: "השם או כתובת המייל לא התקבלו.",
  identity_limited: "יותר מדי ניסיונות. נסו שוב מאוחר יותר.",
  presence_required: "עדיין אין הוכחה שהטלפון הגיע למאמת של המרצה.",
  presence_expired: "בדיקת הרשת פגה. נסו שוב.",
  presence_replay: "בדיקת הרשת כבר שומשה.",
  presence_unavailable: "המאמת המקומי לא פועל.",
  presence_closed: "השיעור נסגר. אי אפשר לסמן נוכחות.",
  presence_mismatch: "הבדיקה לא שייכת לטלפון הזה.",
  qr_required: "עדיין צריך לסרוק את הברקוד החי על המסך.",
  qr_stale: "הברקוד כבר ישן מדי. כוונו שוב למסך החי למשך שתי שניות.",
  qr_replay: "הברקוד הזה כבר שומש. סרקו את המסך החי מחדש.",
  qr_mismatch: "הברקוד לא שייך לחדר הזה או אינו תקין.",
  qr_sequence: "הרצף שנסרק לא תואם את התנועה על המסך. סרקו שוב שתי שניות.",
  qr_static: "התמונה לא זזה. צריך לכוון את המצלמה לברקוד החי על המסך, לא לצילום.",
  qr_short: "צריך להחזיק את המצלמה על הברקוד החי במשך שתי שניות.",
  bad_helper: "המאמת המקומי לא מזוהה.",
  unknown_question: "That question is no longer available.",
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

function setQuestionResult(message, ok) {
  const node = document.querySelector("#question-result");
  node.textContent = message;
  node.className = ok ? "ok" : "bad";
}

function lessonIdentity() {
  return {
    studentId: flow.attendanceId || "",
    room: roomInput.value.trim(),
  };
}

let studentSession = null;

function rememberSession(room, sessionId, sessionKey, studentId) {
  studentSession = { room: room, sessionId: sessionId, sessionKey: sessionKey, studentId: studentId };
  const encoded = JSON.stringify(studentSession);
  sessionStorage.setItem("zoomoodle-session", encoded);
  if (room) localStorage.setItem("zoomoodle-session-" + room, encoded);
}

function loadStudentSession() {
  const room = roomInput.value.trim();
  let raw = sessionStorage.getItem("zoomoodle-session");
  if (!raw && room) raw = localStorage.getItem("zoomoodle-session-" + room);
  if (!raw) return null;
  try { studentSession = JSON.parse(raw); } catch (_err) { studentSession = null; }
  if (!studentSession || (room && studentSession.room && studentSession.room !== room)) {
    studentSession = null;
    return null;
  }
  sessionStorage.setItem("zoomoodle-session", JSON.stringify(studentSession));
  return studentSession;
}

function bytesToB64url(bytes) {
  let text = "";
  bytes.forEach((b) => { text += String.fromCharCode(b); });
  return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function b64urlToBytes(text) {
  const pad = "=".repeat((4 - (text.length % 4)) % 4);
  const raw = atob(text.replace(/-/g, "+").replace(/_/g, "/") + pad);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

async function sessionMacKey(secretB64) {
  const base = await crypto.subtle.importKey("raw", b64urlToBytes(secretB64), "HKDF", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({
    name: "HKDF",
    hash: "SHA-256",
    salt: new TextEncoder().encode("zoomoodle-session-v1"),
    info: new TextEncoder().encode("zoomoodle-session-mac"),
  }, base, 256);
  return crypto.subtle.importKey("raw", bits, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
}

function noteSession(error) {
  const alert = document.querySelector("#lesson-alert");
  if (!alert || !error) return;
  if (error === "session_revoked" || error === "session_required" || error === "bad_session" || error === "session_expired") {
    alert.textContent = explain(error);
    alert.className = "bad";
  }
}

async function signedFetch(path, options) {
  const session = studentSession || loadStudentSession();
  if (!session || !session.sessionKey) {
    return new Response(JSON.stringify({ error: "session_required" }), {
      status: 401,
      headers: { "content-type": "application/json" },
    });
  }
  const method = ((options && options.method) || "GET").toUpperCase();
  const body = options && options.body ? options.body : "";
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonceBytes = new Uint8Array(16);
  crypto.getRandomValues(nonceBytes);
  const nonce = Array.from(nonceBytes).map((b) => b.toString(16).padStart(2, "0")).join("");
  const key = await sessionMacKey(session.sessionKey);
  const message = new TextEncoder().encode([method, path, body, timestamp, nonce].join("\n"));
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, message));
  const headers = {
    "x-zoomoodle-session": session.sessionId,
    "x-zoomoodle-timestamp": timestamp,
    "x-zoomoodle-nonce": nonce,
    "x-zoomoodle-signature": bytesToB64url(mac),
  };
  if (body) headers["content-type"] = "application/json";
  return fetch(path, { method: method, body: body || undefined, headers: headers });
}

async function checkIn(mode, tokenCode) {
  const who = identity();
  if (!who.room) {
    setResult("Enter the room code first.", false);
    return;
  }
  if (!seat) {
    setResult("Pick a seat zone first.", false);
    return;
  }
  setResult("Checking in…", true);
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
  const opened = await challenge.json().catch(() => ({}));
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
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    setResult(explain(body.error, "Check-in was rejected (HTTP " + response.status + ")."), false);
    return;
  }
  const extra = body.external_token ? " Remote token: " + body.external_token : "";
  const flags = body.flags && body.flags.length ? " Flags: " + body.flags.join(", ") : "";
  const issued = body.attendance_id ? " Server id " + body.attendance_id + "." : "";
  setResult("Checked in (" + body.mode + "), confidence " + body.confidence + "." + flags + extra + issued, true);
  if (body.attendance_id) {
    stopListening();
    if (!document.querySelector("#sid").value.trim() && body.student_id) {
      sessionStorage.setItem("zoomoodle-sid", body.student_id);
    }
    if (body.session_key && body.session_id) {
      rememberSession(who.room, body.session_id, body.session_key, body.attendance_id || body.student_id);
    }
    enterLesson("in_class", body.attendance_id);
  } else {
    setResult("The server did not return an attendance id. Try again.", false);
  }
}

document.querySelector("#typed").addEventListener("click", () => {
  if (!document.querySelector("#code").value.trim()) {
    setResult("Enter the on-screen code first.", false);
    return;
  }
  checkIn("in_class", document.querySelector("#code").value.trim()).catch((err) => setResult(err.message, false));
});

document.querySelector("#join-continue").addEventListener("click", async () => {
  const room = roomInput.value.trim();
  const note = document.querySelector("#join-status");
  if (!room) {
    note.textContent = "Enter the room code.";
    return;
  }
  note.textContent = "Looking up the room…";
  let response;
  try {
    response = await fetch("/api/rooms/" + encodeURIComponent(room));
  } catch (_err) {
    note.textContent = "Could not reach the server. Check the connection and try again.";
    return;
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    note.textContent = explain(body.error, "That room was not found.");
    return;
  }
  if (body.closed) {
    note.textContent = ERROR_TEXT.room_closed;
    return;
  }
  note.textContent = "";
  flow.band = body.audio_band || "ultrasonic";
  flow.proof = body.proof || "both";
  flow.title = body.title || flow.title || "";
  sessionStorage.setItem("zoomoodle-room", room);
  document.querySelector("#mode-room").textContent = "Room " + body.id + (body.title ? " · " + body.title : "");
  showStep("mode");
  saveFlow();
});

document.querySelector("#choose-class").addEventListener("click", () => {
  showStep("identity");
  saveFlow();
  loadRosterNames().catch((err) => {
    document.querySelector("#identity-status").textContent = err.message;
  });
});

document.querySelector("#sound-instead").addEventListener("click", () => {
  showStep("class");
  saveFlow();
});

document.querySelector("#remote").addEventListener("click", async () => {
  const room = roomInput.value.trim();
  const note = document.querySelector("#mode-status");
  note.textContent = "Joining…";
  let response;
  try {
    response = await fetch("/api/rooms/" + encodeURIComponent(room) + "/remote-join", { method: "POST" });
  } catch (_err) {
    note.textContent = "Could not reach the server. Check the connection and try again.";
    return;
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok || !body.marker) {
    note.textContent = explain(body.error, "Could not join remotely (HTTP " + response.status + ").");
    return;
  }
  note.textContent = "";
  if (body.session_key && body.session_id) {
    rememberSession(room, body.session_id, body.session_key, body.marker);
  }
  document.querySelector("#welcome").hidden = true;
  document.querySelector("#remote-banner").hidden = false;
  enterLesson("remote", body.marker);
});

document.querySelector("#listen").addEventListener("click", async () => {
  if (!seat) {
    setResult("Pick a seat zone first.", false);
    return;
  }
  if (listen.processor) stopListening();
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
      if (flow.step === "lesson") return;
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
      if (decoded && flow.step !== "lesson") {
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
    setResult("Listening for the lecturer's tone…", true);
  } catch (err) {
    const denied = err && (err.name === "NotAllowedError" || err.name === "SecurityError");
    setResult(denied
      ? "Microphone permission was refused. Allow it in the browser, or type the on-screen code."
      : "Could not start the microphone: " + (err && err.message ? err.message : err), false);
  }
});

function stopListening() {
  if (listen.processor) {
    listen.processor.onaudioprocess = null;
    listen.processor.disconnect();
  }
  if (listen.source) listen.source.disconnect();
  if (listen.stream) listen.stream.getTracks().forEach((track) => track.stop());
  if (listen.scanner) listen.scanner.getTracks().forEach((track) => track.stop());
  listen.processor = null;
  listen.source = null;
  listen.stream = null;
  listen.scanner = null;
  listen.chunks = [];
  document.querySelector("#level-text").textContent = "Microphone is off.";
}

document.querySelector("#stop").addEventListener("click", stopListening);

function renderPoll(poll) {
  const box = document.querySelector("#poll");
  box.className = "";
  box.innerHTML = "<p><strong>" + escapeHtml(poll.question) + "</strong></p>";
  if (poll.voted_option) {
    const counts = poll.counts || {};
    poll.options.forEach((option) => {
      const row = document.createElement("p");
      row.className = "note";
      const count = Object.prototype.hasOwnProperty.call(counts, option) ? counts[option] : 0;
      row.textContent = option + " · " + count + (option === poll.voted_option ? " · your vote" : "");
      box.appendChild(row);
    });
    return;
  }
  const who = lessonIdentity();
  poll.options.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = option;
    button.addEventListener("click", async () => {
      const zone = flow.mode === "remote" ? "remote" : seat;
      const response = await signedFetch("/api/rooms/" + encodeURIComponent(who.room) + "/polls/" + poll.id + "/answers", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ student_id: who.studentId, option: option, seat_zone: zone }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        noteSession(payload.error);
        box.insertAdjacentHTML("beforeend", "<p class=\"bad\">" + escapeHtml(explain(payload.error, "Could not record the answer.")) + "</p>");
        return;
      }
      pollStamp = "";
      renderPoll({
        question: poll.question,
        options: poll.options,
        voted_option: payload.voted_option || option,
        counts: payload.counts || {},
      });
      loadPoll().catch(() => {});
    });
    box.appendChild(button);
  });
}

let pollStamp = "";
let pollGeneration = 0;

async function loadPoll() {
  const generation = ++pollGeneration;
  const who = lessonIdentity();
  if (!who.room) return;
  const query = who.studentId ? "?student_id=" + encodeURIComponent(who.studentId) : "";
  const response = await signedFetch("/api/rooms/" + encodeURIComponent(who.room) + "/polls" + query);
  if (generation !== pollGeneration || !response.ok) return;
  const body = await response.json();
  if (generation !== pollGeneration) return;
  const polls = body.polls || [];
  const box = document.querySelector("#poll");
  if (!polls.length) {
    if (pollStamp === who.room + ":empty") return;
    pollStamp = who.room + ":empty";
    box.className = "note";
    box.textContent = "No polls yet";
    return;
  }
  const poll = polls[polls.length - 1];
  const stamp = who.room + ":" + JSON.stringify(poll);
  if (stamp === pollStamp) return;
  pollStamp = stamp;
  renderPoll(poll);
}

let questionStamp = "";
let questionGeneration = 0;

async function loadQuestions() {
  const generation = ++questionGeneration;
  const who = lessonIdentity();
  if (!who.room) return;
  const query = who.studentId ? "?student_id=" + encodeURIComponent(who.studentId) : "";
  const response = await signedFetch("/api/rooms/" + encodeURIComponent(who.room) + "/questions" + query);
  if (generation !== questionGeneration || !response.ok) return;
  const body = await response.json();
  if (generation !== questionGeneration) return;
  const box = document.querySelector("#questions");
  const questions = body.questions || [];
  const stamp = who.room + ":" + JSON.stringify(questions);
  if (stamp === questionStamp) return;
  questionStamp = stamp;
  if (!questions.length) {
    box.className = "note";
    box.textContent = "No questions yet.";
    return;
  }
  box.className = "question-list";
  box.innerHTML = "";
  questions.forEach((question) => {
    const item = document.createElement("article");
    item.className = "question-item";
    const text = document.createElement("p");
    text.textContent = question.text;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.textContent = (question.upvoted ? "Upvoted" : "Upvote") + " · " + question.votes;
    button.disabled = !!question.upvoted;
    button.addEventListener("click", async () => {
      button.disabled = true;
      const vote = await signedFetch(
        "/api/rooms/" + encodeURIComponent(who.room) + "/questions/" + encodeURIComponent(question.id) + "/upvote",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ student_id: who.studentId }),
        }
      );
      const payload = await vote.json().catch(() => ({}));
      if (!vote.ok) {
        button.disabled = false;
        noteSession(payload.error);
        setQuestionResult(explain(payload.error, "Could not upvote that question."), false);
        return;
      }
      setQuestionResult("", true);
      loadQuestions().catch(() => {});
    });
    item.appendChild(text);
    item.appendChild(button);
    box.appendChild(item);
  });
}

document.querySelector("#send-question").addEventListener("click", async () => {
  const who = lessonIdentity();
  const text = document.querySelector("#question").value.trim();
  if (!who.room || !who.studentId) {
    setQuestionResult("Reload the lesson. The server id is missing.", false);
    return;
  }
  if (!text) {
    setQuestionResult(explain("missing_question"), false);
    return;
  }
  setQuestionResult("Sending…", true);
  let response;
  try {
    response = await signedFetch("/api/rooms/" + encodeURIComponent(who.room) + "/questions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ student_id: who.studentId, text: text }),
    });
  } catch (_err) {
    setQuestionResult("Could not reach the server. Check the connection and try again.", false);
    return;
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    noteSession(body.error);
    setQuestionResult(explain(body.error, "Could not send the question."), false);
    return;
  }
  document.querySelector("#question").value = "";
  setQuestionResult("Question sent.", true);
  loadQuestions().catch(() => {});
});

let lessonRefresh = false;

async function refreshLesson() {
  if (flow.step !== "lesson" || lessonRefresh) return;
  lessonRefresh = true;
  try {
  await refreshLessonBody();
  } finally {
    lessonRefresh = false;
  }
}

async function refreshLessonBody() {
  const who = lessonIdentity();
  if (!who.room) return;
  const counts = await signedFetch("/api/rooms/" + encodeURIComponent(who.room) + "/counts");
  if (!counts.ok) {
    const denied = await counts.json().catch(() => ({}));
    noteSession(denied.error);
    return;
  }
  if (counts.ok) {
    const body = await counts.json();
    if (body.title && body.title !== flow.title) {
      flow.title = body.title;
      document.querySelector("#lesson-title").textContent = body.title;
      saveFlow();
    }
    document.querySelector("#count-in-class").textContent = String(body.in_class);
    document.querySelector("#count-remote").textContent = String(body.remote);
    const summary = await signedFetch("/api/rooms/" + encodeURIComponent(who.room) + "/summary");
    const summaryBody = summary.ok ? await summary.json().catch(() => ({})) : {};
    const card = document.querySelector("#summary-card");
    const closed = !!(body.closed || summaryBody.closed);
    card.hidden = !closed;
    if (closed) {
      const node = document.querySelector("#lesson-summary");
      node.textContent = summaryBody.text ? summaryBody.text : "Summary not published yet";
    }
  }
  await loadPoll();
  await loadQuestions();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
  }[ch]));
}

function enterLesson(mode, attendanceId, title) {
  flow.mode = mode;
  flow.attendanceId = attendanceId || "";
  if (title) flow.title = title;
  document.querySelector("#lesson-title").textContent = flow.title || "Lesson";
  document.querySelector("#lesson-mode").textContent = mode === "remote" ? "Remote" : "In class";
  document.querySelector("#attendance-id").textContent = flow.attendanceId || "—";
  const welcome = document.querySelector("#welcome");
  if (welcome && mode !== "remote" && sessionStorage.getItem("zoomoodle-present") === "1") {
    const name = sessionStorage.getItem("zoomoodle-display") || "";
    welcome.hidden = false;
    welcome.textContent = "ברוך הבא, " + name;
  }
  showStep("lesson");
  saveFlow();
  refreshLesson().catch(() => {});
  loadSources().catch(() => {});
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


const screenQr = { stream: null, timer: null, codes: [], lastRaw: "", needed: 5, required: true, holdSeconds: 2, firstAt: 0, submitting: false };

function stopScreenQrScan() {
  if (screenQr.timer) window.clearTimeout(screenQr.timer);
  screenQr.timer = null;
  if (screenQr.stream) screenQr.stream.getTracks().forEach((track) => track.stop());
  screenQr.stream = null;
  const video = document.querySelector("#screen-qr-scanner");
  if (video) {
    video.srcObject = null;
    video.hidden = true;
  }
  const stop = document.querySelector("#stop-screen-qr");
  if (stop) stop.hidden = true;
}

function setScreenQrProgress(text) {
  const node = document.querySelector("#screen-qr-progress");
  if (node) node.textContent = text;
}

function showScreenQrPanel(visible, needed, holdSeconds) {
  const panel = document.querySelector("#screen-qr-panel");
  if (panel) panel.hidden = !visible;
  if (needed) screenQr.needed = needed;
  if (holdSeconds) screenQr.holdSeconds = holdSeconds;
  if (visible && !sessionStorage.getItem("zoomoodle-qr-ready")) {
    setScreenQrProgress("0.0/" + screenQr.holdSeconds + " שנ׳. ממתינים לסריקה.");
  }
}

function screenQrHeldSeconds() {
  if (!screenQr.firstAt) return 0;
  return Math.max(0, (performance.now() - screenQr.firstAt) / 1000);
}

function describeScreenQrProgress() {
  const held = screenQrHeldSeconds();
  return held.toFixed(1) + "/" + screenQr.holdSeconds + " שנ׳ · " + screenQr.codes.length + " קודים";
}

function extractScreenQrCode(raw) {
  const text = String(raw || "").trim();
  const found = text.match(/ZM1\.[A-Za-z0-9_-]+/);
  return found ? found[0] : "";
}

function decodeScreenQrFrame(video) {
  if (!video || video.readyState < 2) return "";
  const width = video.videoWidth || 0;
  const height = video.videoHeight || 0;
  if (!width || !height) return "";
  if (!screenQr.canvas) {
    screenQr.canvas = document.createElement("canvas");
    screenQr.ctx = screenQr.canvas.getContext("2d", { willReadFrequently: true });
  }
  const maxSide = 640;
  const scale = Math.min(1, maxSide / Math.max(width, height));
  screenQr.canvas.width = Math.max(1, Math.floor(width * scale));
  screenQr.canvas.height = Math.max(1, Math.floor(height * scale));
  screenQr.ctx.drawImage(video, 0, 0, screenQr.canvas.width, screenQr.canvas.height);
  const image = screenQr.ctx.getImageData(0, 0, screenQr.canvas.width, screenQr.canvas.height);
  if (typeof jsQR !== "function") return "";
  const result = jsQR(image.data, image.width, image.height, { inversionAttempts: "dontInvert" });
  return result && result.data ? extractScreenQrCode(result.data) : "";
}

async function submitScreenQr(codes) {
  const room = roomInput.value.trim();
  loadStudentSession();
  const response = await signedFetch("/api/rooms/" + encodeURIComponent(room) + "/presence/screen-qr", {
    method: "POST",
    body: JSON.stringify({ codes: codes }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    screenQr.codes = [];
    screenQr.lastRaw = "";
    screenQr.firstAt = 0;
    screenQr.submitting = false;
    setScreenQrProgress(explain(body.error, "הסריקה נכשלה. כוונו שוב לברקוד החי לשתי שניות."));
    return false;
  }
  sessionStorage.setItem("zoomoodle-qr-ready", "1");
  setScreenQrProgress("הברקוד החי התקבל. עכשיו צריך את בדיקת הרשת.");
  stopScreenQrScan();
  maybeFinishPresence();
  return true;
}

function maybeFinishPresence() {
  const challenge = sessionStorage.getItem("zoomoodle-challenge") || "";
  const pending = sessionStorage.getItem("zoomoodle-presence-pending") === "1";
  const qrReady = sessionStorage.getItem("zoomoodle-qr-ready") === "1";
  const required = sessionStorage.getItem("zoomoodle-qr-required") !== "0";
  if (pending && challenge && (!required || qrReady)) {
    finishPresence(challenge).catch((err) => {
      const note = document.querySelector("#identity-status");
      if (note) note.textContent = err.message;
    });
  }
}

async function startScreenQrScan() {
  const note = document.querySelector("#identity-status");
  if (typeof jsQR !== "function") {
    setScreenQrProgress("הדפדפן לא יכול לפענח ברקוד בלי הסורק המקומי.");
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setScreenQrProgress("הדפדפן לא נותן גישה למצלמה. צריך HTTPS או localhost.");
    return;
  }
  try {
    stopScreenQrScan();
    screenQr.codes = [];
    screenQr.lastRaw = "";
    screenQr.firstAt = 0;
    screenQr.submitting = false;
    sessionStorage.removeItem("zoomoodle-qr-ready");
    screenQr.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
    const video = document.querySelector("#screen-qr-scanner");
    video.srcObject = screenQr.stream;
    video.hidden = false;
    document.querySelector("#stop-screen-qr").hidden = false;
    setScreenQrProgress("0.0/" + screenQr.holdSeconds + " שנ׳. כוונו את המצלמה לברקוד החי.");
    const tick = () => {
      const raw = decodeScreenQrFrame(video);
      if (raw && raw !== screenQr.lastRaw) {
        screenQr.lastRaw = raw;
        if (screenQr.codes[screenQr.codes.length - 1] !== raw) {
          if (!screenQr.firstAt) screenQr.firstAt = performance.now();
          screenQr.codes.push(raw);
        }
      }
      if (screenQr.firstAt && !screenQr.submitting) {
        setScreenQrProgress(describeScreenQrProgress());
        const held = screenQrHeldSeconds();
        if (held >= screenQr.holdSeconds) {
          screenQr.submitting = true;
          const batch = screenQr.codes.slice();
          submitScreenQr(batch).catch((err) => {
            screenQr.submitting = false;
            setScreenQrProgress(err.message);
          });
          return;
        }
      }
      screenQr.timer = window.setTimeout(tick, 80);
    };
    screenQr.timer = window.setTimeout(tick, 80);
  } catch (err) {
    setScreenQrProgress(err.message);
    if (note) note.textContent = err.message;
  }
}

function attemptId() {
  let id = sessionStorage.getItem("zoomoodle-attempt");
  if (!id) {
    id = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
    sessionStorage.setItem("zoomoodle-attempt", id);
  }
  return id;
}

async function loadRosterNames() {
  const room = roomInput.value.trim();
  const response = await fetch("/api/rooms/" + encodeURIComponent(room) + "/roster/names");
  const body = await response.json().catch(() => ({}));
  const select = document.querySelector("#roster-name");
  select.replaceChildren();
  (body.names || []).forEach((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.display;
    select.appendChild(option);
  });
  const note = document.querySelector("#identity-status");
  if (!(body.names || []).length) note.textContent = "הרשימה עדיין לא נבחרה על ידי המרצה.";
  else note.textContent = "";
}

document.querySelector("#identify").addEventListener("click", async () => {
  const emailBox = document.querySelector("#email");
  const email = emailBox.value.trim();
  emailBox.value = "";
  const note = document.querySelector("#identity-status");
  if (!email || !email.includes("@")) {
    note.textContent = "צריך להזין את כתובת המייל.";
    return;
  }
  const room = roomInput.value.trim();
  const response = await fetch("/api/rooms/" + encodeURIComponent(room) + "/roster/identify", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      entry_id: document.querySelector("#roster-name").value,
      email: email,
      attempt: attemptId(),
    }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    note.textContent = explain(body.error, "בדיקת הזהות נכשלה.");
    return;
  }
  rememberSession(room, body.session_id, body.session_key, body.entry_id);
  sessionStorage.setItem("zoomoodle-display", body.display || "");
  sessionStorage.removeItem("zoomoodle-present");
  sessionStorage.removeItem("zoomoodle-qr-ready");
  sessionStorage.removeItem("zoomoodle-presence-pending");
  document.querySelector("#roster-remote").hidden = false;
  screenQr.required = body.qr_required !== false;
  sessionStorage.setItem("zoomoodle-qr-required", screenQr.required ? "1" : "0");
  if (body.qr_needed) screenQr.needed = body.qr_needed;
  if (body.qr_min_distinct) screenQr.needed = body.qr_min_distinct;
  if (body.qr_hold_seconds) screenQr.holdSeconds = body.qr_hold_seconds;
  showScreenQrPanel(screenQr.required, screenQr.needed, screenQr.holdSeconds);
  if (body.presence === "ready" && body.bind_url && body.challenge_id) {
    sessionStorage.setItem("zoomoodle-bind", body.bind_url);
    sessionStorage.setItem("zoomoodle-challenge", body.challenge_id);
    document.querySelector("#prove-network").hidden = false;
    note.textContent = screenQr.required
      ? "הזהות התקבלה. החזיקו את המצלמה על הברקוד החי שתי שניות, ואז פתחו את המאמת המקומי. אין סימון לפני שניהם."
      : "הזהות התקבלה. עדיין אין סימון עד שהטלפון מגיע למאמת.";
  } else {
    document.querySelector("#prove-network").hidden = true;
    note.textContent = "הזהות התקבלה, אבל המאמת המקומי לא פועל. אין סימון נוכחות.";
  }
});

document.querySelector("#scan-screen-qr").addEventListener("click", () => {
  startScreenQrScan();
});
document.querySelector("#stop-screen-qr").addEventListener("click", () => {
  stopScreenQrScan();
  setScreenQrProgress("המצלמה נעצרה.");
});

document.querySelector("#prove-network").addEventListener("click", () => {
  const bind = sessionStorage.getItem("zoomoodle-bind") || "";
  const challenge = sessionStorage.getItem("zoomoodle-challenge") || "";
  if (!bind || !challenge) return;
  window.location.assign(bind.replace(/\/$/, "") + "/prove?c=" + encodeURIComponent(challenge));
});

document.querySelector("#roster-remote").addEventListener("click", async () => {
  const room = roomInput.value.trim();
  const response = await signedFetch("/api/rooms/" + encodeURIComponent(room) + "/roster/remote", {
    method: "POST",
    body: "{}",
  });
  const body = await response.json().catch(() => ({}));
  const note = document.querySelector("#identity-status");
  if (!response.ok) {
    note.textContent = explain(body.error, "לא הצלחנו לסמן חיבור מרחוק.");
    return;
  }
  document.querySelector("#welcome").hidden = true;
  document.querySelector("#remote-banner").hidden = false;
  enterLesson("remote", body.marker || flow.attendanceId);
});

async function finishPresence(challengeId) {
  const room = roomInput.value.trim();
  loadStudentSession();
  const response = await signedFetch("/api/rooms/" + encodeURIComponent(room) + "/presence/finish", {
    method: "POST",
    body: JSON.stringify({ challenge_id: challengeId }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || !body.in_class) {
    const note = document.querySelector("#identity-status");
    const reason = body.error || "";
    if (reason === "qr_required") {
      sessionStorage.setItem("zoomoodle-presence-pending", "1");
      showStep("identity");
      showScreenQrPanel(true, screenQr.needed, screenQr.holdSeconds);
      if (note) note.textContent = explain(reason, "עדיין צריך לסרוק את הברקוד החי.");
      return;
    }
    if (note) note.textContent = explain(reason, "אין סימון נוכחות.");
    showStep("identity");
    return;
  }
  sessionStorage.removeItem("zoomoodle-presence-pending");
  sessionStorage.setItem("zoomoodle-present", "1");
  if (body.display) sessionStorage.setItem("zoomoodle-display", body.display);
  history.replaceState(null, "", location.pathname + location.search);
  enterLesson("in_class", (studentSession && studentSession.studentId) || flow.attendanceId);
}

function showLearn(name) {
  document.querySelectorAll("[data-learn-panel]").forEach((panel) => {
    panel.classList.toggle("selected", panel.getAttribute("data-learn-panel") === name);
  });
  document.querySelectorAll("[data-learn]").forEach((button) => {
    button.classList.toggle("selected", button.getAttribute("data-learn") === name);
  });
}

document.querySelectorAll("[data-learn]").forEach((button) => {
  button.addEventListener("click", () => showLearn(button.getAttribute("data-learn")));
});

async function loadSources() {
  const room = roomInput.value.trim();
  if (!room) return;
  const response = await fetch("/api/rooms/" + encodeURIComponent(room) + "/sources");
  if (!response.ok) return;
  const body = await response.json();
  const box = document.querySelector("#sources");
  const sources = body.sources || [];
  if (!sources.length) {
    box.textContent = "No sources yet.";
    return;
  }
  box.replaceChildren();
  sources.forEach((source) => {
    const label = document.createElement("label");
    label.className = "row";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = true;
    input.value = source.id;
    input.style.width = "auto";
    label.appendChild(input);
    label.appendChild(document.createTextNode(" " + source.title));
    box.appendChild(label);
  });
}

document.querySelector("#ask-send").addEventListener("click", async () => {
  const room = roomInput.value.trim();
  const ids = Array.from(document.querySelectorAll("#sources input:checked")).map((input) => input.value);
  const response = await fetch("/api/rooms/" + encodeURIComponent(room) + "/ask", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ question: document.querySelector("#ask-text").value, source_ids: ids }),
  });
  const body = await response.json().catch(() => ({}));
  const out = document.querySelector("#ask-result");
  if (!response.ok) {
    out.textContent = explain(body.error, "Could not answer.");
    return;
  }
  const mode = body.mode === "model" ? "Model answer from the sources." : "Source search, not a model.";
  document.querySelector("#ask-mode").textContent = mode;
  const lines = [body.answer || ""];
  (body.snippets || []).forEach((snippet) => lines.push(snippet.title + ": " + snippet.text));
  out.textContent = lines.join("\n\n");
});

(function resumePresence() {
  const hash = new URLSearchParams(String(location.hash || "").replace(/^#/, ""));
  const challenge = hash.get("presence");
  if (!challenge) return;
  const paramsNow = new URLSearchParams(location.search);
  if (paramsNow.get("room")) roomInput.value = paramsNow.get("room");
  loadStudentSession();
  sessionStorage.setItem("zoomoodle-challenge", challenge);
  sessionStorage.setItem("zoomoodle-presence-pending", "1");
  const required = sessionStorage.getItem("zoomoodle-qr-required") !== "0";
  const qrReady = sessionStorage.getItem("zoomoodle-qr-ready") === "1";
  if (required && !qrReady) {
    showStep("identity");
    showScreenQrPanel(true, screenQr.needed);
    document.querySelector("#identity-status").textContent = "הרשת התקבלה. עדיין צריך לסרוק את הברקוד הרץ.";
    return;
  }
  finishPresence(challenge).catch((err) => {
    document.querySelector("#identity-status").textContent = err.message;
  });
}());

(function restoreFlow() {
  if (params.get("code")) document.querySelector("#code").value = params.get("code");
  let saved = null;
  try { saved = JSON.parse(sessionStorage.getItem("zoomoodle-student-flow") || "null"); } catch (_err) { saved = null; }
  const urlRoom = params.get("room") || "";
  if (!saved || (urlRoom && saved.room && saved.room !== urlRoom)) return;
  if (saved.room) roomInput.value = saved.room;
  loadStudentSession();
  flow.band = saved.band || flow.band;
  flow.proof = saved.proof || flow.proof;
  flow.title = saved.title || "";
  if (saved.step === "lesson" && saved.attendanceId) enterLesson(saved.mode || "in_class", saved.attendanceId, flow.title);
  else if (saved.step === "class" || saved.step === "mode") showStep(saved.step);
}());

setInterval(() => refreshLesson().catch(() => {}), 3000);
