# Software requirements specification

## 1. Purpose

Attendance a student cannot fake from home with a photo, and live feedback for the lecturer of one lesson.

## 2. Overview

One FastAPI process serves the lecturer page (`/`) and the student page (`/student`) and keeps everything in memory. Phones use HTTPS. An LLM provider is optional.

## 3. Functional requirements

| ID | Requirement |
| --- | --- |
| FR-1 | The lecturer signs in with the lecturer key. The server compares an HMAC of it in constant time, rate-limits failures (10 per 5 min) and returns a 12-hour session token plus the greeting "שלום טום יניב, השבוע שבוע 4 בקורס מערכות נוירונים". |
| FR-2 | The lecturer opens a lesson room (default title "מערכות נוירונים – שבוע 4") and gets a student URL shown as a join QR. |
| FR-3 | The lecturer imports a CSV roster (first/last name or full name, email). The id column is ignored. Emails are stored as salted HMAC; the plain address only in memory for FR-9. |
| FR-4 | The lecturer screen shows the live barcode: an HMAC-signed, room-bound QR per 250 ms slot and a 20 Hz shimmer border. |
| FR-5 | A student picks a name from the roster and chooses in class or remote. No id or email is asked. Each join gets its own signed session. |
| FR-6 | Remote: state `remote` (✓ remote). No network or barcode check. |
| FR-7 | In class requires (a) the client IP inside `ZOOMODLE_CAMPUS_RANGES`, checked at join and again at scan, and (b) a barcode capture of ≥5 distinct codes spanning ≥2 s, each ≤6 s old by the server clock, in order, not reused for that name, from this room. Then the student picks one of 9 areas and becomes `present` with "ברוך הבא ‹name›". |
| FR-8 | Client IP: forwarded headers are honoured only from trusted proxies; `CF-Connecting-IP` only from loopback; else the right-most untrusted `X-Forwarded-For` hop; never a body field. |
| FR-9 | Duplicate names: (1) a verified in-class claim flags remote claims of the same name; (2) two verified in-class claims → both must re-pick; (3) same name again → a 6-digit code to the roster email (or `DEMO_EMAIL_OVERRIDE`), hashed, 5 min, 3 tries per phone / 6 total, single use; the correct code wins and the other goes to the lecturer; (4) expiry or exhausted tries → lecturer. The lecturer can accept or reject any claim. Without SMTP the code is shown only on the dashboard with "מצב הדגמה – המייל לא נשלח". |
| FR-10 | Dashboard: counts (in class, remote, in progress, conflicts), list with ✓, 3×3 map, conflicts, notes, questions by votes, polls with results, homework, summary. CSV/XLSX export of name, mode, state, area, time. |
| FR-11 | Polls: 2–6 options, optional correct answer, one answer per student, close poll. Students see counts only after voting or closing. |
| FR-12 | Students in `present` or `remote` post notes, questions and up-votes, and answer polls. |
| FR-13 | The lecturer uploads homework files (≤5 MB); checked-in students list and download them (as attachments). |
| FR-14 | Summary: the lecturer may publish text, or give provider/model/API key to have the agent write it; then all students of the room see it. A student may generate a private summary with their own key. |

## 4. Non-functional requirements

| Concern | Requirement |
| --- | --- |
| Secrets | Lecturer key from env or a mode-600 file, never printed or committed. API keys used per request only, never stored, logged or returned. |
| Privacy | No id number. No email in any API response, list or export. Agent input uses pseudonyms and redacted names. |
| Usability | Hebrew RTL pages; phone flow fits one screen per step. |
| Availability | In memory; restart loses lessons. Model failures return an error, never invented text. |

## 5. Threat model

| Threat | Mitigation | Residual |
| --- | --- | --- |
| Student at home sends a photo of the barcode | Codes change every 250 ms; ≥5 distinct over 2 s; 6 s freshness; network range | — |
| Live video relay from a classmate | Off-campus IPs are refused | A relay to someone else on the campus network |
| Forged IP headers | Trusted-proxy rules (FR-8) | A compromised proxy |
| Reused or forged codes | Per-slot HMAC with the room key, single use per name, room binding | Leaked master secret |
| Picking a classmate's name | Duplicate stages; e-mail code; lecturer | An absent classmate's name picked in class is not detected unless they also join |
| Forged student requests | Per-session HMAC signature, timestamp and nonce | Stolen phone session |
| Lecturer key guessing | 256-bit key, HMAC compare, rate limit | Key disclosure by the lecturer |
| Data leakage | No emails or ids out; keys dropped after use | Server memory is trusted |
