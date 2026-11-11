# Software requirements specification

ZooMoodle, Exercise 2. This specification covers the teaching-tool design, the implemented demo, and acceptance checks still to be completed.

## 1. Purpose

Provide a simple phone-based teaching tool, prioritizing automatic attendance and a lecturer spreadsheet. Comments, polls, lesson summaries, and homework review support learning during and after one lesson. Fraud should be harder and visible; the tool is not a grading or university-identity system.

## 2. Overall description

A single FastAPI process serves static lecturer and student pages and keeps room state in memory. The lecturer starts the server (locally or on Render), an HTTPS origin for phones, and — for the roster checkmark — a local presence helper on the lecturer hotspot. Students check in and submit feedback or homework. An optional external LLM provider serves the lesson agent through read-only tools.

Target environment: Python 3.12, a lecturer laptop, and current phone browsers. Phones need HTTPS for the camera. No Moodle, Zoom, or personal-information integration is required. A transcript file is prepared externally.

Constraints: a ten-minute classroom demo, simple web controls, one process, server-side provider keys, no face recognition or saved camera frames. Attention is a labeled-sample extension. Comments require a running server.

## 3. Functional requirements

| ID | Requirement |
| --- | --- |
| FR-1 | An authenticated lecturer can create a titled room. The response contains a student path, with no salt or key material. |
| FR-2 | Each room uses at least 16 random salt bytes and a 32-byte HKDF-SHA256 key derived from the master secret, salt, and info `zoomoodle-room-v1`. |
| FR-3 | The lecturer can import a class CSV and select a group. The server stores names, group, a per-person salt, and a salted HMAC of the student's email. It does not store a national id. The student picks a name from that list (no free typing of a new name) and confirms with that email. Repeated failures lock out. The public name list does not show the email. |
| FR-4 | The lecturer page shows a flickering video-like barcode: a signed QR that changes about every 250 ms, and a border that shimmers about 20 times a second from a server-issued seed. The phone must hold the camera on it for about two seconds and collect at least five distinct frames. Reject a still photo or repeated frame (`qr_static`) and a capture shorter than two seconds (`qr_short`). Each frame is room-bound, HMAC-signed, single-use per student, and fresh for 6 seconds by the **server** clock at receipt. Reject a wrong-room, replayed, or largely gapped sequence. The lecturer may turn the barcode off; then the checkmark uses the network verifier only. |
| FR-5 | The lecturer enters a network name, verifier address, and client range no wider than /24. Public ranges and a bind of `0.0.0.0` are rejected. The helper accepts a connection only on the bound address and only if the socket peer is inside the range. It ignores `X-Forwarded-For` and a client-claimed IP or Wi-Fi name. |
| FR-6 | The roster checkmark and the welcome (`ברוך הבא` + name) appear only after FR-3, FR-4 (unless toggled off), and FR-5 all succeed for the same student session. Closing the room revokes the helper and the session. |
| FR-7 | Remote check-in is stored as `remote`, with no roster checkmark and no barcode or helper requirement. |
| FR-8 | Require one of six seat zones: front/middle/back × left/right. |
| FR-9 | Flag late or reused optional-path codes, subnet mismatch, both attendance modes, shared devices, and multiple devices. Keep suspicious records and assign confidence `high`, `medium`, or `low`. A campus-subnet list, if configured, is a flag only — not the FR-5 admission gate. Honor forwarded headers only from `ZOOMODLE_TRUSTED_PROXIES`. |
| FR-10 | Lecturer-only CSV/XLSX export includes the stored attendance fields (name, mode, zone, UTC time, confidence, flags, and device or roster identifiers as stored). It does not include a national id or the raw email. The export is not model input. |
| FR-11 | Lecturers create polls with 2–6 options and an optional correct option from that list. One answer per student per poll. Students cannot see the correct option or counts; lecturers can, including by zone. |
| FR-12 | Students post comments; lecturers see named comments. Agent tools use pseudonyms and redacted text. |
| FR-13 | Import UTF-8 transcript text (JSON or file); retain up to 200,000 characters. |
| FR-14 | `POST /api/rooms/{id}/agent/summary` runs the lesson agent. Return JSON only after report validation; otherwise return an error without a partial narrative. |
| FR-15 | Students and lecturers can request a review by submission id, including anonymous peer comparison and `not_a_grade: true`. |
| FR-16 | Without provider, model, and required key, summary/review routes return HTTP 503 stating that no model was called. Keys are optional for Ollama and generic compatible endpoints. |
| FR-17 | Store provider, model, base URL, and key in process memory. `GET /api/llm/config` reports `key_configured`, never the key. A blank key on save keeps the existing key; `clear_key` removes it. |
| FR-18 | Lecturer-only `POST /api/llm/test` runs a short tool call (8-second default timeout). Success returns provider, model, latency, and `tool_calling`. Failure categories follow the existing API (`invalid_key`, `no_access`, `rate_limit`, `timeout`, `network`, `unknown_provider`, `invalid_request`, `upstream`). Never echo the key or save test-only settings. |
| FR-19 | Accept attention samples only with `source=sample-not-camera`. No image input. |
| FR-20 | Require `X-Lecturer-Token` for room creation, roster/presence settings, attendance/export, current barcode, poll creation, comment/homework lists, transcript, summary, lecturer-audience review, attention, and model configuration/test. Student identify, barcode submit, helper finish, poll answers, comments, homework, and student-audience review are public demo routes. |

An optional ultrasonic FSK beacon and typed code remain in the demo. They are not required for FR-6.

## 4. Non-functional requirements

| Concern | Requirement or limit |
| --- | --- |
| Authentication and crypto | Constant-time lecturer-token and HMAC comparison. Barcode freshness uses server time, not the phone clock. |
| Secrets | Gitignore `.env`. Helper key in a mode-`0600` setup file. The Wi-Fi password is used only to draw a local Wi-Fi QR and is not sent to the server. Omit keys from API responses. |
| Privacy | No national id in the roster store or the export. Email is used only for confirmation (salted HMAC); the public list and the export do not include the raw email. Redact known names on the agent path; tool results use pseudonyms. |
| Usability | Phone: name list, email confirmation, two-second camera scan, then the network step, plus poll, comment, and homework. Lecturer: room, roster import, flickering barcode, network fields, sheet/export, poll, transcript, agent, and model settings. |
| Availability | Restarting loses all lesson state. Provider failure must not fabricate an AI result. |
| Attention | Zone aggregates are an indicator, not a grade. No camera observation is claimed. |

## 5. Threat model

| Threat | Mitigation | Residual limit |
| --- | --- | --- |
| Forged barcode or wrong room | Room HKDF key and per-frame HMAC. | A leaked master secret compromises room keys. |
| Replay or stale frame | Server-clock freshness (6 s); single-use per student. | A very fast live relay can still present fresh frames. |
| Screenshot or shared photo | Liveness: ≥5 distinct frames over ~2 s; `qr_static` / `qr_short`. | A live video relay from a classmate may pass liveness. |
| Student not in the room | Local helper checks the real socket peer in the entered range. | Someone already on the hotspot can relay a challenge. |
| Spoofed IP, SSID, or proxy header | Ignore claimed IP/SSID and `X-Forwarded-For`; reject public or > /24 ranges and bind `0.0.0.0`. | OS routing issues if another network uses the same subnet. |
| Impersonation | Name must come from the imported list; email checked with a salted HMAC; lockout. | No university login; a student who knows a peer's email can still try that name. |
| Invalid or misleading AI | Read-only tools, a data-tool prerequisite, report checks, `not_a_grade: true`. | Validation cannot prove findings are correct. Live-model evaluation remains open. |
| Key disclosure | No key in config/student responses; scrub provider errors. | Process memory, `.env`, and the helper setup file remain trusted. |

## 6. Traceability

The [testing strategy](08-testing-strategy.md) maps requirement ids to classes and tests. Agent loop details are in the [design document](07-design.md). Physical acceptance is recorded through the [demo checklist](10-demo-script.md).
