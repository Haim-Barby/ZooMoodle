# Statement of work

ZooMoodle, Exercise 2 of Introduction to Software Engineering (OOP/OOD). One student. No team name is stated here because none was provided.

## Objectives

1. Define a teaching tool that makes in-class attendance hard to fake and noticeable when it is faked, and that shows a lecturer which material and which part of the room lost attention.
2. Keep the student side a simple phone web page.
3. Design only what can be implemented, then implement a short demo: room, ultrasonic or fallback attendance, polls, comments, export, and an LLM **agent** (not a single prompt) for the lesson summary and homework review.
4. Leave a 10-minute demo script. The in-class demo itself is the owner's step and is not claimed here.

## Scope

### In scope

- One room per lesson. The room key is HKDF(master secret, room salt).
- Attendance by a rotating HMAC token carried as 18/19 kHz FSK, with an on-screen code if audio fails.
- Remote check-in on a separate token, so the sheet splits in-class and remote.
- Seat zone on a six-cell map.
- Device binding (one P-256 key stored on the phone) and anomaly flags.
- CSV and XLSX export with a confidence level.
- Short polls and comments.
- A lesson agent and a homework-review agent with read-only tools, provider chosen by the lecturer.
- A connection test that classifies provider errors and does not echo the key.
- Attention only as labeled sample aggregates. No camera in this demo.

### Out of scope

- Moodle, Zoom, Google Classroom, or any personal-information system. A transcript is a file.
- Native apps, accounts, and a durable database.
- Face recognition, stored video, per-student tracking, and using attention as a grade.
- Making fraud impossible.

## Deliverables

| PDF item | Artifact | State in this repository |
| --- | --- | --- |
| 1 | README problem and scope | Written |
| 2 | This tools report's companion, `docs/02-tools-report.md` | VM spikes recorded. Classroom table empty. |
| 3 | `docs/03-SoW.md` | This document |
| 4 | `docs/04-SRS.md` | Written |
| 5 | `docs/05-use-cases.md` | Written |
| 6 | `docs/06-components.md` | Written, with a component diagram |
| 7 | `docs/07-design.md` | Class and sequence diagrams |
| 8 | `docs/08-testing-strategy.md` | Written |
| 9 | `app/`, `tests/`, `requirements.txt` | Demo and pytest |
| 10 | `docs/10-demo-script.md` | Script only. Demo not given. |
| 11 | `docs/11-conclusions.md` | Draft. Classroom placeholders empty. |
| Agent spec | `docs/09-ai-agent.md` | Written. Sits between the testing strategy and the demo script. |

## Milestones

No calendar dates were set. Order of work, all dates TBD:

1. Problem and scope in the README. Done in the repository.
2. Tool spikes and this statement of work. VM part done.
3. SRS, use cases, components, design, testing strategy, agent spec.
4. Demo implementation and automated tests.
5. Owner: campus tunnel, real phones, LLM key, 10-minute demo.
6. Owner: fill the classroom tables and replace the draft conclusion.

## Assumptions

- The lecturer runs the server on a laptop and opens an HTTPS tunnel so phones can use the microphone.
- Students have a current mobile browser. The same origin serves both pages.
- One process, in memory, is enough for a single lesson demo. A restart clears rooms.
- The lecturer supplies an API key later, for whichever provider they choose. Until then the agent endpoints fail with a configuration message.
- "Single-use" for a broadcast token means once per device. Every phone that hears the same tone may redeem it during the window. A globally single-use tone could admit only one student.
- The university subnet CIDR is not known here. The check is off until `ZOOMODLE_ALLOWED_SUBNETS` is set.
- Names stay on the lecturer's sheet. The agent sees pseudonyms (`P-` plus a hash prefix) and text with known names redacted.

## Risks

| Risk | What it does to the demo | Mitigation in this design |
| --- | --- | --- |
| Laptop speakers or phone mics drop 18–19 kHz | In-class audio check-in fails | On-screen rotating code. Energy bar on the phone so the failure is visible. |
| A student reads the code off the projector or a photo | They can submit the current code from outside the room | Short window, single use per device, challenge latency, anomaly flags. Honest limit: a fast photo can still work. |
| Voice call or recording relays the tone | A remote student checks in as in-class | FSK is above the usual voice band. A 3400 Hz lowpass removed the lab signal. Not yet tried on a real call. |
| Tunnel hides the campus IP | Subnet check does not see the university range | The check is reported, not required. Document the header the server reads (`CF-Connecting-IP`, then `X-Forwarded-For`). |
| Model ignores tools or invents counts | The summary looks confident and is wrong | The loop requires a data tool before `produce_report`, checks the JSON shape, and stops with an error instead of a made-up report. |
| Key leaks through logs or the student page | Provider account is exposed | Key is a header only, scrubbed from error text, never returned by GET, never written to `.env` by the app. |
| Process restart | Rooms and the in-memory key disappear | Set `ZOOMODLE_MASTER_SECRET`. The UI token is printed once if it was generated. |

## Acceptance criteria

- A lecturer with the lecturer token can open a room, show a rotating code, play the tone, see in-class and remote rows with flags, and download CSV and XLSX.
- A student page can bind a device, pick a seat zone, check in with a code or as remote, answer one poll, comment, and submit homework.
- A second use of the same code from the same device is rejected. Two devices can use one broadcast code.
- Export and the token endpoint reject a missing lecturer token.
- With no LLM key, summary and homework review return a clear configuration error and do not return a summary.
- With a scripted tool-calling provider, the agent returns a validated report and does not pass stored names through.
- `POST /api/llm/test` returns `ok` with latency and a tool-calling flag, or one of the error categories, and the JSON does not contain the key.
- The classroom demo and the owner's result tables are still open.
