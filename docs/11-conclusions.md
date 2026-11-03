# Conclusions (draft)

Draft for the owner. It records what this repository contains and what was run on the development VM. It does not record an in-class demo. Replace the empty section at the end after the demo. Do not paste VM results in as if they were classroom results.

## What was built

A single-process demo: FastAPI, static lecturer and student pages, HKDF room keys, HMAC broadcast tokens, 18/19 kHz FSK in Python and in the browser, device signatures, anomaly flags, CSV/XLSX export, polls, comments, and a tool-calling lesson agent with a provider adapter (OpenAI, Anthropic, Gemini, xAI, Ollama, or another OpenAI-compatible URL) and a connection test.

Attention is a stub that accepts only samples labeled `sample-not-camera`. MediaPipe is not called by the app.

No Moodle or Zoom integration. The store is memory only.

## What was tested on the VM

Automated suite, command `pytest -v` with pytest 9.2.0 and Python 3.12.3:

```text
25 passed, 1 warning in 0.52s
```

The warning is Starlette saying that `TestClient` still uses `httpx` and would prefer `httpx2`. It did not fail a test.

Passed tests:

- Agent: tool required before the report, homework `not_a_grade`, stop with no invented report, redaction helpers.
- API: lecturer token, check-in plus CSV/XLSX, poll correct option hidden from students, key absent from config and from a 401 connection test, summary blocked with no key, summary path with a scripted provider and a redacted name.
- Attendance: two devices one code, reuse rejected, bad signature, expired challenge, late token, remote row, both-modes, shared device, multi-device.
- Export columns for CSV and XLSX.
- FSK clean decode, small noise, voice-band filter removes the payload, WAV round trip.
- Connection categories: tool call, no tool call, tool request rejected then a plain completion, 401, 403, 404, 429, timeout, network, unknown provider, missing key, Anthropic and Gemini tool JSON.
- HKDF stability and token windows.

Spikes, with outputs in `docs/02-tools-report.md`: FastAPI `/ping`, HKDF/HMAC, CSV/XLSX, FSK including a Node/Python WAV exchange (`010203040506` both ways, Base32 `AEBAGBAFAY`), ggwave protocol 5 round trip of `ZK7Q` (not selected; energy near 7.5–8.2 kHz and 16.5 kHz), PlantUML SVG render, MediaPipe 1.2.0 face landmarker on a blank image (0 faces, 0 matrices) after `libEGL` was installed. The first MediaPipe call failed on a missing `libEGL.so.1`. The first `ggwave` build failed on a missing `Python.h`.

No live LLM request was sent. No phone, no speaker-to-mic trial, no tunnel, and no campus subnet were available on this VM.

## What is explicitly not claimed

- A class demo happened.
- Ultrasonic check-in works on iPhone or Android.
- A real model produced a lesson summary or a homework review.
- Attendance cannot be faked.
- The attention map observed a class.

## In-class results (owner fills this in)

| Item | Result | Notes |
| --- | --- | --- |
| Date and room | | |
| Phones used | | |
| Ultrasonic check-in | | |
| Fallback code | | |
| Remote vs in-class | | |
| Export opened | | |
| Poll by zone | | |
| Test connection (provider, model, latency, tool calling, or error category) | | |
| Lesson agent | | |
| Homework agent | | |
| What to change before a second demo | | |
