# ZooMoodle

A simple, LLM-ready web tool for one lesson at a time: attendance that is hard to fake, and a clear picture of which material and which part of the room lost the class.

Individual course project for Introduction to Software Engineering (OOP/OOD), Exercise 2. The problem and the scope are below. A small demo is in this repository. The in-class demo has not been run.

## Problem

Current online tools for teaching are not doing the job. Courses need simpler tools that support learning in the room and that are ready for large language models.

Two gaps drive this project:

- **Attendance is easy to fake.** A student can check in from elsewhere, share a code, or have a classmate do it. The lecturer then has a list, with little sign of who was actually in the room.
- **Feedback is late and coarse.** Lecturers rarely see, during the lesson or just after it, which material lost the class and which area of the room stopped following.

ZooMoodle is a small set of tools that stay inside a single lesson. Students use a phone browser. Summaries and homework review can use an LLM later, without connecting to Moodle, Zoom, or personal-information systems.

## Goal

Design an end-to-end web application a lecturer can run in this class and show in a real demo of about ten minutes. The design stays simple enough to implement. For attendance, the honest aim is to make faking hard and noticeable, not impossible.

## Scope

### In scope

Each lesson is a **Room**. The lecturer opens a room for that lesson only. The room has its own cryptographic key, derived from the lecturer's master secret and a room-specific random salt (for example with HKDF). Attendance, polls, comments, and a later transcript all belong to that room.

- **Attendance (core — must work flawlessly in the demo).**
  - The lecturer's computer broadcasts a short-lived, signed one-time token as a near-ultrasonic signal (about 18–20 kHz).
  - The student's phone receives it through the microphone in the web app (Web Audio API). Audio is chosen over Bluetooth because it works in ordinary browsers on iPhone, Android, Mac, and laptops. Web Bluetooth is not supported on iOS Safari.
  - The token is an HMAC over the room id, a rotating time window, and a nonce. It is valid for only a few seconds. Everyone who hears it may redeem it once; the same device cannot redeem that code again.
  - Further checks: the device is on the university-network subnet; one device is bound to one student (a device key stored on first use); a challenge-response with a latency check resists relaying the sound over a call or a recording (phone and VoIP codecs typically cut these high frequencies).
  - If audio fails, the lecturer can show a short rotating code on screen.
  - A remote participant presses "I'm joining remotely" and receives a separate external token, so the sheet keeps in-class and remote apart.
  - Anomalies are flagged for the lecturer: the same student or device on both lists, two students from one device, or a late token.
  - The lecturer gets an online sheet and an offline export (CSV or XLSX) with the details and a confidence level.
- **Seat zone.** At check-in the student picks a zone on a simple classroom map: front, middle, or back, and left or right.
- **Comments and suggestions**, during the lesson or afterwards. Minimal, and working in the demo.
- **On-the-spot polls.** The lecturer asks a short question about the material just covered. Results can be viewed by seat zone. Minimal, and working in the demo.
- **Attention map (stretch).** One camera facing the class computes an anonymous attention indicator per zone over time (for example head pose with open-source MediaPipe). There is no face recognition and no per-student tracking. Frames are not stored; only zone aggregates are kept. The map is an indicator for the lecturer, not a grade. Designed in full; implemented only as a stretch.
- **AI lesson summary (stretch).** After class the lecturer imports a transcript file from a Zoom or Google Classroom recording. There is no live integration. A tool-calling agent (not one pasted prompt) reads the transcript, polls by zone, comments, and attention aggregates, and returns a structured report: which topic and time, and which zone, lost attention or answered wrongly. Designed in full. The demo runs the loop when a key is set; with no key it stops and says so.
- **LLM homework review (stretch).** The same agent reviews one submission for a student or the lecturer and compares it anonymously with other submissions. It does not assign a grade. Designed in full. Same key rule as the summary.
- **Connection test.** The lecturer chooses a provider (OpenAI, Anthropic, Gemini, xAI, Ollama, or another OpenAI-compatible URL), enters a key, and presses Test connection. The key stays on the server.

### Out of scope

- Integration with Moodle, Zoom, Google Classroom, or any personal-information system. A recording enters only as a file the lecturer imports.
- Storing personal or biometric data, face recognition, and tracking a student on video.
- Native iOS or Android applications. Students use a web app in the phone browser.
- Treating the attention map as a grade, or any feature that cannot be implemented for a short in-class demo.

## Key features

| Priority | Feature | Demo intent |
| --- | --- | --- |
| P0 | Room, plus attendance (ultrasonic token, device binding, remote vs in-class, export with confidence) | Must work flawlessly |
| P1 | Seat zone on a simple map | Part of check-in |
| P1 | Comments and suggestions, live or later | Minimal, working |
| P1 | On-the-spot polls, results by zone | Minimal, working |
| P2 | Lesson-summary agent (transcript, polls, zones) | Designed fully; runs when a key is set |
| P2 | Homework-review agent, anonymized comparison | Designed fully; runs when a key is set |
| P2 | Anonymous attention map by zone | Designed fully; demo stores labeled samples only |

## Requirements and constraints

- It must work in this class and be shown in a real demo of about ten minutes.
- Keep it simple (KISS). Students use a simple web application on a smartphone.
- No integration with Moodle, Zoom, or personal-information systems.
- Design only what can be implemented. The demo may be composed from existing code; writing everything from scratch is not required.
- The same browser flow should run on common phones and laptops.
- The phone page needs HTTPS (microphone). The laptop page can use localhost.
- The lecturer supplies an LLM key later. Until then the agent tells them to configure one and does not invent a report.

## Planned deliverables

- [x] 1. Create a repository and define the problem and the scope in the README.
- [x] 2. Technical tools report, with VM spikes recorded in [docs/02-tools-report.md](docs/02-tools-report.md).
  - [ ] In-class checks (phones, campus Wi-Fi, tunnel). The results table in that report is empty on purpose.
- [x] 3. Statement of Work — [docs/03-SoW.md](docs/03-SoW.md).
- [x] 4. Software requirements — [docs/04-SRS.md](docs/04-SRS.md).
- [x] 5. Use cases — [docs/05-use-cases.md](docs/05-use-cases.md).
- [x] 6. Components — [docs/06-components.md](docs/06-components.md).
- [x] 7. Class and sequence diagrams — [docs/07-design.md](docs/07-design.md).
- [x] 8. Testing strategy — [docs/08-testing-strategy.md](docs/08-testing-strategy.md).
- [x] 9. Demo web application under `app/` and `tests/`.
- [ ] 10. Demo in class. Script only: [docs/10-demo-script.md](docs/10-demo-script.md).
- [x] 11. Draft conclusion of what was built and tested on the VM — [docs/11-conclusions.md](docs/11-conclusions.md).
  - [ ] In-class results. Placeholders in that file are for the owner.

The agent specification is [docs/09-ai-agent.md](docs/09-ai-agent.md). It sits with the design set; it is not a separate item on the original 1–11 list.

## Privacy and security principles

- Each lesson gets its own key, derived from the lecturer's master secret and a fresh salt. Tokens are short-lived HMACs bound to that room, and each device can use a given code only once.
- One student is bound to one device. A device key is stored on first use and identifies that binding afterwards.
- In-class and remote presence use different tokens and stay in separate rows. Odd patterns are flagged for the lecturer to review.
- If an attention map is built, it keeps zone aggregates only: no faces, no identities, and no saved video frames. It is an indicator, not a grade.
- Homework comparison is anonymized. The tool does not take identity data from university personal-information systems.
- The attendance export is for the lecturer of that room and includes a confidence level. The design makes cheating difficult and visible; it does not claim to make cheating impossible.
- The model key is stored in server memory (or in an uncommitted `.env`). It is not returned to the browser, not written into the repo, and not sent to students. The agent sees pseudonyms, not the names on the sheet.

## Documents

| | |
| --- | --- |
| [docs/02-tools-report.md](docs/02-tools-report.md) | Tool choices and VM spikes |
| [docs/03-SoW.md](docs/03-SoW.md) | Statement of work |
| [docs/04-SRS.md](docs/04-SRS.md) | Requirements and threat model |
| [docs/05-use-cases.md](docs/05-use-cases.md) | Use cases |
| [docs/06-components.md](docs/06-components.md) | Components |
| [docs/07-design.md](docs/07-design.md) | Classes and sequences |
| [docs/08-testing-strategy.md](docs/08-testing-strategy.md) | Tests and traceability |
| [docs/09-ai-agent.md](docs/09-ai-agent.md) | Agent prompt, tools, loop, schemas |
| [docs/10-demo-script.md](docs/10-demo-script.md) | Ten-minute script |
| [docs/11-conclusions.md](docs/11-conclusions.md) | Draft conclusions |

## Run the demo

Python 3.12, a virtualenv, no global install. Same commands on macOS and Linux. `python3` may be `python` on some machines.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` if you want a stable master secret and lecturer token. If you leave them empty, the process invents them and prints the lecturer token once. Rooms then die on restart. Do not commit `.env`.

```bash
python -m app.main
```

Lecturer page: `http://127.0.0.1:8000/`. Student phones need HTTPS, because the microphone is blocked on plain HTTP except localhost. On the laptop, in a second terminal, after [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) is installed:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

Open the printed `https://` URL on the phone and add `/student?room=ROOMID` (the lecturer page shows the full link). Keep the beacon on the laptop speakers, not on headphones. The phone page has an energy bar for the 18–19 kHz band; if it stays flat, type the on-screen code.

`.env.example` sets `ZOOMODLE_ALLOWED_SUBNETS=192.114.48.0/21,192.114.56.0/23`. That is the RIPE registration Ariel-segments, measured on Ariel University Wi-Fi on 2026-11-03 (public egress 192.114.52.1). It also matches dorms and the campus VPN, so it only supports the ultrasonic token. Local 10.6.0.0/20 is not usable through the tunnel. cloudflared connects from loopback, and only those peers (`ZOOMODLE_TRUSTED_PROXIES`, default `127.0.0.1/32,::1/128`) may supply `CF-Connecting-IP` or `X-Forwarded-For`.

Tests:

```bash
pytest
```

The VM run of this suite is copied in `docs/11-conclusions.md`. It does not include a live model call. Set the provider and key in the lecturer page, then press Test connection, before expecting a summary.
