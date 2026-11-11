# ZooMoodle

A simple web teaching tool for one lesson: automatic attendance with anomaly flags, student feedback, polls, and LLM-assisted lesson and homework review.

Individual project for Introduction to Software Engineering (OOP/OOD), Exercise 2. Deadline: 25 November 2026. A demo and the design documents are included. Real-phone camera and hotspot trials, live-model validation, and the in-class demo remain open.

## Problem and scope

Attendance codes can be shared, and lecturers receive feedback too late to see which material confused the class. ZooMoodle aims to make in-class presence harder to fake and more visible, and to connect feedback to lesson topics and seat zones.

Students use a phone browser; the lecturer uses a laptop. The goal is an implementable end-to-end design and a real classroom demo of about ten minutes. Attendance is the main feature. The system does not claim to prevent all fraud.

Each lesson is a **Room**, with its own derived cryptographic key and its own attendance, polls, comments, homework, and transcript.

**In-class attendance** is a combined check:

1. **Roster.** The lecturer imports a class list. The student picks a name and confirms with that person's email. The server checks a salted HMAC of the email and does not store a national id. The public name list does not show the email.
2. **Live barcode.** The lecturer screen shows a flickering, video-like barcode: a signed QR that changes about every 250 ms, with a border that shimmers about 20 times a second from a server seed. The phone must hold the camera on that live pattern for about two seconds and collect at least five distinct frames. A still photo or screenshot is rejected (`qr_static`); a shorter capture is rejected (`qr_short`). Each code is room-bound, HMAC-signed, single-use, and checked for freshness against the server clock (6 seconds at receipt).
3. **Network verifier.** The phone must open the lecturer's local helper from an address inside the lecturer-entered client range (no wider than /24). The helper reads the real socket peer; a claimed IP or Wi-Fi name is not enough. Double-click launchers start the helper after a saved setup. They do not fully provision a hotspot.
4. **Admission.** Only then does the lecturer sheet show a checkmark and the phone shows a welcome (`ברוך הבא`) with that name.

A classmate who live-streams the lecturer screen may still pass liveness; the network check covers a student who is not on the lecturer's network. An older ultrasonic 18/19 kHz FSK beacon and typed on-screen code remain in the demo as an optional path; they are not required for the checkmark and have not been verified on real speakers or a phone. Physical camera scanning and a real hotspot are also unverified. Hotspot setup is in **Lecturer hotspot** below.

| Also in the demo | Scope |
| --- | --- |
| Attendance sheet | Separate in-class and remote rows, roster checkmarks, six seat zones, confidence, and anomaly flags. Lecturer-only CSV/XLSX export. |
| Comments | During or after the lesson while the server is up. Offline sync is not implemented. |
| Instant polls | Two to six options, an optional correct answer, one answer per student, and lecturer results by zone. |
| Lesson summary | Import a UTF-8 transcript; a tool-calling agent combines it with polls, comments, and zone aggregates. Transcription is external. |
| Homework review | The same agent compares a submission anonymously with peers. It does not assign grades. |
| Model connection | Lecturer-selected provider, model, optional base URL, and server-side key; separate Save and Test actions. |
| Attention map | Labeled sample aggregates only. A live camera pipeline is outside the demo. |

The LLM code paths exist, but successful real-model output has not been validated. Without a configured model, the app returns an error instead of a fabricated report.

Out of scope: Moodle/Zoom/personal-information integration, native mobile apps, university accounts, a durable database, face recognition, and stored classroom video. The agent uses pseudonyms and best-effort redaction.

## Assignment deliverables

Status distinguishes a written artifact from completed validation.

| Item | Artifact | Status |
| --- | --- | --- |
| 1. Problem and scope | This README | Written |
| 2. Tools report | [Tools and recorded experiments](docs/02-tools-report.md) | VM and Mac tests recorded; physical camera, hotspot, and live-provider checks pending |
| 3. SoW | [Statement of work](docs/03-SoW.md) | Written |
| 4. SRS | [Requirements and threat model](docs/04-SRS.md) | Written |
| 5. Use cases | [Stories and acceptance criteria](docs/05-use-cases.md) | Written |
| 6. Components | [Components and interfaces](docs/06-components.md) | Written |
| 7. Design | [Class and sequence diagrams](docs/07-design.md) | Written |
| 8. Test strategy | [Tests and traceability](docs/08-testing-strategy.md) | Written; 103 automated tests passed on the owner's Mac |
| 9. Demo app | `demo-web/` (`app/`, `tests/`, `requirements.txt`) | Implemented; physical camera and hotspot trials remain, see [conclusions](docs/11-conclusions.md) |
| 10. Classroom demo | [Ten-minute script](docs/10-demo-script.md) | Not performed |
| 11. Conclusions | [Results and remaining work](docs/11-conclusions.md) | Draft; classroom results pending |

The assignment deliverables are the eleven items above. Hotspot setup and Render steps are in the sections below; design details are in [the design document](docs/07-design.md).

## Run the demo

Use Python 3.12 and a virtual environment. The app lives in `demo-web/`:

```bash
cd demo-web
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `ZOOMODLE_MASTER_SECRET` and `ZOOMODLE_LECTURER_TOKEN` in `.env`. If empty, the process generates them and prints the lecturer token once. The store is in memory: restarting loses rooms even with a stable secret. Never commit `.env`.

```bash
python -m app.main
```

The lecturer page is at `http://127.0.0.1:8000/`. Phones need HTTPS for the camera (and for the optional microphone path). After [installing cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/), run `cloudflared tunnel --url http://127.0.0.1:8000` in a second terminal. Open the lecturer page through the printed HTTPS URL so student links use that origin. A localhost link must have its origin replaced before sharing.

The flickering barcode is on the lecturer screen. The local verifier runs on the laptop, on the hotspot network, not through the tunnel and not on Render. Camera scanning on a real phone and a real hotspot have not been tested.

The optional campus-subnet list in `.env.example` is supporting evidence only; it is not the hotspot range check. The lecturer enters the verifier address and the phone range on the lecturer page. Forwarded IP headers are accepted only from `ZOOMODLE_TRUSTED_PROXIES` (default loopback).

From `demo-web/`, run `pytest`. A local run on the owner's Mac reported **103 passed**. That suite does not replace a physical camera or hotspot trial.

For AI, enter provider, model, and key, press **Save settings**, then **Test connection**. Test alone does not save the key. Supported adapters: OpenAI, Anthropic, Gemini, xAI, Ollama, and other OpenAI-compatible endpoints. Keys stay in server memory or the uncommitted environment file and are omitted from configuration responses.

## Lecturer hotspot

This is not fully automatic. On the lecturer page, enter the network name, the verifier address, and the phone address range (no wider than /24). Windows Mobile Hotspot is often `192.168.137.1` and `192.168.137.0/24`. macOS Internet Sharing is often `192.168.2.1` and `192.168.2.0/24`. Pair the helper and copy the one-time key into `~/.zoomoodle/lecturer-setup.json` (mode `0600`), together with the server, room, bind address, and range.

Then double-click `demo-web/launch/macos/ZooMoodle Lecturer.command` or `demo-web/launch/windows/ZooMoodle Lecturer.bat`. That starts the local verifier only. On macOS, turn on Internet Sharing yourself (Ethernet or another upstream shared **to** Wi-Fi) in System Settings → General → Sharing. On Windows, the launcher may try `NetworkOperatorTetheringManager`; otherwise open Mobile Hotspot settings.

Show two QR codes: one only to join the Wi-Fi, and one only to open the student page. The Wi-Fi password is used to draw the Wi-Fi QR and is not sent to the server. The helper does not bind `0.0.0.0` and checks the real socket peer. Someone already on the hotspot can still relay a challenge.

## Deploy on Render

A free Web Service Blueprint is in `demo-web/render.yaml` (`rootDir: demo-web`). In the Render dashboard choose **New** → **Blueprint**, select this repository, and apply. The service builds with `pip install -r requirements.txt` and serves HTTPS. `autoDeploy` follows `main`.

`ZOOMODLE_MASTER_SECRET` and `ZOOMODLE_LECTURER_TOKEN` are generated by Render and live in the service Environment, not in git. Copy the token into the lecturer page. A few minutes before class, open `/api/health` and leave a tab open — the free plan spins down after about 15 minutes, and a restart or spin-down erases in-memory rooms. Export the attendance sheet before you finish.

The local verifier and the hotspot run on the laptop, not on Render. Student links must use the Render HTTPS origin so the phone camera is allowed.
