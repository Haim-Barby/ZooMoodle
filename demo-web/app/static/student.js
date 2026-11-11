/* ZooMoodle student phone page. Lesson actions are signed with a per-session HMAC key. */
const ZONES = ["front-left", "front-center", "front-right", "middle-left", "middle-center", "middle-right", "back-left", "back-center", "back-right"];
const ZONE_HE = { "front-left": "קדימה שמאל", "front-center": "קדימה מרכז", "front-right": "קדימה ימין", "middle-left": "אמצע שמאל", "middle-center": "אמצע מרכז", "middle-right": "אמצע ימין", "back-left": "אחורה שמאל", "back-center": "אחורה מרכז", "back-right": "אחורה ימין" };
const ERRORS = {
  not_on_campus_network: "אתה לא מחובר לרשת של האוניברסיטה. התחבר ל־Wi‑Fi של הקמפוס (לא דרך סלולר) ונסה שוב, או בחר \"מרחוק\".",
  qr_static: "זוהתה תמונה קפואה. צריך לכוון לברקוד החי על המסך.",
  qr_short: "הסריקה קצרה מדי. החזק את המצלמה על הברקוד 2 שניות.",
  qr_stale: "הברקוד ישן מדי. סרוק את המסך עצמו, בזמן אמת.",
  qr_sequence: "הסריקה נקטעה. נסה שוב והחזק יציב.",
  qr_mismatch: "זה לא הברקוד של השיעור הזה.",
  qr_replay: "הקודים האלה כבר שימשו. סרוק שוב את המסך.",
  bad_code: "הקוד שגוי.",
  code_expired: "הקוד פג. המרצה יחליט.",
  code_attempts: "יותר מדי ניסיונות. המרצה יחליט.",
  room_closed: "השיעור נסגר.",
  unknown_room: "השיעור לא נמצא. סרוק שוב את קוד ההצטרפות.",
  not_checked_in: "צריך לסיים את הכניסה לשיעור קודם.",
  already_answered: "כבר ענית על הסקר הזה.",
  session_expired: "השעון בטלפון לא מכוון. כוון שעה אוטומטית ונסה שוב.",
};
const $ = (s) => document.querySelector(s);
const roomId = new URLSearchParams(location.search).get("room") || "";
const STORE_KEY = "zm-session-" + roomId;
let session = JSON.parse(localStorage.getItem(STORE_KEY) || "null");
let names = [];
let lastState = "";
let lastShown = "";
const scan = { stream: null, codes: [], first: 0, timer: 0, busy: false, hold: 2, canvas: null, ctx: null };

function esc(v) { return String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function say(code, fallback) { $("#alert").textContent = code ? (ERRORS[code] || fallback || code) : ""; }

/* ----- signing ----- */
function b64u(bytes) { let t = ""; bytes.forEach((b) => { t += String.fromCharCode(b); }); return btoa(t).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); }
function unb64u(text) { const raw = atob(text.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (text.length % 4)) % 4)); return Uint8Array.from(raw, (c) => c.charCodeAt(0)); }
async function macKey(secret) {
  const base = await crypto.subtle.importKey("raw", unb64u(secret), "HKDF", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({ name: "HKDF", hash: "SHA-256", salt: new TextEncoder().encode("zoomoodle-session-v1"), info: new TextEncoder().encode("zoomoodle-session-mac") }, base, 256);
  return crypto.subtle.importKey("raw", bits, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
}
async function signed(path, method = "GET", payload) {
  const body = payload === undefined ? "" : JSON.stringify(payload);
  const stamp = String(Math.floor(Date.now() / 1000));
  const nonce = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
  const key = await macKey(session.session_key);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode([method, path, body, stamp, nonce].join("\n"))));
  const headers = { "x-zoomoodle-session": session.session_id, "x-zoomoodle-timestamp": stamp, "x-zoomoodle-nonce": nonce, "x-zoomoodle-signature": b64u(mac) };
  if (body) headers["content-type"] = "application/json";
  return fetch(path, { method, headers, body: body || undefined });
}
async function call(path, method, payload) {
  const res = await signed(path, method, payload);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || "HTTP " + res.status), { code: data.error });
  return data;
}
const R = (p) => `/api/rooms/${encodeURIComponent(roomId)}${p}`;

/* ----- steps ----- */
function step(name) { ["step-name", "step-scan", "step-area", "step-wait", "lesson"].forEach((id) => { $("#" + id).hidden = id !== name; }); }

async function loadNames() {
  const res = await fetch(R("/roster/names"));
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { say(data.error); return; }
  names = data.names || [];
  const opts = '<option value="">— בחר שם —</option>' + names.map((n) => `<option value="${esc(n.id)}">${esc(n.display)}</option>`).join("");
  $("#name").innerHTML = opts; $("#repick-name").innerHTML = opts;
}

async function join(mode) {
  say("");
  const entry = $("#name").value;
  if (!entry) { say("x", "בחר קודם את השם שלך."); return; }
  const res = await fetch(R("/join"), { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ entry_id: entry, mode }) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { say(data.error); return; }
  session = { session_id: data.session_id, session_key: data.session_key };
  localStorage.setItem(STORE_KEY, JSON.stringify(session));
  render(data);
}
$("#go-class").addEventListener("click", () => join("in_class"));
$("#go-remote").addEventListener("click", () => join("remote"));

function render(me) {
  lastState = me.state;
  $("#repick").hidden = me.state !== "repick";
  if (me.state === "pending_barcode") { step("step-scan"); return; }
  if (me.state === "needs_area") { stopScan(); step("step-area"); return; }
  if (me.state === "present" || me.state === "remote") {
    const first = lastShown !== me.state;
    lastShown = me.state;
    stopScan(); step("lesson");
    $("#welcome").textContent = me.welcome;
    $("#where").textContent = me.state === "remote" ? "מחובר מרחוק" : "בכיתה · " + (ZONE_HE[me.zone] || "");
    if (first) refreshLesson().catch(() => {});
    return;
  }
  lastShown = me.state;
  stopScan(); step("step-wait");
  $("#code-box").hidden = me.state !== "email_code";
  const texts = {
    repick: ["שם כפול", "בחר שוב את השם שלך בחלון שנפתח."],
    email_code: ["אימות במייל", me.email_sent ? "שלחנו קוד בן 6 ספרות למייל הרשום של השם הזה. מי שמקליד אותו מקבל את השם." : "שלחנו קוד בן 6 ספרות לבעל השם. בהדגמה המרצה רואה את הקוד על המסך שלו."],
    flagged_remote: ["בבדיקה", "השם הזה נבחר גם במקום אחר. המרצה יחליט."],
    lecturer_decision: ["המרצה יחליט", "לא הצלחנו להכריע אוטומטית. המרצה יבדוק בכיתה."],
    rejected: ["לא אושר", "המרצה לא אישר את הכניסה עם השם הזה."],
  }[me.state] || [me.state_text, ""];
  $("#wait-title").textContent = texts[0]; $("#wait-text").textContent = texts[1];
}

async function refreshMe() {
  if (!session) return;
  try { render(await call(R("/me"))); } catch (err) {
    if (["session_required", "bad_session", "unknown_claim", "session_mismatch"].includes(err.code)) { localStorage.removeItem(STORE_KEY); session = null; step("step-name"); }
  }
}

/* ----- live barcode scan ----- */
function stopScan() {
  clearTimeout(scan.timer); scan.timer = 0;
  if (scan.stream) scan.stream.getTracks().forEach((t) => t.stop());
  scan.stream = null; $("#video").hidden = true;
}
function decode(video) {
  if (video.readyState < 2 || !video.videoWidth) return "";
  if (!scan.canvas) { scan.canvas = document.createElement("canvas"); scan.ctx = scan.canvas.getContext("2d", { willReadFrequently: true }); }
  const k = Math.min(1, 640 / Math.max(video.videoWidth, video.videoHeight));
  scan.canvas.width = Math.floor(video.videoWidth * k); scan.canvas.height = Math.floor(video.videoHeight * k);
  scan.ctx.drawImage(video, 0, 0, scan.canvas.width, scan.canvas.height);
  const img = scan.ctx.getImageData(0, 0, scan.canvas.width, scan.canvas.height);
  const found = jsQR(img.data, img.width, img.height, { inversionAttempts: "dontInvert" });
  const m = found && found.data ? found.data.match(/ZM1\.[A-Za-z0-9_-]+/) : null;
  return m ? m[0] : "";
}
async function startScan() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { $("#scan-state").textContent = "אין גישה למצלמה. צריך לפתוח את האתר ב־HTTPS."; return; }
  stopScan(); scan.codes = []; scan.first = 0; scan.busy = false;
  scan.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
  const video = $("#video"); video.srcObject = scan.stream; video.hidden = false; await video.play();
  const tick = async () => {
    const code = decode(video);
    if (code && scan.codes[scan.codes.length - 1] !== code) { if (!scan.first) scan.first = performance.now(); scan.codes.push(code); }
    const held = scan.first ? (performance.now() - scan.first) / 1000 : 0;
    $("#scan-level").style.width = Math.min(100, (held / scan.hold) * 100) + "%";
    $("#scan-state").textContent = held.toFixed(1) + "/" + scan.hold + " שנ׳ · " + scan.codes.length + " קודים";
    if (held >= scan.hold && !scan.busy) {
      scan.busy = true;
      try { render(await call(R("/barcode"), "POST", { codes: scan.codes.slice() })); say(""); return; }
      catch (err) { say(err.code, err.message); scan.codes = []; scan.first = 0; scan.busy = false; }
    }
    scan.timer = setTimeout(tick, 80);
  };
  tick();
}
$("#scan-start").addEventListener("click", () => startScan().catch((e) => { $("#scan-state").textContent = e.message; }));

$("#zones").innerHTML = ZONES.map((z) => `<button class="ghost" data-zone="${z}" type="button">${ZONE_HE[z]}</button>`).join("");
$("#zones").addEventListener("click", async (e) => {
  const zone = e.target.dataset && e.target.dataset.zone; if (!zone) return;
  try { render(await call(R("/area"), "POST", { zone })); } catch (err) { say(err.code, err.message); }
});

$("#repick-send").addEventListener("click", async () => {
  const entry = $("#repick-name").value; if (!entry) return;
  try { render(await call(R("/repick"), "POST", { entry_id: entry })); } catch (err) { say(err.code, err.message); }
});
$("#code-send").addEventListener("click", async () => {
  try { render(await call(R("/email-code"), "POST", { code: $("#code").value })); say(""); } catch (err) { say(err.code, err.message); refreshMe(); }
});

/* ----- lesson ----- */
async function lessonPart(path, fallback) {
  try { return await call(path); } catch (_err) { return fallback; }
}
async function refreshLesson() {
  if (lastState !== "present" && lastState !== "remote") return;
  const [polls, questions, homework, summary] = await Promise.all([
    lessonPart(R("/polls"), { polls: [] }),
    lessonPart(R("/questions"), { questions: [] }),
    lessonPart(R("/homework"), { homework: [] }),
    lessonPart(R("/summary"), { text: "" }),
  ]);
  const open = (polls.polls || []).filter((p) => p.open || p.voted_option);
  $("#polls").innerHTML = open.length ? open.map((p) => `<div style="margin-bottom:.7rem"><b>${esc(p.question)}</b><div class="row">${(p.options || []).map((o) =>
    `<button class="${p.voted_option === o ? "" : "ghost"}" data-poll="${esc(p.id)}" data-opt="${esc(o)}" ${p.voted_option || !p.open ? "disabled" : ""} type="button">${esc(o)}${p.counts ? " (" + p.counts[o] + ")" : ""}</button>`).join("")}</div></div>`).join("") : "אין סקר פתוח.";
  $("#questions").innerHTML = (questions.questions || []).map((q) => `<li><button class="ghost" data-up="${esc(q.id)}" ${q.upvoted ? "disabled" : ""} type="button">▲ ${q.votes}</button> ${esc(q.text)}</li>`).join("");
  $("#homework").innerHTML = (homework.homework || []).map((h) => `<li><button class="ghost" data-hw="${esc(h.id)}" data-name="${esc(h.filename)}" type="button">⬇ ${esc(h.title)}</button> <span class="note">${esc(h.filename)}</span></li>`).join("") || '<li class="note">אין עדיין.</li>';
  if (summary.text) $("#summary").textContent = summary.text;
}
document.addEventListener("click", async (e) => {
  const t = e.target.closest("button"); if (!t) return;
  try {
    if (t.dataset.poll) { await call(R(`/polls/${t.dataset.poll}/answers`), "POST", { option: t.dataset.opt }); refreshLesson(); }
    if (t.dataset.up) { await call(R(`/questions/${t.dataset.up}/upvote`), "POST"); refreshLesson(); }
    if (t.dataset.hw) {
      const res = await signed(R(`/homework/${t.dataset.hw}`));
      const url = URL.createObjectURL(await res.blob()); const a = document.createElement("a");
      a.href = url; a.download = t.dataset.name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
  } catch (err) { $("#lesson-state").textContent = ERRORS[err.code] || err.message; }
});
$("#note-send").addEventListener("click", async () => {
  try { await call(R("/comments"), "POST", { text: $("#note-text").value }); $("#note-text").value = ""; $("#lesson-state").textContent = "ההערה נשלחה."; }
  catch (err) { $("#lesson-state").textContent = ERRORS[err.code] || err.message; }
});
$("#q-send").addEventListener("click", async () => {
  try { await call(R("/questions"), "POST", { text: $("#q-text").value }); $("#q-text").value = ""; refreshLesson(); }
  catch (err) { $("#lesson-state").textContent = ERRORS[err.code] || err.message; }
});
$("#my-summary").addEventListener("click", async () => {
  const key = $("#llm-key");
  try {
    $("#summary").textContent = "יוצר סיכום…";
    const r = await call(R("/summary/generate"), "POST", { provider: $("#llm-provider").value, model: $("#llm-model").value, api_key: key.value });
    $("#summary").textContent = r.text;
  } catch (err) { $("#summary").textContent = err.message; }
  finally { key.value = ""; }
});

(async function boot() {
  if (!roomId) { say("x", "חסר קוד שיעור. סרוק את קוד ההצטרפות שעל המסך."); return; }
  const info = await fetch(R("")).then((r) => r.json()).catch(() => ({}));
  if (info.title) $("#title").textContent = info.title;
  if (info.qr_hold_seconds) scan.hold = info.qr_hold_seconds;
  await loadNames();
  if (session) await refreshMe(); else step("step-name");
  setInterval(refreshMe, 2000);
  setInterval(() => refreshLesson().catch(() => {}), 2000);
}());
