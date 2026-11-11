# Testing strategy

Tests are mapped to the classes in `docs/07-design.md` and the requirement ids in `docs/04-SRS.md`. Recorded runs are in `docs/11-conclusions.md`. This document does not claim a classroom pass.

## Layers

| Layer | What it proves | How |
| --- | --- | --- |
| Unit | Roster email confirmation and lockout, barcode windows and liveness, range parsing, check-in rules, anomalies, export bytes, agent control flow, provider error mapping | `pytest` in `tests/`. |
| API | Lecturer token, hidden poll answer, key absent from JSON, 503 without a model, name redaction | `fastapi.testclient` against `create_app`. |
| Security / abuse | Forged helper MAC, stale/replay/wrong-room barcode, `qr_static` / `qr_short`, peer outside range, forged `X-Forwarded-For`, claimed IP/SSID, email lockout | Unit and API tests above. Not a penetration test. |
| Agent | Scripted tool calls, rejected premature `produce_report`, `not_a_grade: false` rejected, names scrubbed, no invented report | `tests/test_agent.py`. |
| Manual, in class | Real phone camera, real hotspot, HTTPS, real provider | `docs/10-demo-script.md` and the empty table in `docs/02-tools-report.md`. Owner only. |

Playwright is not part of this strategy. The phone page is checked by hand during the owner's demo. An optional FSK file-level suite remains for the legacy tab; it is not a speaker-to-phone pass.

## Traceability

| Requirement | Class / module | Test |
| --- | --- | --- |
| FR-2 room key | `KeyManager` | HKDF stability and salt separation |
| FR-3 roster and email | `RoomRoster.verify_email` | `test_roster_presence.py`: groups, English/Hebrew headers, duplicates, no national id or raw email on the public list, email confirmation (including case/whitespace), lockout, hidden secrets |
| FR-4 live barcode | `ScreenQrService` | `test_screen_qr.py`: 2 s live sequence, `qr_static`, `qr_short`, stale, replay, wrong room, gaps, server clock, toggle off |
| FR-5, FR-6 helper and checkmark | `presence`, `network_range` | Range rejects wide/public; real socket peer; forged header; checkmark only after barcode + network; remote has no checkmark |
| FR-7 remote | `AttendanceService` | Remote stored separately, no checkmark |
| FR-8 seat zone | `SeatZone` | Valid zones in check-in paths |
| FR-9 anomalies | `AnomalyDetector`, `DeviceBinding` | Flags and confidence |
| FR-10 export | `ExportService` | CSV/XLSX columns; no national id or raw email |
| FR-11 polls | `Store.add_poll` | Hidden correct option |
| FR-12, privacy | `Store.snapshot`, `redact` | Name redaction tests |
| FR-13 transcript | `Store.set_transcript` | Used by summary tests |
| FR-14, FR-15 agent | `LessonAgent`, `ToolRegistry` | Tool-then-report, `not_a_grade`, stop without inventing |
| FR-16–18 model config | `LLMClient`, API gate | No key ⇒ no invented output; config never returns the key; mocked error categories |
| FR-19 attention | `AttentionAggregator` | Source label required |
| FR-20 lecturer token | API | Token gate tests |

## Exit criteria for the automated suite

- From `demo-web/`, `pytest` exits 0 in a venv created from `requirements.txt`.
- A local run on the owner's Mac reported **103 passed**.
- A failure in roster, barcode, helper-range, export, agent, or connection tests blocks calling the demo "ready on the laptop."
- A green suite does not close physical camera, hotspot, or live-model results.

## Manual acceptance (owner)

Follow `docs/10-demo-script.md`. Record pass or fail in `docs/02-tools-report.md`. Do not treat the 103 automated tests as a phone or hotspot pass.
