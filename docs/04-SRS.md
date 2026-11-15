# Software requirements specification

## 1. Purpose

Attendance a student cannot fake from home, with a spreadsheet for the lecturer (feature 1, the main one), and live feedback and LLM help for one lesson (features 2–5).

## 2. Overview

One FastAPI process serves the lecturer page (`/`) and the student page (`/student`) and keeps everything in memory. Phones use HTTPS. An LLM provider is optional and is called only with a key given in the request.

## 3. Glossary

| Term | Meaning |
| --- | --- |
| Room | One lesson: roster, live barcode, check-ins, polls, notes, questions, homework, summary. |
| Roster | The class list imported from CSV (names; e-mail kept as a salted HMAC, the plain address only in memory to send the one-time code). |
| One-time code | 6 digits e-mailed to the roster address of a disputed name; stored only as an HMAC; 5 min, 3 tries per phone / 6 total, single use. |
| Claim | One phone's attempt to be one roster name. Its state drives check-in (see the state diagram in [design](07-design.md)). |
| Live barcode | A QR code signed with the room key that changes every 250 ms (one *slot*), inside a 20 Hz shimmering border. |
| Campus ranges | Public IP ranges the university network leaves through (`192.114.48.0/21`, `192.114.56.0/23`). |
| Two-factor check-in | In class = campus network **and** live barcode. |
| Pseudonym | `P-xxxxxxxx`, a hash of a claim id; the only identity an LLM sees. |
| Submission | One student's homework text for the LLM review (feature 5). |

## 4. Functional requirements

Priority: **M** = must (the demo fails without it), **S** = should, **C** = could.

| ID | Feature | Requirement | Pri |
| --- | --- | --- | --- |
| FR-1 | 1 | The lecturer signs in with the lecturer key. The server compares an HMAC of it in constant time, rate-limits failures (10 per 5 min) and returns a 12-hour session token and a greeting built from settings (demo: "שלום טום יניב, השבוע שבוע 4 בקורס מערכות נוירונים"). | M |
| FR-2 | 1 | The lecturer opens a lesson room (default title "‹course› – שבוע ‹n›") and gets a student URL shown as a join QR. | M |
| FR-3 | 1 | The lecturer imports a CSV roster (first/last name or full name, e-mail, optional group). The ID column is ignored. E-mails are stored as salted HMAC; the plain address only in server memory, for FR-9. | M |
| FR-4 | 1 | The lecturer screen shows the live barcode: an HMAC-signed, room-bound QR per 250 ms slot and a 20 Hz shimmer border. | M |
| FR-5 | 1 | A student picks a name from the roster and chooses in class or remote. No ID or e-mail is asked. Each join gets its own signed session. | M |
| FR-6 | 1 | Remote: state `remote` (✓ remote). No network or barcode check. | M |
| FR-7 | 1 | In class requires (a) the client IP inside the campus ranges, checked at join and again at scan, and (b) a barcode capture of ≥5 distinct codes spanning ≥2 s, each ≤3 s old by the server clock, in order, not reused for that name, from this room. Then the student picks one of 9 areas and becomes `present` with "ברוך הבא ‹name›". | M |
| FR-8 | 1 | Client IP: forwarded headers are honoured only from trusted proxies (loopback, and Render's private proxy ranges). From a trusted proxy the server uses `CF-Connecting-IP` / `True-Client-IP` (set by Cloudflare); otherwise the right-most `X-Forwarded-For` hop that is neither a trusted proxy nor a Cloudflare address; never a body field. | M |
| FR-9 | 1 | Duplicate names are decided automatically: (1) a verified in-class claim flags remote claims of the same name; (2) two verified in-class claims → both must re-pick; (3) the same name again → a 6-digit one-time code is e-mailed (SMTP, e.g. Gmail) to that name's roster address (or `DEMO_EMAIL_OVERRIDE`); the first correct code wins and the other claims are rejected; (4) expiry (5 min) or all tries used (3 per phone / 6 total) → every claim on the name is rejected and the students start again. A phone that later re-picks a name proven by code is rejected. Without SMTP the code is shown only on the dashboard as "מצב הדגמה – המייל לא נשלח". The lecturer can accept or reject any claim by hand. | S |
| FR-10 | 1 | **Online sheet:** the dashboard shows counts (in class, remote, in progress, conflicts), the list with ✓, a 3×3 map, conflicts. **Offline sheet:** CSV/XLSX export of name, mode, state, area, time. | M |
| FR-11 | 3 | Polls: 2–6 options, optional correct answer, one answer per student, close poll. Students see counts only after voting or closing. | M |
| FR-12 | 2 | Students in `present` or `remote` post notes and questions and up-vote questions. The dashboard lists notes and sorts questions by votes. | M |
| FR-13 | — | The lecturer uploads homework files (≤5 MB); checked-in students download them as attachments. | C |
| FR-14 | 4 | Summary: the lecturer uploads the lesson transcript (VTT/TXT from Zoom/Meet) and either writes a summary or gives provider/model/API key to have the agent write it from the transcript, polls and questions; then all students of the room see it. | S |
| FR-15 | 5 | Homework review: a checked-in student submits a text answer (paste or text/code file, ≤100,000 characters; a new one replaces the old). The student (own submission only) or the lecturer (any) asks for a review with provider/model/key. The agent reads the submission, compares it with the other submissions through a Jaccard-similarity tool, and returns strengths, issues and an anonymous comparison, marked "not a grade". Needs at least 2 submissions in the room. | S |

## 5. Non-functional requirements

| ID | Concern | Requirement | Verified by |
| --- | --- | --- | --- |
| NFR-P1 | Performance | A room handles a 150-student hall: 150 full in-class check-ins in < 15 s server time; dashboard response < 0.5 s. (Measured: ~10 ms per check-in, 6 ms dashboard.) | `test_a_class_of_150_checks_in_quickly` |
| NFR-P2 | Performance | Dashboard and phone refresh every 2 s; a poll answer appears on the dashboard within one refresh. | Demo script |
| NFR-U1 | Usability | Check-in takes at most 4 taps after scanning the join QR (name, mode, 2 s hold, area). Hebrew RTL pages, one step per screen, works in iOS Safari and Android Chrome. | Real-life table, tools report |
| NFR-U2 | Usability | No install: the student app is a web page opened from a QR. | Demo |
| NFR-S1 | Security | Lecturer key 256 bits, from env or a mode-600 file, never printed or committed. | `test_lecturer.py` |
| NFR-S2 | Security | Every student request after join is signed (HMAC-SHA256, timestamp ±60 s, single-use nonce). | `test_lesson.py::test_unsigned_or_pending_students_cannot_post` |
| NFR-S3 | Security | LLM API keys are used for one request only: never stored, logged or returned. | `test_lesson.py`, `test_homework_review.py` |
| NFR-PR1 | Privacy | No ID number stored; no e-mail in any response, list or export (only the code is sent to it); the one-time code is never in a student response and is stored only as an HMAC; the LLM sees pseudonyms and `[name]` only. | `test_emails_and_id_numbers_never_leave_the_server`, `test_lecturer_review_compares_anonymously_and_drops_the_key` |
| NFR-A1 | Availability | In memory; a restart loses lessons (export first). A model failure returns an error, never invented text. | `test_agent.py` |
| NFR-M1 | Maintainability | Automated tests ≥ 60, line coverage ≥ 80% (now 73 tests, 85%). | `pytest --cov` |

## 6. Threat model

| Threat | Mitigation | Residual |
| --- | --- | --- |
| Student at home gets a photo of the barcode | Codes change every 250 ms; ≥5 distinct over 2 s; 3 s freshness; campus network required | — (a photo holds one code; home is off campus) |
| Video of the screen replayed later | 3 s freshness; single use per name | A replay within 3 s from the campus network |
| Live video relay from a classmate | Off-campus IPs are refused | A relay to someone else on the campus network (e.g. a dorm) |
| Forged IP headers | Trusted-proxy rules (FR-8) | A compromised proxy |
| Reused or forged codes | Per-slot HMAC with the room key, single use per name, room binding | Leaked master secret |
| Picking a classmate's name | Re-pick, then a one-time code to the classmate's own e-mail | An absent classmate's name picked in class is not detected unless they also join |
| Guessing the one-time code | 10^6 codes, 3 tries per phone / 6 total, 5 min, single use, HMAC-stored | A stolen mailbox |
| Forged student requests | Per-session HMAC signature, timestamp and nonce | Stolen phone session |
| Lecturer key guessing | 256-bit key, HMAC compare, rate limit | Key disclosure by the lecturer |
| Data leakage to the LLM | Pseudonyms, name redaction, read-only tools | Personal details a student writes inside a free-text answer |
| Copying homework from a classmate | The review compares submissions and reports similarity | The tool flags similarity; the lecturer decides |
