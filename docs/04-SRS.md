# Software requirements specification

ZooMoodle, Exercise 2. This specification covers the teaching-tool design, implemented demo, and acceptance checks still to be completed.

## 1. Purpose

Provide a simple phone-based teaching tool, prioritizing automatic attendance and a lecturer spreadsheet. Comments, polls, lesson summaries, and homework review support learning during and after one lesson. Fraud should be harder and visible; the tool is not a grading or university-identity system.

## 2. Overall description

A single FastAPI process serves static lecturer and student pages and keeps room state in memory. The lecturer/operator starts the server and an HTTPS tunnel, manages the lesson, and supplies model configuration. Students check in and submit feedback or homework. An optional external LLM provider serves the lesson agent through read-only tools.

Target environment: Python 3.12 venv, laptop speakers, and current phone browsers. Phones need HTTPS for the microphone. The lecturer should use the public HTTPS origin when generating student links. No Moodle, Zoom, or personal-information integration is required. A transcript file is prepared externally from a recording.

Constraints: a ten-minute classroom demo, simple web controls, one process, server-side provider keys, no face recognition or saved camera frames. Attention is a labeled-sample extension. Comments require connectivity and a running server; disconnected synchronization is outside this demo.

## 3. Functional requirements

| ID | Requirement |
| --- | --- |
| FR-1 | An authenticated lecturer can create a titled room. The response contains a student path, with no salt or key material. |
| FR-2 | Each room uses at least 16 random salt bytes and a 32-byte HKDF-SHA256 key derived from the master secret, salt, and info `zoomoodle-room-v1`. |
| FR-3 | Issue a broadcast code per window (default 5 seconds): truncated HMAC-SHA256 over room id, window, and nonce, accompanied by the nonce. Show it to the lecturer and transmit it as 18/19 kHz FSK. Anonymous clients cannot fetch it. |
| FR-4 | Check-in requires a P-256 signature over `challenge id \| nonce`. Challenges expire after 8 seconds by default and cannot be reused. |
| FR-5 | Accept the current code or the previous window with `late_token`; reject older codes. Each device may redeem a given code once; other devices may use the same broadcast. |
| FR-6 | Remote check-in requires no acoustic code. Generate a separate external token and store the row as `remote`. |
| FR-7 | Require one of six seat zones: front/middle/back × left/right. |
| FR-8 | Keep the first observed public key per device id. Flag late codes, subnet mismatch, both attendance modes, shared devices, and multiple devices per student. Preserve suspicious records for lecturer review and assign confidence `high`, `medium`, or `low`. |
| FR-9 | For in-class rows, a client IP in `ZOOMODLE_ALLOWED_SUBNETS` is `match`, otherwise `mismatch`; an unset list gives `not_configured` without a confidence penalty. Honor forwarded headers only from `ZOOMODLE_TRUSTED_PROXIES`: prefer `CF-Connecting-IP`, then the first `X-Forwarded-For` hop; otherwise use the socket peer. |
| FR-10 | Lecturer-only CSV/XLSX export includes student id, name, mode, zone, UTC time, confidence, flags, subnet, and device id. |
| FR-11 | Lecturers create polls with 2–6 options and an optional correct option from that list. One answer per student per poll. Students cannot see the correct option or counts by option/zone; lecturers can. |
| FR-12 | Students post comments; lecturers see named comments. Agent tools use pseudonyms and redacted text. |
| FR-13 | Import UTF-8 transcript text using JSON or multipart file upload; retain up to 200,000 characters. |
| FR-14 | `POST /api/rooms/{id}/agent/summary` runs the [lesson agent](09-ai-agent.md). Return JSON only after report validation; otherwise return an error without a partial narrative. |
| FR-15 | Students and lecturers can request a review by submission id, including anonymous peer comparison and `not_a_grade: true`. The review should prefer short comparisons to raw peer-text dumps. |
| FR-16 | Without provider, model, and required key, summary/review routes return HTTP 503 stating that no model was called. Keys are optional for Ollama and generic compatible endpoints. |
| FR-17 | Store provider, model, base URL, and key in process memory. `GET /api/llm/config` reports `key_configured`, never the key. A blank key on save keeps the existing key; `clear_key` removes it. |
| FR-18 | Lecturer-only `POST /api/llm/test` checks a short tool call with an 8-second default per-request timeout. Success returns provider, model, latency, and `tool_calling` (`supported`/`not_supported`). Failure categories: `invalid_key` (401/missing key), `no_access` (403/404), `rate_limit` (429), `timeout`, `network`, `unknown_provider`, `invalid_request`, `upstream`. If tools cause HTTP 400 but a plain retry succeeds, report `not_supported`. Never echo the key or save test-only settings. |
| FR-19 | Accept attention samples only with `source=sample-not-camera`; include the disclaimer on reads. No image input. |
| FR-20 | Require `X-Lecturer-Token` for room creation, current code, attendance/export, poll creation, comment/homework lists, transcript, summary, lecturer-audience review, attention, and model configuration/test. Student check-in, poll answers, comments, homework submission, and student-audience review are public demo routes. |

## 4. Non-functional requirements

| Concern | Requirement or limit |
| --- | --- |
| Authentication and crypto | Constant-time lecturer-token/HMAC comparison; ECDSA P-256/SHA-256. Browser signatures are raw 64-byte r\|\|s; the server converts them to DER. See [design](07-design.md) for framing. |
| Secrets | Gitignore `.env`; examples contain empty secrets. Provider keys travel in headers (`Authorization`, `x-api-key`, `x-goog-api-key`), not query strings. Scrub provider errors and omit keys from API responses. |
| Privacy | Redact known display names and ids on the agent path; tool results use pseudonyms. The attendance export is lecturer-only and is not agent input. Unknown names embedded in free text may remain. |
| Performance | The 6-byte FSK payload takes about 1.1 seconds at 20 ms/bit. Current plus previous token windows allow decoding margin. Model calls should not delay attendance; synchronous calls in the current demo need isolation. |
| Usability | Phone: identity, six-zone map, listening, code fallback, remote, poll, comment, homework. Lecturer: room/code, playback, sheet/export, poll, transcript, agent, and model settings. An energy indicator assists audio diagnosis. |
| Availability | Restarting loses all lesson state even with a stable secret. No database or recovery is included. Provider failure must not fabricate an AI result; the current blocking model-call path remains an availability gap. |
| Attention | Zone aggregates are an indicator, not a grade. Demo samples must remain visibly labeled; no camera observation is claimed. |

## 5. Threat model

| Threat | Mitigation | Residual limit |
| --- | --- | --- |
| Forged token | Room-specific HKDF key and HMAC; wrong-room codes fail. | Leaking the master secret compromises all room keys. |
| Replay | Current/grace windows; one redemption per code/device; grace is flagged. | Another device can redeem a shared current code. |
| Acoustic relay | 18/19 kHz signal and expiring challenge. A simulated 3400 Hz ×4 lowpass removed the laboratory signal. | A full-band relay can carry it; no real-call trial has been performed. Challenge age alone does not prove location. |
| Screenshot/shared code | Short lifetime, signed challenge, device flags, and no public current-code route. | Fast sharing can still succeed. |
| Spoofed subnet/VPN | Trust forwarded headers only from configured proxies; subnet mismatch is flagged. | Campus ranges also cover dorms/VPN; IP match does not prove classroom presence. |
| Shared/multiple devices | `shared_device`/`multi_device` flags and low confidence; retain records. | Lecturer judgment is needed. Clearing browser storage creates another device identity. |
| Impersonation | Signed check-in associates the typed id with a browser key; conflicting use is flagged. | No university login verifies who typed the id. |
| Invalid or misleading AI | Read-only tools, a data-tool prerequisite, report checks, citations requested by prompt, and `not_a_grade: true`. | Validation is partial: it cannot prove findings are correct or citations support them. Live-model evaluation remains open. |
| Key disclosure | No key in config/student responses; scrub provider errors; tests do not persist keys. | The laptop's process memory and `.env` remain trusted. |

## 6. Traceability

The [testing strategy](08-testing-strategy.md) maps requirement ids to classes and tests, including gaps. The [agent specification](09-ai-agent.md) defines tools, the loop, and report shapes. Physical and live-model acceptance is recorded through the [demo checklist](10-demo-script.md).
