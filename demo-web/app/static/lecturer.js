/* ZooMoodle lecturer page. The lecturer key is sent once to sign in; only the session token is kept. */
const ZONES = ["front-left", "front-center", "front-right", "middle-left", "middle-center", "middle-right", "back-left", "back-center", "back-right"];
const ZONE_HE = { "front-left": "קדימה שמאל", "front-center": "קדימה מרכז", "front-right": "קדימה ימין", "middle-left": "אמצע שמאל", "middle-center": "אמצע מרכז", "middle-right": "אמצע ימין", "back-left": "אחורה שמאל", "back-center": "אחורה מרכז", "back-right": "אחורה ימין" };
const state = { token: sessionStorage.getItem("zm-lecturer") || "", roomId: "", greeting: "", code: "", seed: "", hz: 20, raf: 0, tick: -1, timers: [] };
const $ = (sel) => document.querySelector(sel);

function esc(v) { return String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

async function api(path, options = {}) {
  const headers = Object.assign({ "x-lecturer-session": state.token }, options.headers || {});
  if (options.body && !(options.body instanceof FormData)) headers["content-type"] = "application/json";
  const res = await fetch(path, Object.assign({}, options, { headers }));
  if (res.status === 401 && path !== "/api/lecturer/login") { signOut(); throw new Error("צריך להיכנס שוב"); }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || ("HTTP " + res.status));
  return body;
}

function show(id) { ["login", "home", "room"].forEach((name) => { $("#" + name).hidden = name !== id; }); }

function signOut() {
  state.token = ""; sessionStorage.removeItem("zm-lecturer"); stopRoom(); show("login");
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("#lecturer-key");
  try {
    const body = await api("/api/lecturer/login", { method: "POST", body: JSON.stringify({ key: input.value }) });
    input.value = "";
    state.token = body.token; sessionStorage.setItem("zm-lecturer", body.token);
    enterHome(body.greeting);
  } catch (err) {
    $("#login-state").textContent = err.message === "bad_lecturer_key" ? "המפתח שגוי." : err.message === "login_limited" ? "יותר מדי ניסיונות. נסה שוב בעוד כמה דקות." : err.message;
  }
});

$("#logout").addEventListener("click", async () => { await api("/api/lecturer/logout", { method: "POST" }).catch(() => {}); signOut(); });

async function enterHome(greeting) {
  state.greeting = greeting; $("#greeting").textContent = greeting; show("home");
  const rooms = await api("/api/rooms").catch(() => ({ rooms: [] }));
  $("#open-rooms").innerHTML = rooms.rooms.length
    ? "שיעורים פתוחים: " + rooms.rooms.map((r) => `<button class="ghost" data-room="${esc(r.id)}" type="button">${esc(r.title)}</button>`).join(" ")
    : "";
  document.querySelectorAll("[data-room]").forEach((b) => b.addEventListener("click", () => enterRoom(b.dataset.room)));
}

$("#new-room").addEventListener("click", async () => {
  const room = await api("/api/rooms", { method: "POST", body: JSON.stringify({ title: $("#room-title").value }) });
  enterRoom(room.id);
});

async function enterRoom(roomId) {
  state.roomId = roomId; location.hash = roomId; show("room");
  $("#room-greeting").textContent = state.greeting;
  await refreshDashboard();
  state.timers.push(setInterval(refreshBarcode, 200));
  state.timers.push(setInterval(() => refreshDashboard().catch(() => {}), 2000));
  startFlicker();
}

function stopRoom() {
  state.timers.forEach(clearInterval); state.timers = [];
  if (state.raf) cancelAnimationFrame(state.raf); state.raf = 0;
}

/* ----- live flickering barcode ----- */
function hash32(text) { let h = 2166136261; for (let i = 0; i < text.length; i += 1) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
function rng32(seed) { let a = seed >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

function paintFlicker(now) {
  const canvas = $("#flicker"); const frame = $("#live-frame");
  if (!state.seed || !frame.clientWidth) return;
  const tick = Math.floor((now / 1000) * state.hz);
  const w = frame.clientWidth; const h = frame.clientHeight; const ratio = window.devicePixelRatio || 1;
  if (canvas.width !== Math.floor(w * ratio)) { canvas.width = Math.floor(w * ratio); canvas.height = Math.floor(h * ratio); state.tick = -1; }
  if (tick === state.tick) return;
  state.tick = tick;
  const ctx = canvas.getContext("2d"); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, w, h);
  const rnd = rng32(hash32(state.seed + ":" + tick)); const cells = 28; const cell = w / cells; const rows = Math.ceil(h / cell);
  const colors = ["#081018", "#f4fbff", "#3d9cf0", "#7cf0d0", "#ffd36a"];
  for (let y = 0; y < rows; y += 1) for (let x = 0; x < cells; x += 1) {
    if (!(x < 3 || y < 3 || x >= cells - 3 || y >= rows - 3)) continue;
    const v = rnd(); if (v < 0.12) continue;
    ctx.fillStyle = colors[Math.floor(v * colors.length) % colors.length]; ctx.fillRect(x * cell, y * cell, cell + 0.6, cell + 0.6);
  }
}
function startFlicker() { const loop = (t) => { paintFlicker(t); state.raf = requestAnimationFrame(loop); }; state.raf = requestAnimationFrame(loop); }

async function refreshBarcode() {
  if (!state.roomId) return;
  try {
    const body = await api("/api/rooms/" + state.roomId + "/barcode");
    state.seed = body.flicker_seed; state.hz = body.qr_flicker_hz || 20;
    if (body.code !== state.code) { state.code = body.code; $("#live-qr").innerHTML = ZooQR.toSvg(body.code, 5); }
    $("#live-level").style.width = Math.min(100, (body.expires_in / body.qr_frame_seconds) * 100) + "%";
  } catch (_err) { /* room closed */ }
}

/* ----- dashboard ----- */
async function refreshDashboard() {
  const d = await api("/api/rooms/" + state.roomId + "/dashboard");
  $("#room-title-view").textContent = d.title + (d.closed ? " (סגור)" : "");
  if ($("#join-link").textContent !== d.student_url) {
    $("#join-link").textContent = d.student_url; $("#join-link").href = d.student_url;
    $("#join-qr").innerHTML = ZooQR.toSvg(d.student_url, 4);
  }
  $("#c-in").textContent = d.counts.in_class; $("#c-remote").textContent = d.counts.remote;
  $("#c-pending").textContent = d.counts.pending; $("#c-conflicts").textContent = d.counts.conflicts;
  $("#zone-map").innerHTML = ZONES.map((z) => `<div><b>${d.zones[z] || 0}</b>${ZONE_HE[z]}</div>`).join("");
  $("#students").innerHTML = d.students.map((s) => `<tr><td>${s.checked ? "✓" : ""}</td><td>${esc(s.name)}</td><td>${esc(s.mode)}</td><td>${esc(s.state_text)}</td><td>${esc(ZONE_HE[s.zone] || "")}</td></tr>`).join("");
  renderConflicts(d.conflicts);
  $("#questions").innerHTML = d.questions.map((q) => `<li><span class="tag">${q.votes}▲</span> ${esc(q.text)} <span class="note">${esc(q.name)}</span></li>`).join("") || '<li class="note">אין עדיין</li>';
  $("#comments").innerHTML = d.comments.map((c) => `<li>${esc(c.text)} <span class="note">${esc(c.name)}</span></li>`).join("") || '<li class="note">אין עדיין</li>';
  $("#polls").innerHTML = d.polls.map((p) => `<div style="margin-top:.7rem"><b>${esc(p.question)}</b> <span class="note">${p.answer_count} תשובות</span>
    ${Object.entries(p.counts || {}).map(([o, n]) => `<div>${esc(o)}${o === p.correct_option ? " ✓" : ""}: ${n}</div>`).join("")}
    ${p.open ? `<button class="ghost" data-close-poll="${esc(p.id)}" type="button">סגור סקר</button>` : '<span class="tag">סגור</span>'}</div>`).join("");
  document.querySelectorAll("[data-close-poll]").forEach((b) => b.addEventListener("click", () => api(`/api/rooms/${state.roomId}/polls/${b.dataset.closePoll}/close`, { method: "POST" }).then(refreshDashboard)));
  $("#homework").innerHTML = d.homework.map((h) => `<li>${esc(h.title)} <span class="note">${esc(h.filename)} · ${Math.ceil(h.size / 1024)}KB</span></li>`).join("");
  if (d.summary && !$("#summary-state").dataset.shown) { $("#summary-state").textContent = "סיכום מפורסם לסטודנטים."; }
}

function renderConflicts(list) {
  const box = $("#conflicts");
  if (!list.length) { box.textContent = "אין כרגע."; return; }
  box.innerHTML = list.map((c) => {
    const email = c.email || null;
    const emailHtml = !email ? "" : email.demo_code
      ? `<p class="warn">${esc(email.demo_label)}: <span class="demo-code">${esc(email.demo_code)}</span> (פג בעוד ${email.expires_in} שנ׳)</p>`
      : email.open ? `<p class="note">נשלח קוד למייל הרשום של השם (פג בעוד ${email.expires_in} שנ׳).</p>` : "";
    return `<div class="card"><b>${esc(c.name)}</b>${emailHtml}<ul class="plain">${c.claims.map((k) => `<li>
      ${k.mode === "in_class" ? "בכיתה" : "מרחוק"} · ${esc(k.state_text)} ${k.zone ? "· " + esc(ZONE_HE[k.zone]) : ""}
      <button data-decide="${esc(k.claim_id)}" data-action="accept" type="button">זה הוא</button>
      <button class="bad" data-decide="${esc(k.claim_id)}" data-action="reject" type="button">דחה</button></li>`).join("")}</ul></div>`;
  }).join("");
  box.querySelectorAll("[data-decide]").forEach((b) => b.addEventListener("click", () =>
    api(`/api/rooms/${state.roomId}/conflicts/decide`, { method: "POST", body: JSON.stringify({ claim_id: b.dataset.decide, action: b.dataset.action }) }).then(refreshDashboard)));
}

$("#roster-file").addEventListener("change", async (event) => {
  const file = event.target.files[0]; if (!file) return;
  try {
    const form = new FormData(); form.append("file", file);
    const r = await api("/api/rooms/" + state.roomId + "/roster", { method: "POST", body: form });
    $("#roster-state").textContent = `נטענו ${r.imported} שמות (${r.duplicates} כפולים, ${r.skipped} דולגו). המיילים לא מוצגים.`;
  } catch (err) { $("#roster-state").textContent = err.message; }
});

$("#poll-create").addEventListener("click", async () => {
  const options = $("#poll-opts").value.split(",").map((s) => s.trim()).filter(Boolean);
  await api("/api/rooms/" + state.roomId + "/polls", { method: "POST", body: JSON.stringify({ question: $("#poll-q").value, options, correct_option: $("#poll-correct").value.trim() || null }) });
  $("#poll-q").value = ""; $("#poll-opts").value = ""; $("#poll-correct").value = ""; refreshDashboard();
});

$("#hw-upload").addEventListener("click", async () => {
  const file = $("#hw-file").files[0]; if (!file) return;
  const form = new FormData(); form.append("file", file); form.append("title", $("#hw-title").value);
  await api("/api/rooms/" + state.roomId + "/homework", { method: "POST", body: form });
  $("#hw-file").value = ""; $("#hw-title").value = ""; refreshDashboard();
});

$("#summary-generate").addEventListener("click", async () => {
  const note = $("#summary-state"); note.dataset.shown = "1";
  const key = $("#llm-key");
  try {
    const file = $("#transcript").files[0];
    if (file) await api("/api/rooms/" + state.roomId + "/transcript", { method: "POST", body: JSON.stringify({ transcript: await file.text() }) });
    note.textContent = "יוצר סיכום…";
    const r = await api("/api/rooms/" + state.roomId + "/summary/generate", { method: "POST", body: JSON.stringify({ provider: $("#llm-provider").value, model: $("#llm-model").value, api_key: key.value }) });
    $("#summary-text").value = r.text; note.textContent = "הסיכום פורסם לכל הסטודנטים בשיעור.";
  } catch (err) { note.textContent = err.message; }
  finally { key.value = ""; }
});

$("#summary-publish").addEventListener("click", async () => {
  try { await api("/api/rooms/" + state.roomId + "/summary", { method: "POST", body: JSON.stringify({ text: $("#summary-text").value }) }); $("#summary-state").textContent = "פורסם."; }
  catch (err) { $("#summary-state").textContent = err.message; }
});

async function download(kind) {
  const res = await fetch(`/api/rooms/${state.roomId}/export.${kind}`, { headers: { "x-lecturer-session": state.token } });
  const url = URL.createObjectURL(await res.blob()); const a = document.createElement("a");
  a.href = url; a.download = `${state.roomId}-attendance.${kind}`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$("#export-csv").addEventListener("click", (e) => { e.preventDefault(); download("csv"); });
$("#export-xlsx").addEventListener("click", (e) => { e.preventDefault(); download("xlsx"); });
$("#close-room").addEventListener("click", async () => {
  if (!confirm("לסגור את השיעור?")) return;
  await api("/api/rooms/" + state.roomId + "/close", { method: "POST" }); stopRoom(); refreshDashboard();
});

(async function boot() {
  if (!state.token) { show("login"); return; }
  try {
    const me = await api("/api/lecturer/me");
    const roomId = location.hash.slice(1);
    state.greeting = me.greeting;
    if (roomId) await enterRoom(roomId).catch(() => enterHome(me.greeting)); else enterHome(me.greeting);
  } catch (_err) { show("login"); }
}());
