# Design

Class and sequence diagrams for the demo. Sources and SVG exports live in `docs/diagrams/` (`classes`, `seq-checkin`, and `components` in the components document). How to run the demo, start the hotspot helper, and deploy on Render is in the [README](../README.md). Agent, hotspot, and deploy essentials used by the design are summarized here.

## Design rules that the code follows

- The roster checkmark requires, in order: a name from the imported list and a correct email confirmation, a two-second live barcode sequence (unless the lecturer turned that step off), and a helper observation from a real socket peer inside the configured range.
- Barcode frames are single-use per student, room-bound, and judged at receipt by the server clock (6 seconds). Liveness needs at least five distinct frames spanning about two seconds. A still photo is `qr_static`; a short capture is `qr_short`.
- The helper does not trust a body field `ssid` or `ip`, `X-Forwarded-For`, or a public or wider-than-/24 range. It will not bind `0.0.0.0`.
- Names exist on attendance, comments, and homework records. `Store.snapshot` is the only door into the agent, and it redacts them. A national id is not stored. The email is kept only as a salted HMAC for confirmation; the raw address is not shown on the public list or the export.
- `produce_report` is the only way the agent finishes. There is no offline stub on the HTTP API.
- Attention samples must declare `source=sample-not-camera`.
- An optional FSK beacon and typed code remain in the UI. They are not required for the checkmark.

## Classes

![Classes](diagrams/classes.svg)

`SeatZone` is a checked value, not a picture of the furniture. `Poll`, `Comment`, and `HomeworkSubmission` are records on the room. `SummaryService` and `HomeworkReviewService` pick a task and call `LessonAgent`. `LLMClient` hides which provider is configured.

| Item | Value |
| --- | --- |
| Room key | HKDF-SHA256, 32 bytes, salt = room salt, info = `zoomoodle-room-v1` |
| Email confirmation | Per-person salt and HMAC of the normalized email under the master secret; national id not stored |
| Barcode frame | Signed QR about every 250 ms; shimmer seed at about 20 Hz |
| Liveness | ~2 s hold, ≥5 distinct frames; `qr_static` / `qr_short` |
| Freshness | 6 s at receipt, server clock only |
| Helper range | Lecturer-entered CIDR, no wider than /24; real socket peer |
| Typical defaults | Windows `192.168.137.1` + `192.168.137.0/24`; macOS `192.168.2.1` + `192.168.2.0/24` |

## Sequences

### In-class check-in

![In-class check-in](diagrams/seq-checkin.svg)

Name and email confirmation create a student session without a checkmark. The phone then submits the two-second live frame batch. Only after a successful helper `/prove` on the hotspot does the server mark the roster and return the welcome. Closing the room revokes both the helper and the session.

### Other sequences

Remote check-in, polls, export, the agent loop, and the connection test follow the same services and are not given separate diagram files. Remote admission still creates no roster checkmark. Export remains lecturer-only and is not model input. The agent loop still requires a data tool before `produce_report` and rejects a fabricated or ungraded homework report (`not_a_grade` must be `true`).

## Hotspot and launchers (essentials)

This is not fully automatic provisioning. After `~/.zoomoodle/lecturer-setup.json` holds the server, room, bind address, and helper key, a double-click starts the helper only. On macOS, Internet Sharing stays a manual System Settings step (Ethernet or another upstream shared **to** Wi-Fi). On Windows, the launcher may try `NetworkOperatorTetheringManager` and otherwise opens Mobile Hotspot settings. Two QR codes: a Wi-Fi QR that only joins the network, and a join QR that only opens the student link. The Wi-Fi password is not stored on the server. Someone already on the hotspot can still relay a challenge. Physical Mac/Windows/phone trials are open.

## Lesson agent (essentials)

One tool-calling agent supports `lesson_summary` and `homework_review`. It never assigns a grade. Tools are read-only (`get_transcript_segment`, `get_poll_results`, `get_attention_by_zone`, `list_comments`, homework get/compare). The loop may run up to `ZOOMODLE_AGENT_MAX_STEPS` (default 8). A report is accepted only after a data tool and schema checks; otherwise the HTTP API returns an error, not a substitute narrative. Known names and ids are redacted; the attendance sheet is not in the snapshot.

## Deploy (essentials)

Render uses `demo-web/render.yaml` with `rootDir: demo-web`. Rooms are in memory, so a spin-down or redeploy erases them. The lecturer token lives in the Render dashboard. The presence helper and the hotspot are not part of that service; they run on the laptop. Phones still need the Render HTTPS origin for the camera.

## Module map

```text
app/main.py            HTTP
app/store.py           rooms and the redacting snapshot
app/crypto_tokens.py   KeyManager
app/roster.py          class list and RoomRoster.verify_email HMAC
app/screen_qr.py       flickering barcode issue/verify
app/network_range.py   verifier address and client CIDR
app/presence.py        local helper observe path
app/session_keys.py    per-student request HMAC
app/attendance.py      AttendanceService, DeviceBinding, AnomalyDetector
app/export_svc.py      ExportService
app/attention.py       AttentionAggregator
app/llm/               providers, agent, tools, prompts
app/audio_fsk.py       optional legacy modem (tests / UI tab)
app/static/fsk.js      same modem in the browser
```
