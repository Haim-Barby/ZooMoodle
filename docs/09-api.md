# API reference

The full, generated reference (OpenAPI / Swagger) is live at **https://zoomoodle.onrender.com/docs**. This page is the short version, taken from the routes in `demo-web/app/main.py`.

## 1. Overview and authentication

- Base URL: `https://zoomoodle.onrender.com`. JSON over HTTPS; all routes are under `/api` except the two pages.
- **Lecturer:** `POST /api/lecturer/login` with `{"key": "…"}` returns a 12-hour session token. Send it as `X-Lecturer-Session`. Login failures are rate-limited (10 per 5 min → 429).
- **Student:** `POST /api/rooms/{room_id}/join` returns `session_id` and `session_key`. Every later call sends `X-ZooMoodle-Session`, `X-ZooMoodle-Timestamp` (±60 s), `X-ZooMoodle-Nonce` (single use) and `X-ZooMoodle-Signature` = HMAC-SHA256 over method, path, body, timestamp and nonce.
- **LLM calls:** the body carries `provider`, `model`, optional `base_url` and `api_key`. The key is used for that request only.

## 2. Endpoints

Auth: **—** none, **L** lecturer, **S** signed student, **L/S** either.

| Method | Path | Auth | Purpose | FR |
| --- | --- | --- | --- | --- |
| GET | `/api/health` | — | Health check | — |
| GET | `/`, `/student` | — | Lecturer page, student page | — |
| POST | `/api/lecturer/login` | — | Key → session token and greeting | FR-1 |
| GET | `/api/lecturer/me` | L | Current session and greeting | FR-1 |
| POST | `/api/lecturer/logout` | — | End the session in `X-Lecturer-Session` | FR-1 |
| POST / GET | `/api/rooms` | L | Open a lesson / list open lessons | FR-2 |
| GET | `/api/rooms/{room_id}` | — | Public room info and barcode parameters | FR-2 |
| POST | `/api/rooms/{room_id}/close` | L | Close the lesson | FR-2 |
| POST | `/api/rooms/{room_id}/roster` | L | Import the roster CSV | FR-3 |
| POST | `/api/rooms/{room_id}/roster/group` | L | Limit the list to one group | FR-3 |
| GET | `/api/rooms/{room_id}/roster/names` | — | Names for the student picker | FR-5 |
| GET | `/api/rooms/{room_id}/barcode` | L | Current signed 250 ms code and shimmer seed | FR-4 |
| POST | `/api/rooms/{room_id}/join` | — | `{entry_id, mode}` → signed session | FR-5, FR-6, FR-7a |
| GET | `/api/rooms/{room_id}/me` | S | This phone's claim state | FR-5 |
| POST | `/api/rooms/{room_id}/barcode` | S | `{codes}` captured in 2 s | FR-7a, FR-7b |
| POST | `/api/rooms/{room_id}/area` | S | `{zone}` → `present` | FR-7c |
| POST | `/api/rooms/{room_id}/repick` | S | `{entry_id}` after a duplicate | FR-9b |
| POST | `/api/rooms/{room_id}/name-code` | S | `{code}` typed by the lecturer | FR-9d, FR-9e |
| GET | `/api/rooms/{room_id}/dashboard` | L | Counts, list, map, conflicts, open codes | FR-10, FR-9c |
| POST | `/api/rooms/{room_id}/conflicts/decide` | L | `{claim_id, action: accept\|reject}` | FR-9f |
| GET | `/api/rooms/{room_id}/export.csv`, `export.xlsx` | L | Attendance sheet | FR-10 |
| POST | `/api/rooms/{room_id}/polls` | L | `{question, options, correct_option}` | FR-11 |
| POST | `/api/rooms/{room_id}/polls/{poll_id}/close` | L | Close a poll | FR-11 |
| GET | `/api/rooms/{room_id}/polls` | S | Polls for this phone | FR-11 |
| POST | `/api/rooms/{room_id}/polls/{poll_id}/answers` | S | `{option}` | FR-11 |
| POST | `/api/rooms/{room_id}/comments` | S | `{text}` note | FR-12 |
| GET / POST | `/api/rooms/{room_id}/questions` | S | List / ask (`{text}`) | FR-12 |
| POST | `/api/rooms/{room_id}/questions/{question_id}/upvote` | S | Up-vote | FR-12 |
| POST | `/api/rooms/{room_id}/homework` | L | Upload a file (multipart, ≤5 MB) | FR-13 |
| GET | `/api/rooms/{room_id}/homework`, `/homework/{homework_id}` | L/S | List / download as attachment | FR-13 |
| POST | `/api/rooms/{room_id}/submissions` | S | `{text, filename}` homework answer | FR-15 |
| GET | `/api/rooms/{room_id}/submissions` | L/S | All (lecturer) or own (student) | FR-15 |
| POST | `/api/rooms/{room_id}/submissions/{submission_id}/review` | L/S | LLM review with comparison | FR-15 |
| POST | `/api/rooms/{room_id}/transcript` | L | Upload VTT/TXT | FR-14 |
| POST | `/api/rooms/{room_id}/summary` | L | Publish a manual summary | FR-14 |
| POST | `/api/rooms/{room_id}/summary/generate` | L | LLM summary, published to the class | FR-14 |
| GET | `/api/rooms/{room_id}/summary` | L/S | Read the summary | FR-14 |

## 3. Responses and errors

Errors are JSON `{"error": "<reason>"}` with a status code:

| Status | Meaning | Examples |
| --- | --- | --- |
| 400 | Bad input | `roster_headers`, `bad_mode`, `bad_zone`, `bad_action` |
| 401 | Not signed in, forged code or wrong code | `lecturer_required`, `session_mismatch`, `qr_mismatch`, `bad_code` |
| 403 | Not allowed | `not_on_campus_network`, `not_checked_in`, a student asking for someone else's review |
| 404 | Unknown item | `unknown_name`, `unknown_claim` |
| 409 | Conflict with the current state | `room_closed`, `qr_static`, `qr_short`, `qr_stale`, `qr_replay`, `code_not_requested` |
| 429 | Too many tries | lecturer login, `code_attempts` |

## 4. Example

```http
POST /api/rooms/a6ddc1/join
{"entry_id": "<id from /roster/names>", "mode": "remote"}

200 OK
{"session_id": "…", "session_key": "…", "claim_id": "…", "display": "דנה לוי",
 "mode": "remote", "state": "remote", "checked": true, "welcome": "ברוך הבא דנה לוי", …}
```

## 5. Limits

- One lesson state per server process, in memory; no pagination (a class is ≤150 students).
- Text limits: roster 1 MB, submission 100,000 characters, transcript 200,000 characters, homework file 5 MB.
- No versioning: the API serves only this app's two pages.
