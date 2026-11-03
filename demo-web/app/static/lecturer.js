const tokenInput = document.querySelector("#token");
const savedToken = sessionStorage.getItem("zoomoodle-lecturer-token") || "";
if (savedToken) tokenInput.value = savedToken;

const state = {
  roomId: null,
  audio: null,
  playing: false,
  lastCode: "",
  llmConfigLoaded: false,
  llmKeyConfigured: false,
  payloadHex: "",
  source: null,
  gain: null,
  analyser: null,
  raf: 0,
  closed: false,
  camera: null,
  band: "ultrasonic",
  proof: "both",
  joinLink: "",
};

function authHeaders() {
  return { "x-lecturer-token": tokenInput.value.trim() };
}

async function api(path, options = {}) {
  const headers = Object.assign({ "content-type": "application/json" }, authHeaders(), options.headers || {});
  if (options.body === undefined) delete headers["content-type"];
  const response = await fetch(path, Object.assign({}, options, { headers }));
  const text = await response.text();
  let body = null;
  if (text) {
    try { body = JSON.parse(text); } catch (_err) { body = { error: text }; }
  }
  if (!response.ok) {
    const message = body && body.error ? body.error : response.statusText;
    throw new Error(message);
  }
  return body;
}

function showApp() {
  document.querySelector("#gate").hidden = true;
  document.querySelector("#shell").hidden = false;
}

document.querySelector("#unlock-form").addEventListener("submit", (event) => event.preventDefault());
document.querySelector("#save-token").addEventListener("click", async () => {
  sessionStorage.setItem("zoomoodle-lecturer-token", tokenInput.value.trim());
  const unlocked = await loadLlm();
  document.querySelector("#token-state").textContent = unlocked
    ? "Saved in this browser tab's session only."
    : "Enter the lecturer token to load model settings.";
  if (unlocked) {
    showApp();
    await restoreRoom();
  }
});

const ROOM_KEY = "zoomoodle-lecturer-room";

function showTab(name) {
  document.querySelectorAll(".nav-item").forEach((button) => {
    const on = button.dataset.tab === name;
    button.classList.toggle("selected", on);
    button.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll(".panel").forEach((panel) => {
    panel.hidden = panel.dataset.panel !== name;
  });
  if (name === "architecture") loadDiagrams().catch(() => {});
}

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => showTab(button.dataset.tab));
});

document.querySelector("#theme").addEventListener("click", () => {
  const root = document.documentElement;
  const next = root.dataset.theme === "dark" ? "light" : "dark";
  root.dataset.theme = next;
  localStorage.setItem("zoomoodle-theme", next);
});
const savedTheme = localStorage.getItem("zoomoodle-theme");
if (savedTheme) document.documentElement.dataset.theme = savedTheme;

function showRoom(room) {
  state.roomId = room.id;
  state.closed = !!room.closed;
  sessionStorage.setItem(ROOM_KEY, room.id);
  const path = room.student_url || room.student_path || ("/student?room=" + room.id);
  const link = new URL(path, window.location.origin).href;
  document.querySelector("#room-info").innerHTML =
    "Room <strong>" + room.id + "</strong>. Student link: <a href=\"" + link + "\">" + link + "</a>";
  document.querySelector("#student-link").innerHTML = "<a href=\"" + link + "\">" + link + "</a>";
  document.querySelector("#room-code").textContent = room.id;
  document.querySelector("#lesson-title").textContent = room.title || "Lesson";
  if (room.title) document.querySelector("#title").value = room.title;
  state.band = room.audio_band || state.band;
  state.proof = room.proof || state.proof;
  state.joinLink = link;
  if (room.audio_band) document.querySelector("#audio-band").value = room.audio_band;
  if (room.proof) document.querySelector("#proof").value = room.proof;
  document.querySelector("#play").disabled = !!room.closed || state.proof === "qr";
  document.querySelector("#close-room").disabled = !!room.closed;
  const qr = document.querySelector("#qr");
  const svg = window.ZooQR ? ZooQR.toSvg(link, 5) : "";
  qr.innerHTML = svg;
  qr.hidden = !svg;
  document.querySelector("#live-pill").textContent = room.closed ? "Closed" : "Live";
}

function forgetRoom(message) {
  state.roomId = null;
  state.closed = false;
  sessionStorage.removeItem(ROOM_KEY);
  document.querySelector("#play").disabled = true;
  document.querySelector("#close-room").disabled = true;
  document.querySelector("#room-info").textContent = message;
  document.querySelector("#student-link").textContent = message;
  document.querySelector("#qr").hidden = true;
  document.querySelector("#live-pill").textContent = "Idle";
}

document.querySelector("#open-room").addEventListener("click", async () => {
  try {
    const room = await api("/api/rooms", {
      method: "POST",
      body: JSON.stringify({ title: document.querySelector("#title").value }),
    });
    showRoom(room);
    await refreshToken();
    await refreshOverview();
    await refreshSheet();
  } catch (err) {
    document.querySelector("#room-info").textContent = err.message;
  }
});

document.querySelector("#close-room").addEventListener("click", async () => {
  if (!state.roomId) return;
  try {
    await api("/api/rooms/" + state.roomId + "/close", { method: "POST", body: "{}" });
    state.closed = true;
    stopBeacon();
    document.querySelector("#play").disabled = true;
    document.querySelector("#close-room").disabled = true;
    document.querySelector("#live-pill").textContent = "Closed";
    await refreshOverview();
  } catch (err) {
    document.querySelector("#room-info").textContent = err.message;
  }
});

async function restoreRoom() {
  const saved = sessionStorage.getItem(ROOM_KEY);
  if (!saved) return;
  try {
    const room = await api("/api/rooms/" + encodeURIComponent(saved));
    showRoom(room);
  } catch (err) {
    if (err.message === "unknown_room") {
      forgetRoom("That room is no longer on this server. Open a new one.");
      return;
    }
    document.querySelector("#room-info").textContent = err.message;
    return;
  }
  try { await refreshToken(); } catch (err) {
    document.querySelector("#beacon-meta").textContent = err.message;
  }
  try { await refreshOverview(); } catch (_err) { /* overview is lecturer-only */ }
  try { await refreshSheet(); } catch (err) { showSheetError(err); }
}

async function refreshOverview() {
  if (!state.roomId) return;
  const body = await api("/api/rooms/" + state.roomId + "/overview");
  state.closed = !!body.closed;
  document.querySelector("#count-class").textContent = body.counts.in_class;
  document.querySelector("#count-remote").textContent = body.counts.remote;
  document.querySelector("#count-flagged").textContent = body.counts.flagged;
  document.querySelector("#key-fp").textContent = body.key_fingerprint;
  document.querySelector("#salt-fp").textContent = body.salt_fingerprint;
  document.querySelector("#live-pill").textContent = body.closed ? "Closed" : "Live";
  if (body.audio_band) {
    state.band = body.audio_band;
    document.querySelector("#audio-band").value = body.audio_band;
  }
  if (body.proof) {
    state.proof = body.proof;
    document.querySelector("#proof").value = body.proof;
    document.querySelector("#play").disabled = body.closed || body.proof === "qr";
    document.querySelector("#rotating-qr").hidden = body.proof === "sound";
  }
  if (body.token) {
    document.querySelector("#beacon-code").textContent = body.token.code;
    document.querySelector("#beacon-meta").textContent =
      "About " + body.token.seconds_left + "s left in this code";
  }
}

async function refreshToken() {
  if (!state.roomId) return;
  const token = await api("/api/rooms/" + state.roomId + "/token");
  document.querySelector("#beacon-code").textContent = token.code;
  document.querySelector("#rotating-code").textContent = token.code;
  document.querySelector("#beacon-meta").textContent =
    "About " + token.seconds_left + "s left in this code";
  if (state.joinLink && window.ZooQR && state.proof !== "sound") {
    const proofLink = state.joinLink + (state.joinLink.indexOf("?") >= 0 ? "&" : "?") + "code=" + encodeURIComponent(token.code);
    document.querySelector("#rotating-qr").innerHTML = ZooQR.toSvg(proofLink, 4);
  }
  if (token.code !== state.lastCode) {
    state.lastCode = token.code;
    state.payloadHex = token.payload_hex;
    if (state.playing) await startBeacon();
  }
}

function ensureAudio() {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!state.audio) state.audio = new Ctx();
  if (!state.gain) {
    state.gain = state.audio.createGain();
    state.gain.gain.value = Number(document.querySelector("#volume").value) / 100;
    state.analyser = state.audio.createAnalyser();
    state.analyser.fftSize = 2048;
    state.gain.connect(state.analyser);
    state.analyser.connect(state.audio.destination);
  }
  return state.audio;
}

function paintWave() {
  const canvas = document.querySelector("#wave");
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.strokeStyle = "#7ddec0";
  ctx.lineWidth = 2;
  ctx.beginPath();
  if (!state.analyser || !state.playing) {
    ctx.moveTo(0, height / 2);
    ctx.lineTo(width, height / 2);
    ctx.stroke();
    return;
  }
  const data = new Uint8Array(state.analyser.fftSize);
  state.analyser.getByteTimeDomainData(data);
  let energy = 0;
  for (let i = 0; i < data.length; i += 1) {
    const x = (i / data.length) * width;
    const y = (data[i] / 255) * height;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
    const sample = (data[i] - 128) / 128;
    energy += sample * sample;
  }
  ctx.stroke();
  const level = Math.min(100, Math.sqrt(energy / data.length) * 180);
  document.querySelector("#beacon-level").style.width = level + "%";
  document.querySelector("#beacon-level-text").textContent = state.playing
    ? "Beacon is playing. Level " + Math.round(level)
    : "Beacon is off.";
}

function loopWave() {
  paintWave();
  state.raf = requestAnimationFrame(loopWave);
}

async function startBeacon() {
  if (!state.payloadHex || state.closed) return;
  const audio = ensureAudio();
  if (audio.state === "suspended") await audio.resume();
  const bytes = ZooFSK.hexToBytes(state.payloadHex);
  const pcm = ZooFSK.encode(bytes, audio.sampleRate, state.band || "ultrasonic");
  const buffer = audio.createBuffer(1, pcm.length, audio.sampleRate);
  buffer.getChannelData(0).set(pcm);
  if (state.source) {
    try { state.source.stop(); } catch (_err) { /* already stopped */ }
  }
  const source = audio.createBufferSource();
  source.buffer = buffer;
  source.loop = true;
  source.connect(state.gain);
  source.start();
  state.source = source;
  state.playing = true;
  document.querySelector("#stop").disabled = false;
  document.querySelector("#beacon-level-text").textContent = "Beacon is playing.";
  if (!state.raf) loopWave();
}

function stopBeacon() {
  if (state.source) {
    try { state.source.stop(); } catch (_err) { /* already stopped */ }
  }
  state.source = null;
  state.playing = false;
  document.querySelector("#stop").disabled = true;
  document.querySelector("#beacon-level").style.width = "0";
  document.querySelector("#beacon-level-text").textContent = "Beacon is off.";
  paintWave();
}

document.querySelector("#volume").addEventListener("input", () => {
  if (state.gain) state.gain.gain.value = Number(document.querySelector("#volume").value) / 100;
});

document.querySelector("#play").addEventListener("click", async () => {
  try {
    await refreshToken();
    await startBeacon();
  } catch (err) {
    document.querySelector("#beacon-meta").textContent = err.message;
  }
});

document.querySelector("#stop").addEventListener("click", stopBeacon);

document.querySelector("#save-proof").addEventListener("click", async () => {
  if (!state.roomId) return;
  try {
    const saved = await api("/api/rooms/" + state.roomId + "/lesson-settings", {
      method: "POST",
      body: JSON.stringify({
        audio_band: document.querySelector("#audio-band").value,
        proof: document.querySelector("#proof").value,
      }),
    });
    state.band = saved.audio_band;
    state.proof = saved.proof;
    document.querySelector("#proof-state").textContent = "Saved. Phones follow " + saved.audio_band + " / " + saved.proof + ".";
    document.querySelector("#play").disabled = state.closed || saved.proof === "qr";
    document.querySelector("#rotating-qr").hidden = saved.proof === "sound";
  } catch (err) {
    document.querySelector("#proof-state").textContent = err.message;
  }
});

document.querySelector("#test-device").addEventListener("click", async () => {
  const note = document.querySelector("#test-device-status");
  note.textContent = "Listening on this device…";
  try {
    const audio = ensureAudio();
    if (audio.state === "suspended") await audio.resume();
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
    });
    const source = audio.createMediaStreamSource(stream);
    const processor = audio.createScriptProcessor(4096, 1, 1);
    const chunks = [];
    processor.onaudioprocess = (event) => {
      chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      let total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      const keep = audio.sampleRate * 2;
      while (total > keep && chunks.length > 1) total -= chunks.shift().length;
      const merged = new Float32Array(total);
      let offset = 0;
      chunks.forEach((chunk) => { merged.set(chunk, offset); offset += chunk.length; });
      const report = ZooFSK.inspect(merged, audio.sampleRate, state.band || "ultrasonic");
      const heard = report.bytes ? ZooFSK.base32(report.bytes) : "";
      note.textContent = "Test from this device · " + Math.round(report.power0) + " / " + Math.round(report.power1) +
        (heard ? " · heard " + heard : " · listening…");
    };
    source.connect(processor);
    processor.connect(audio.destination);
    window.setTimeout(() => {
      processor.disconnect();
      source.disconnect();
      stream.getTracks().forEach((track) => track.stop());
    }, 4000);
  } catch (err) {
    note.textContent = err.message;
  }
});

document.querySelector("#test-tone").addEventListener("click", async () => {
  const audio = ensureAudio();
  if (audio.state === "suspended") await audio.resume();
  const osc = audio.createOscillator();
  osc.frequency.value = ZooFSK.bandOf(state.band || "ultrasonic").f0;
  osc.connect(state.gain);
  osc.start();
  state.playing = true;
  window.setTimeout(() => {
    try { osc.stop(); } catch (_err) { /* already stopped */ }
    if (!state.source) {
      state.playing = false;
      document.querySelector("#beacon-level-text").textContent = "Test tone finished. Band is 18/19 kHz.";
    }
  }, 450);
});

function renderSheet(records) {
  if (!records.length) {
    document.querySelector("#sheet").innerHTML = "<p class=\"note\">Nobody has checked in.</p>";
    return;
  }
  const rows = records.map((record) => {
    const flags = record.flags && record.flags.length ? record.flags.join(", ") : "";
    const kind = record.mode === "remote" ? "Remote" : "In class";
    const issued = record.attendance_id || record.external_token || "";
    return "<tr><td>" + escapeHtml(record.name || "") + "</td><td>" + escapeHtml(record.student_id) +
      "</td><td class=\"mono\">" + escapeHtml(issued) + "</td><td>" + kind + "</td><td>" + escapeHtml(record.seat_zone) +
      "</td><td>" + escapeHtml(record.confidence) +
      "</td><td class=\"flag\">" + escapeHtml(flags) + "</td><td>" + escapeHtml(record.subnet) + "</td></tr>";
  }).join("");
  document.querySelector("#sheet").innerHTML =
    "<table><thead><tr><th>Name</th><th>Id</th><th>Attendance id</th><th>Mode</th><th>Zone</th><th>Confidence</th><th>Flags</th><th>Subnet</th></tr></thead><tbody>" +
    rows + "</tbody></table>";
}

async function refreshSheet() {
  if (!state.roomId) return;
  const body = await api("/api/rooms/" + state.roomId + "/attendance");
  renderSheet(body.records || []);
  const comments = await api("/api/rooms/" + state.roomId + "/comments");
  const polls = await api("/api/rooms/" + state.roomId + "/polls");
  const homework = await api("/api/rooms/" + state.roomId + "/homework");
  document.querySelector("#comments").innerHTML = (comments.comments || []).length
    ? (comments.comments || []).map((item) => "<p><strong>" + escapeHtml(item.name || item.student_id) + ":</strong> " + escapeHtml(item.text) + "</p>").join("")
    : "None yet.";
  document.querySelector("#polls").innerHTML = (polls.polls || []).map((poll) => {
    return "<p><strong>" + escapeHtml(poll.question) + "</strong> (" + poll.answer_count + " answers)</p><pre>" +
      escapeHtml(JSON.stringify({ counts: poll.counts, by_zone: poll.by_zone, correct_option: poll.correct_option }, null, 2)) + "</pre>";
  }).join("") || "<p class=\"note\">No polls yet.</p>";
  const box = document.querySelector("#homework");
  box.innerHTML = (homework.submissions || []).map((item) => {
    return "<p>" + escapeHtml(item.name || item.student_id) + " · " + item.id +
      " <button type=\"button\" data-hw=\"" + item.id + "\">Review</button></p>";
  }).join("") || "No submissions.";
  box.querySelectorAll("button[data-hw]").forEach((button) => {
    button.addEventListener("click", () => reviewHomework(button.getAttribute("data-hw")));
  });
}

document.querySelector("#refresh").addEventListener("click", () => refreshSheet().catch(showSheetError));

async function download(kind) {
  if (!state.roomId) return;
  const response = await fetch("/api/rooms/" + state.roomId + "/export." + kind, { headers: authHeaders() });
  if (!response.ok) throw new Error("Export failed (" + response.status + ")");
  const blob = await response.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = state.roomId + "-attendance." + kind;
  link.click();
}

document.querySelector("#csv").addEventListener("click", () => download("csv").catch(showSheetError));
document.querySelector("#xlsx").addEventListener("click", () => download("xlsx").catch(showSheetError));

function showSheetError(err) {
  document.querySelector("#sheet").innerHTML = "<p class=\"bad\">" + escapeHtml(err.message) + "</p>";
}

document.querySelector("#add-poll").addEventListener("click", async () => {
  try {
    const options = document.querySelector("#options").value.split("\n").map((line) => line.trim()).filter(Boolean);
    const correct = document.querySelector("#correct").value.trim();
    await api("/api/rooms/" + state.roomId + "/polls", {
      method: "POST",
      body: JSON.stringify({
        question: document.querySelector("#question").value,
        options: options,
        correct_option: correct || null,
      }),
    });
    await refreshSheet();
  } catch (err) {
    document.querySelector("#polls").textContent = err.message;
  }
});

document.querySelector("#summarize").addEventListener("click", async () => {
  const out = document.querySelector("#summary");
  try {
    const file = document.querySelector("#transcript").files[0];
    if (!file) throw new Error("Choose a transcript file first.");
    const transcript = await file.text();
    await api("/api/rooms/" + state.roomId + "/transcript", {
      method: "POST",
      body: JSON.stringify({ transcript: transcript }),
    });
    out.textContent = "Running the agent…";
    const report = await api("/api/rooms/" + state.roomId + "/agent/summary", { method: "POST", body: "{}" });
    out.textContent = JSON.stringify(report, null, 2);
  } catch (err) {
    out.textContent = err.message;
  }
});

function renderAttention(body) {
  document.querySelector("#attention").textContent = JSON.stringify(body, null, 2);
  const zones = ["front-left", "front-right", "middle-left", "middle-right", "back-left", "back-right"];
  const map = body.zones || {};
  document.querySelector("#attention-map").innerHTML = zones.map((zone) => {
    const item = map[zone];
    const level = item ? item.mean_level : 0;
    const tone = Math.round(255 - level * 140);
    return "<div class=\"zone-cell\" style=\"background:rgb(" + tone + "," + (220 - Math.round(level * 80)) + "," + (200 - Math.round(level * 40)) + ")\">" +
      "<strong>" + zone.replace("-", " ") + "</strong><div class=\"note\">" +
      (item ? item.mean_level + " · " + item.samples + " samples" : "No samples") + "</div></div>";
  }).join("");
}

document.querySelector("#sample-attention").addEventListener("click", async () => {
  try {
    const body = await api("/api/rooms/" + state.roomId + "/attention/samples", {
      method: "POST",
      body: JSON.stringify({
        samples: [
          { t_seconds: 120, zone: "front-left", level: 0.8, source: "sample-not-camera" },
          { t_seconds: 600, zone: "back-right", level: 0.3, source: "sample-not-camera" },
        ],
      }),
    });
    renderAttention(body);
  } catch (err) {
    document.querySelector("#attention").textContent = err.message;
  }
});

document.querySelector("#camera-toggle").addEventListener("change", async (event) => {
  const note = document.querySelector("#camera-state");
  const video = document.querySelector("#camera-preview");
  if (!event.target.checked) {
    if (state.camera) state.camera.getTracks().forEach((track) => track.stop());
    state.camera = null;
    video.hidden = true;
    video.srcObject = null;
    note.textContent = "Camera is off. Nothing was uploaded.";
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    event.target.checked = false;
    note.textContent = "This browser has no camera API. The dashboard still works without one.";
    return;
  }
  try {
    state.camera = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    video.srcObject = state.camera;
    video.hidden = false;
    note.textContent = "Preview is local. The video is not uploaded or analyzed.";
  } catch (_err) {
    event.target.checked = false;
    note.textContent = "Camera permission was denied, or this machine has no camera. You can still use every other tab.";
  }
});

async function reviewHomework(id) {
  const out = document.querySelector("#summary");
  try {
    out.textContent = "Running the homework agent…";
    const report = await api("/api/rooms/" + state.roomId + "/agent/homework", {
      method: "POST",
      body: JSON.stringify({ submission_id: id, audience: "lecturer" }),
    });
    out.textContent = JSON.stringify(report, null, 2);
  } catch (err) {
    out.textContent = err.message;
  }
}

document.querySelector("#save-llm").addEventListener("click", async () => {
  try {
    const saved = await api("/api/llm/config", { method: "POST", body: JSON.stringify(llmBody(true)) });
    state.llmConfigLoaded = true;
    state.llmKeyConfigured = !!saved.key_configured;
    document.querySelector("#api-key").value = "";
    document.querySelector("#llm-state").textContent =
      "Saved. Key stored: " + (saved.key_configured ? "yes" : "no") + ". Ready: " + saved.ready + ".";
    document.querySelector("#key-banner").hidden = !!saved.key_configured;
  } catch (err) {
    document.querySelector("#llm-state").textContent = err.message;
  }
});

function providerNeedsKey(provider) {
  return provider !== "ollama" && provider !== "openai_compatible";
}

document.querySelector("#test-llm").addEventListener("click", async () => {
  const box = document.querySelector("#llm-state");
  const provider = document.querySelector("#provider").value;
  const typedKey = document.querySelector("#api-key").value.trim();
  if (!typedKey && providerNeedsKey(provider) && state.llmConfigLoaded && !state.llmKeyConfigured) {
    box.textContent = "Enter an API key first.";
    return;
  }
  box.textContent = "Testing…";
  try {
    const result = await api("/api/llm/test", { method: "POST", body: JSON.stringify(llmBody(true)) });
    if (result.category === "missing_key") {
      state.llmConfigLoaded = true;
      state.llmKeyConfigured = false;
      box.textContent = result.message || "Enter an API key first.";
      return;
    }
    const bits = [
      result.status,
      result.provider,
      result.model,
      result.latency_ms != null ? result.latency_ms + " ms" : "",
      "tool calling: " + result.tool_calling,
      result.category || "",
      result.message || "",
    ].filter(Boolean);
    box.textContent = bits.join(" · ");
    document.querySelector("#api-key").value = "";
  } catch (err) {
    box.textContent = err.message;
  }
});

function llmBody(includeKey) {
  const body = {
    provider: document.querySelector("#provider").value,
    model: document.querySelector("#model").value,
    base_url: document.querySelector("#base-url").value,
  };
  const key = document.querySelector("#api-key").value.trim();
  if (includeKey && key) body.api_key = key;
  return body;
}

async function loadLlm() {
  try {
    const config = await api("/api/llm/config");
    state.llmConfigLoaded = true;
    state.llmKeyConfigured = !!config.key_configured;
    if (config.provider) document.querySelector("#provider").value = config.provider;
    if (config.model) document.querySelector("#model").value = config.model;
    if (config.base_url) document.querySelector("#base-url").value = config.base_url;
    document.querySelector("#llm-state").textContent =
      "Key stored: " + (config.key_configured ? "yes" : "no") + ". Ready: " + config.ready + ".";
    document.querySelector("#key-banner").hidden = !!config.key_configured;
    return true;
  } catch (_err) {
    state.llmConfigLoaded = false;
    state.llmKeyConfigured = false;
    document.querySelector("#llm-state").textContent = "Enter the lecturer token to load model settings.";
    return false;
  }
}

async function loadDiagrams() {
  const body = await api("/api/diagrams");
  const gallery = document.querySelector("#gallery");
  gallery.innerHTML = (body.diagrams || []).map((item) => {
    return "<button type=\"button\" class=\"diagram\" data-src=\"" + escapeHtml(item.src) + "\" data-title=\"" +
      escapeHtml(item.title) + "\"><img src=\"" + escapeHtml(item.src) + "\" alt=\"" + escapeHtml(item.title) +
      "\"><span>" + escapeHtml(item.title) + "</span></button>";
  }).join("") || "<p class=\"note\">No diagrams were found.</p>";
  gallery.querySelectorAll(".diagram").forEach((button) => {
    button.addEventListener("click", () => {
      const dialog = document.querySelector("#lightbox");
      const image = document.querySelector("#lightbox-img");
      image.src = button.getAttribute("data-src");
      image.alt = button.getAttribute("data-title");
      if (dialog.showModal) dialog.showModal();
    });
  });
}

document.querySelector("#lightbox-close").addEventListener("click", () => {
  document.querySelector("#lightbox").close();
});

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
  }[ch]));
}

paintWave();
if (savedToken) {
  loadLlm().then((ok) => { if (ok) { showApp(); return restoreRoom(); } return null; });
}
setInterval(() => {
  if (!state.roomId) return;
  refreshToken().catch(() => {});
  refreshOverview().catch(() => {});
  refreshSheet().catch(() => {});
}, 2000);
