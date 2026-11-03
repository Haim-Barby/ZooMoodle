# ZooMoodle

A simple web teaching tool for one lesson: automatic attendance with anomaly flags, student feedback, polls, and LLM-assisted lesson and homework review.

Individual project for Introduction to Software Engineering (OOP/OOD), Exercise 2. A demo and the design documents are included. Real-phone trials, live model validation, and the in-class demo remain open.

## Problem and goal

Attendance codes can be shared, and lecturers receive feedback too late to see which material confused the class. ZooMoodle aims to make attendance fraud harder and more visible, and to connect feedback to lesson topics and seat zones.

Students use a phone browser; the lecturer uses a laptop. The goal is an implementable end-to-end design and a real classroom demo of about ten minutes. Attendance is the main feature. The system does not claim to prevent all fraud.

## Scope

Each lesson is a **Room**, with its own derived cryptographic key and its own attendance, polls, comments, homework, and transcript.

| Feature | Design and demo scope |
| --- | --- |
| Automatic attendance | The laptop broadcasts a short-lived HMAC token as 18/19 kHz FSK. The phone decodes it through its microphone and signs a device challenge. A rotating on-screen code is the fallback. Physical speaker-to-phone reception is unverified. |
| Attendance sheet | Separate in-class and remote rows, six seat zones, confidence, and flags for late codes, subnet mismatch, shared devices, multiple devices, and both modes. Lecturer-only CSV/XLSX export. |
| Comments and suggestions | During or after the lesson while the server is available. Disconnected composition and later synchronization are not implemented. |
| Instant polls | Two to six options, an optional correct answer, one answer per student, and lecturer results by zone. |
| Lesson summary | Import a UTF-8 transcript from a recording; a tool-calling agent combines it with polls, comments, and available zone aggregates. Transcription itself is external to this demo. |
| Homework review | The same agent reviews a submission and compares it anonymously with peers. It does not assign grades. |
| Model connection | Lecturer-selected provider, model, optional base URL, and server-side key; separate Save settings and Test connection actions. |
| Attention map — optional extension | The demo accepts labeled sample aggregates only. A live camera pipeline is outside the demo scope. |

The assignment includes both LLM features. Their code paths exist, but successful real-model output has not been validated. Without a configured model, the app returns an error instead of a fabricated report.

Attendance safeguards include a token valid for the current window and one grace window, one redemption per code per device, device signatures, and an optional campus-subnet signal. A fast shared photo or full-band relay can still work; see the [SRS threat model](docs/04-SRS.md#5-threat-model).

Out of scope: Moodle/Zoom/personal-information integration, native mobile apps, university accounts, a durable database, face recognition, and stored classroom video. Names and student ids are stored for the lecturer; the agent uses pseudonyms and best-effort redaction.

## Assignment deliverables

Status distinguishes a written artifact from completed validation.

| Item | Artifact | Status |
| --- | --- | --- |
| 1. Problem and scope | This README | Written |
| 2. Tools report | [Tools and recorded experiments](docs/02-tools-report.md) | VM experiments recorded; physical and live-provider checks pending |
| 3. SoW | [Statement of work](docs/03-SoW.md) | Written |
| 4. SRS | [Requirements and threat model](docs/04-SRS.md) | Written |
| 5. Use cases | [Stories and acceptance criteria](docs/05-use-cases.md) | Written |
| 6. Components | [Components and interfaces](docs/06-components.md) | Written |
| 7. Design | [Class and sequence diagrams](docs/07-design.md) | Present; class detail can be refined |
| 8. Test strategy | [Tests and traceability](docs/08-testing-strategy.md) | Written; coverage gaps identified |
| 9. Demo app | `app/`, `tests/`, `requirements.txt` | Implemented; known issues remain, see [conclusions](docs/11-conclusions.md) |
| 10. Classroom demo | [Ten-minute script](docs/10-demo-script.md) | Not performed |
| 11. Conclusions | [Results and remaining work](docs/11-conclusions.md) | Draft; classroom results pending |

The [agent specification](docs/09-ai-agent.md) supports the design; it is not a twelfth assignment deliverable.

## Run the demo

Use Python 3.12 and a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `ZOOMODLE_MASTER_SECRET` and `ZOOMODLE_LECTURER_TOKEN` in `.env`. If empty, the process generates them and prints the lecturer token once. The store is in memory: restarting loses rooms even with a stable secret. Never commit `.env`.

```bash
python -m app.main
```

The lecturer page is at `http://127.0.0.1:8000/`. Phones need HTTPS for microphone access. After [installing cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/), run in a second terminal:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

Open the lecturer page through the printed HTTPS URL so its generated student links also use that origin. A link generated from localhost points to localhost on the phone and must have its origin replaced. Keep the beacon on laptop speakers. If reception fails, use the on-screen code and record that fallback separately from an acoustic success.

`.env.example` configures Ariel public ranges `192.114.48.0/21,192.114.56.0/23`. The recorded egress was `192.114.52.1` on 2026-11-03. These ranges also cover dorms/VPN, so a match is supporting evidence only. Through a tunnel, private Wi-Fi addresses are not visible. Forwarded IP headers are accepted only from `ZOOMODLE_TRUSTED_PROXIES`, default loopback.

Tests:

```bash
pytest
```

For AI, enter provider, model, and key, press **Save settings**, then **Test connection**. Test alone does not save the key and clears its input. Supported adapters: OpenAI, Anthropic, Gemini, xAI, Ollama, and other OpenAI-compatible endpoints. Keys stay in server memory or the uncommitted environment file and are omitted from configuration responses.
