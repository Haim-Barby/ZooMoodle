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

document.querySelector("#save-token").addEventListener("click", () => {
  sessionStorage.setItem("zoomoodle-lecturer-token", tokenInput.value.trim());
  document.querySelector("#token-state").textContent = "Saved in this browser tab's session only.";
});

const ROOM_KEY = "zoomoodle-lecturer-room";

function showRoom(room) {
  state.roomId = room.id;
  sessionStorage.setItem(ROOM_KEY, room.id);
  const path = room.student_path || ("/student?room=" + room.id);
  const link = new URL(path, window.location.origin).href;
  document.querySelector("#room-info").innerHTML =
    "Room <strong>" + room.id + "</strong>. Student link: <a href=\"" + link + "\">" + link + "</a>";
  document.querySelector("#play").disabled = false;
  if (room.title) document.querySelector("#title").value = room.title;
}

function forgetRoom(message) {
  state.roomId = null;
  sessionStorage.removeItem(ROOM_KEY);
  document.querySelector("#play").disabled = true;
  document.querySelector("#room-info").textContent = message;
}

document.querySelector("#open-room").addEventListener("click", async () => {
  try {
    const room = await api("/api/rooms", {
      method: "POST",
      body: JSON.stringify({ title: document.querySelector("#title").value }),
    });
    showRoom(room);
    await refreshToken();
    await refreshSheet();
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
  try {
    await refreshToken();
  } catch (err) {
    document.querySelector("#beacon-meta").textContent = err.message;
  }
  try {
    await refreshSheet();
  } catch (err) {
    showSheetError(err);
  }
}

async function refreshToken() {
  if (!state.roomId) return;
  const token = await api("/api/rooms/" + state.roomId + "/token");
  document.querySelector("#beacon-code").textContent = token.code;
  document.querySelector("#beacon-meta").textContent =
    "Window " + token.window + " · about " + token.seconds_left + "s left in this code";
  if (token.code !== state.lastCode) {
    state.lastCode = token.code;
    state.payloadHex = token.payload_hex;
    if (state.playing) await startBeacon();
  }
}

async function startBeacon() {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!state.audio) state.audio = new Ctx();
  if (state.audio.state === "suspended") await state.audio.resume();
  const bytes = ZooFSK.hexToBytes(state.payloadHex);
  const pcm = ZooFSK.encode(bytes, state.audio.sampleRate);
  const buffer = state.audio.createBuffer(1, pcm.length, state.audio.sampleRate);
  buffer.getChannelData(0).set(pcm);
  if (state.source) {
    try { state.source.stop(); } catch (_err) { /* already stopped */ }
  }
  const source = state.audio.createBufferSource();
  source.buffer = buffer;
  source.loop = true;
  source.connect(state.audio.destination);
  source.start();
  state.source = source;
  state.playing = true;
  document.querySelector("#stop").disabled = false;
}

document.querySelector("#play").addEventListener("click", async () => {
  try {
    await refreshToken();
    await startBeacon();
  } catch (err) {
    document.querySelector("#beacon-meta").textContent = err.message;
  }
});

document.querySelector("#stop").addEventListener("click", () => {
  if (state.source) {
    try { state.source.stop(); } catch (_err) { /* already stopped */ }
  }
  state.playing = false;
});

function renderSheet(records) {
  if (!records.length) {
    document.querySelector("#sheet").innerHTML = "<p class=\"note\">Nobody has checked in.</p>";
    return;
  }
  const rows = records.map((record) => {
    const flags = record.flags && record.flags.length ? record.flags.join(", ") : "";
    return "<tr><td>" + escapeHtml(record.name || "") + "</td><td>" + escapeHtml(record.student_id) +
      "</td><td>" + record.mode + "</td><td>" + record.seat_zone + "</td><td>" + record.confidence +
      "</td><td class=\"flag\">" + escapeHtml(flags) + "</td><td>" + record.subnet + "</td></tr>";
  }).join("");
  document.querySelector("#sheet").innerHTML =
    "<table><thead><tr><th>Name</th><th>Id</th><th>Mode</th><th>Zone</th><th>Confidence</th><th>Flags</th><th>Subnet</th></tr></thead><tbody>" +
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
    document.querySelector("#attention").textContent = JSON.stringify(body, null, 2);
  } catch (err) {
    document.querySelector("#attention").textContent = err.message;
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
  } catch (_err) {
    document.querySelector("#llm-state").textContent = "Enter the lecturer token to load model settings.";
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
  }[ch]));
}

if (savedToken) loadLlm();
restoreRoom();
setInterval(() => {
  if (!state.roomId) return;
  refreshToken().catch(() => {});
  refreshSheet().catch(() => {});
}, 2000);
