# Software requirements specification

ZooMoodle demo. IEEE-style, shortened to what this assignment needs. This describes the system that the repository implements, plus the classroom checks that are still open.

## 1. Purpose

ZooMoodle is a web tool for one lesson. Students use a phone browser. The lecturer uses a laptop page. The product goal is attendance that is hard to fake and easy to notice when faked, plus an agent that can relate a transcript, polls, and zone-level attention after class. It is not a grading system and it does not connect to Moodle, Zoom, or a personal-information service.

### 1.1 Intended readers

The student who owns the repository, and the lecturer who will run the demo.

## 2. Overall description

### 2.1 Product perspective

The server is a single FastAPI process with an in-memory store. Browsers are static HTML and JavaScript. An optional HTTPS tunnel (cloudflared or similar) makes the phone page a secure context so `getUserMedia` can run. LLM calls go from the server to a provider the lecturer selects.

### 2.2 Users and actors

| Actor | What they do |
| --- | --- |
| Lecturer | Opens a room, plays the beacon, reads the sheet, exports it, runs polls, configures the model, runs the agent. |
| Student | Checks in, picks a seat zone, answers a poll, comments, submits homework, may ask for their own review. |
| Lesson agent | Reads room data through tools and returns a structured report. It is software, not a person. |
| LLM provider | External API. Not part of the university systems. |
| Operator | The same person as the lecturer for this demo: starts the process, the tunnel, and holds the API key. |

### 2.3 Operating environment

Python 3.12 venv, laptop speakers, phone browser, HTTPS for the phone. The lecturer page can stay on `http://127.0.0.1`.

### 2.4 Constraints

- KISS. Phone UI is a web page, not a native app.
- Design and build only what can run in a demo of about ten minutes.
- No integration with Moodle, Zoom, or personal-information systems.
- No face recognition and no stored frames.
- The API key is server-side only.
- Attendance fraud is to be made hard and noticeable, not impossible.

## 3. Functional requirements

| ID | Requirement |
| --- | --- |
| FR-1 | The lecturer, presenting the lecturer token, can open a room with a title. The response includes a student path and no key material. |
| FR-2 | Each room has a salt of at least 16 bytes and a 32-byte key from HKDF-SHA256 over the process master secret, salt, and info `zoomoodle-room-v1`. |
| FR-3 | The server publishes one broadcast token per time window (default 5 seconds). The token is an HMAC-SHA256 over `room id \| window \| nonce`, truncated, plus the nonce. The lecturer page shows the code and can play it as 18/19 kHz FSK. Students cannot fetch the current code from the API. |
| FR-4 | A student starts a challenge, signs `challenge id \| nonce` with a P-256 device key, and submits a check-in. The signature is checked. The challenge expires (default 8 seconds) and cannot be reused. |
| FR-5 | In-class check-in accepts the current window's code, or the previous window's code marked late. An older code is rejected. Each device can redeem a given code only once. Another device may redeem that same broadcast code. |
| FR-6 | Remote check-in does not accept the acoustic code. The server mints a separate external token and stores the row as `remote`. |
| FR-7 | Check-in requires a seat zone: front/middle/back and left/right. |
| FR-8 | The first public key seen for a device id is kept. Records are flagged, not silently dropped, when the same student appears in both modes, one device serves two students, or one student uses two devices. Late tokens and subnet mismatches are flagged. Each row has confidence `high`, `medium`, or `low`. |
| FR-9 | If `ZOOMODLE_ALLOWED_SUBNETS` is set, an in-class client IP in one of those CIDRs is `match`, otherwise `mismatch`. If it is unset, the value is `not_configured` and the row is not punished for that. The IP is taken from `CF-Connecting-IP`, then the first `X-Forwarded-For` hop, then the socket peer. |
| FR-10 | The lecturer can download CSV and XLSX with student id, name, mode, seat zone, UTC time, confidence, flags, subnet, and device id. |
| FR-11 | The lecturer can create a poll with 2 to 6 options and an optional correct option. Students see the question and options only. Results by option and by zone are on the lecturer view. One answer per student per poll. |
| FR-12 | A student can post a comment. The lecturer lists comments with names. The agent does not receive those names. |
| FR-13 | The lecturer can import a transcript as UTF-8 text (JSON or a multipart file), up to 200,000 characters. |
| FR-14 | `POST /api/rooms/{id}/agent/summary` runs the lesson agent (see `docs/09-ai-agent.md`). The report is JSON. If the agent stops without a valid report, the API returns an error and no partial narrative. |
| FR-15 | A student or the lecturer can request a homework review of one submission id. The review includes an anonymized comparison and `not_a_grade: true`. Peer text is not returned as a raw dump; the agent may cite short comparisons. |
| FR-16 | Without a configured provider, model, and key (key optional only for Ollama and a generic compatible endpoint), FR-14 and FR-15 return HTTP 503 with the message that no model was called. |
| FR-17 | The lecturer can store provider, model, base URL, and API key in process memory. `GET /api/llm/config` returns `key_configured` and never the key. A blank key on save leaves the stored key unchanged. `clear_key` removes it. |
| FR-18 | `POST /api/llm/test` sends one short tool-calling request (8 second default timeout). It returns `status: ok` with provider, model, `latency_ms`, and `tool_calling` of `supported` or `not_supported`, or `status: error` with category `invalid_key` (401 or missing key), `no_access` (403 or 404), `rate_limit` (429), `timeout`, `network`, `unknown_provider`, `invalid_request`, or `upstream`. The key is not in the body. A key sent only on this call is not saved. If the tool request returns HTTP 400 and a second call without tools succeeds, the result is `ok` and `tool_calling: not_supported`. |
| FR-19 | Attention samples are stored only when `source` is `sample-not-camera`. The read API includes a disclaimer. No image is accepted. |
| FR-20 | Lecturer routes (create room, current token, attendance, export, poll create, comments list, transcript, summary, lecturer homework review, attention, LLM config and test) require header `X-Lecturer-Token`. Student check-in, poll answer, comment, homework submit, and a student-audience review do not. |

## 4. Non-functional requirements

### 4.1 Security

- Compare tokens and HMAC tags in constant time.
- Device signatures are ECDSA P-256 with SHA-256. The browser sends the raw 64-byte signature. The server converts it to DER to verify.
- Lecturer token and API key are not written to the repo. `.env` is gitignored. `.env.example` has empty secrets.
- Provider keys travel in headers (`Authorization`, `x-api-key`, or `x-goog-api-key`), not in the query string, so they are less likely to land in access logs. Error strings are scrubbed.
- The broadcast code is not on an anonymous GET.

### 4.2 Privacy

- The agent snapshot replaces known display names and student ids in free text. Tool results use pseudonyms.
- Homework comparison is by submission id and token overlap, not by name.
- Attention is a zone aggregate or it is empty. It is an indicator, not a grade.
- The attendance export is for the lecturer. It is not a tool input.

### 4.3 Performance

- A token window of a few seconds, a check-in challenge under about 8 seconds, and an LLM test under about 8 seconds.
- The FSK packet for a 6-byte token is about 1.1 seconds at 20 ms per bit. That fits inside a 5-second window with margin for the previous window.
- The in-memory store is for one class, not a campus deployment.

### 4.4 Usability

- Phone page: large controls, a seat map, one listening button, a typed-code fallback, and a remote button.
- The phone shows an energy indicator around the ultrasonic band so a failed speaker/mic path is visible.
- Lecturer page: the current code in large type, play/stop, the sheet, export, poll, agent, and the connection test.

### 4.5 Availability

- One process. If it stops, the lesson state is gone.
- If the provider is down, attendance still works. The agent returns the connection error or the configuration message. It does not substitute a canned summary.

## 5. Threat model

The goal of the attendance design is to make faking **hard and noticeable**, not impossible.

| Threat | What the attacker does | Mitigation in this demo | Residual |
| --- | --- | --- | --- |
| Forged token | Builds a code without the room key | HMAC under the HKDF room key. A wrong room or a wrong key fails closed. | A leaked master secret forges every room. The secret stays in env or process memory. |
| Replay | Submits a code after the window, or the same device submits it twice | Window plus one grace window. Grace is flagged `late_token`. The pair (code, device) is single-use. | Another device that learned the code during the window can still redeem it once. |
| Relay over a call or a recording | Sends the speaker sound to a remote phone | Tone is at 18 and 19 kHz. A 3400 Hz ×4 lowpass on the VM removed it. Challenge age is a few seconds. | A full-band digital relay (not a phone codec) can still carry it. Not tested on a real call. |
| Screenshot or shared code | Photos the projector or reads the code from a chat | Short lifetime, device binding, challenge signature, latency. API does not hand the code to anonymous clients. | Someone in the room, or a fast photo, can still type the code before it rotates. |
| VPN or tunnel fakes the subnet | Presents an address in the campus range, or hides behind the tunnel | Subnet is a flag, not a pass. Tunnel IP is whatever `CF-Connecting-IP` or the socket sees. Mismatch lowers confidence when the CIDR list is set. | IP checks are weak. A tunnel often makes them useless. Documented, not hidden. |
| Multi-device | One student checks in from two phones, or two students share one phone | Flags `multi_device` and `shared_device`, confidence `low`. The second row is kept so the lecturer sees it. | The lecturer must look. The system does not block the person at the door. |
| Impersonation | A student types someone else's id | The device key is bound on first use and the check-in is signed. A different person on that phone is `shared_device`. There are no university accounts, so a new phone plus a typed id is a new binding. | Identity is whatever the student types, tied to that browser's key. |
| Confused agent | The model invents a poll result or grades the homework | Read-only tools, required data-tool call, schema check, `not_a_grade` must be true, names stripped, missing data must be declared. No key means no call. | A real model can still misread a tool result. Citations are required so the lecturer can check. |
| Key theft from the UI or logs | Student page or a log line reveals the provider key | The key is not in student responses, not in `GET /api/llm/config`, and scrubbed if a provider echoes it. Test-only keys are not saved. | Anyone who can read the server process memory or the owner's `.env` has the key. That is the laptop trust boundary. |

## 6. Requirements trace

Classes and tests that cover these IDs are listed in `docs/08-testing-strategy.md`. The agent loop, prompts, and tool list are specified in `docs/09-ai-agent.md`.
