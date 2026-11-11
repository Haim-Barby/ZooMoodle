# Design

Diagrams are in `docs/diagrams/` (PlantUML source + SVG). Running and deploying are in the [README](../README.md).

## Classes

![Classes](diagrams/classes.svg)

A `Room` owns a `RoomRoster`, a `ScreenQrService`, a `CheckinBook`, a `SessionBook` and the lesson records (`Poll`, `Comment`, `Question`, `HomeworkFile`). A `Claim` is one phone's attempt to be one roster name; its `state` drives everything:

```text
remote ─────────────────────────────── ✓ remote
in_class: pending_barcode ─► needs_area ─► present ✓
conflicts: flagged_remote | repick ─► (re-pick) | email_code ─► present / lecturer_decision
lecturer: accept ─► present/remote, other claims ─► rejected
```

| Item | Value |
| --- | --- |
| Lecturer key | `zmk_` + 32 random bytes; server keeps HMAC-SHA256(master, key) |
| Room key | HMAC-SHA256(master, `zoomoodle-room-v2` ‖ 16 random bytes) |
| Barcode code | `ZM1.` + slot ‖ nonce ‖ HMAC(room key, room id ‖ slot ‖ nonce)[:16]; slot = 250 ms |
| Liveness | ≥5 distinct codes, ≥2 s span, increasing slots, gap ≤3 slots, ≤6 s old at receipt |
| Network | client IP in `192.114.48.0/21`, `192.114.56.0/23` (configurable) |
| Session | 32-byte secret → HKDF verifier; requests signed over method, path, body, time, nonce |
| E-mail code | 6 digits, HMAC with salt, 5 min, 3 tries per phone / 6 total, single use |

## Sequences

### In-class check-in

![In-class check-in](diagrams/seq-checkin.svg)

The network is checked twice — when the student picks בכיתה and when the barcode batch arrives — so a phone cannot start on campus and finish elsewhere. After a valid batch the claim is verified; `CheckinBook` then resolves the name (duplicate stages) before the area makes it `present`.

### Duplicate name

1. A verified in-class claim sets every remote claim of that name to `flagged_remote`.
2. Two verified in-class claims → both `repick`. Each answers the popup; a different free name resolves it.
3. If a claim that already re-picked collides again → `email_code`: one code is sent to the roster address (or `DEMO_EMAIL_OVERRIDE`). The first correct code becomes the owner; the others → `lecturer_decision`.
4. Expiry or exhausted tries → `lecturer_decision`. `decide(accept)` gives the name and rejects the rest.

### Summary

`Store.snapshot` builds pseudonymous input (polls, notes, questions, transcript). `LessonAgent` must call a data tool before `produce_report`; the report is rendered to text. A lecturer's summary is stored on the room for students; a student's is returned only to them. The API key lives only in the request.

## Module map

```text
app/main.py           HTTP routes
app/config.py         Settings, key file
app/lecturer_auth.py  LecturerAuth
app/store.py          Store, Room, snapshot
app/checkin.py        CheckinBook, Claim, EmailChallenge
app/screen_qr.py      ScreenQrService
app/net.py            client_ip, subnet_status
app/session_keys.py   SessionBook
app/roster.py         RoomRoster
app/mailer.py         Mailer
app/export_svc.py     ExportService
app/llm/              providers, agent, tools, prompts
app/static/           lecturer and student pages, qr.js, jsqr.js
```
