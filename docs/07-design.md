# Design

Class and sequence diagrams for the demo. Sources and SVG exports live in `docs/diagrams/`. The agent itself is specified in `docs/09-ai-agent.md`; the loop sequence is included here so the design set is in one place.

## Design rules that the code follows

- A broadcast token is single-use **per device**. The whole class hears one signal, so every device may redeem the current code once. A second redemption by that device is rejected.
- The previous window is accepted and flagged `late_token`. Older windows fail.
- Remote admission is a different token, stored on a `remote` row. It is not an HMAC of the acoustic payload.
- Names exist on attendance, comments, and homework records. `Store.snapshot` is the only door into the agent, and it redacts them.
- `produce_report` is the only way the agent finishes. There is no offline stub on the HTTP API.
- Attention samples must declare `source=sample-not-camera`.

## Classes

![Classes](diagrams/classes.svg)

`SeatZone` is a checked value, not a picture of the furniture. `Poll`, `Comment`, and `HomeworkSubmission` are the records on the room. `SummaryService` and `HomeworkReviewService` are thin: they pick the task and call `LessonAgent`. `LLMClient` hides which provider is configured.

Crypto and framing details:

| Item | Value |
| --- | --- |
| HKDF | SHA-256, 32 bytes, salt = room salt, info = `zoomoodle-room-v1` |
| Token message | UTF-8 `roomId\|window\|` concatenated with a 2-byte nonce |
| MAC | First 4 bytes of HMAC-SHA256 |
| On-screen code | Base32 of `nonce \|\| mac`, padding stripped |
| Audio | 48 kHz nominal, 20 ms/bit, 18 kHz = 0, 19 kHz = 1, preamble `11110010`, then 48 payload bits |
| Device signature | ECDSA P-256 / SHA-256 over UTF-8 `challengeId\|nonce`, raw r\|\|s on the wire |
| Device id | First 16 hex chars of SHA-256 of `jwk.x + "." + jwk.y` |

Confidence starts high for a fresh in-class row. One weakness (late, subnet mismatch, or remote) makes it medium. Two weaknesses, or any of `both_modes`, `shared_device`, `multi_device`, makes it low.

## Sequences

### In-class check-in

![In-class check-in](diagrams/seq-checkin.svg)

The microphone path and the typed code meet at the same POST. The server does not care which one produced the Base32 string. Latency is the age of the challenge, checked before the HMAC result is trusted.

### Remote check-in

![Remote check-in](diagrams/seq-remote.svg)

### Poll

![Poll](diagrams/seq-poll.svg)

### Export

![Export](diagrams/seq-export.svg)

### Agent loop (lesson summary and homework review)

![Agent loop](diagrams/seq-agent.svg)

Homework review is the same loop. The task text names the submission id and the audience (`student` or `lecturer`), and the schema requires `not_a_grade: true`.

### Connection test

![Connection test](diagrams/seq-llm-test.svg)

Save and test are separate. Test may send a key that is used for that request only.

## Module map

```text
app/main.py            HTTP
app/store.py           rooms and the redacting snapshot
app/crypto_tokens.py   KeyManager, TokenService
app/device_keys.py     JWK and ECDSA
app/attendance.py      AttendanceService, DeviceBinding, AnomalyDetector
app/export_svc.py      ExportService
app/attention.py       AttentionAggregator
app/audio_fsk.py       modem used by tests and the VM spike
app/static/fsk.js      the same modem in the browser
app/llm/providers.py   adapters and LLMClient
app/llm/agent.py       LessonAgent, SummaryService, HomeworkReviewService
app/llm/tools.py       ToolRegistry
app/llm/prompts.py     system prompt
```
