# Software requirements specification

## 1. Introduction

**Purpose.** Attendance a student cannot fake from home, with a spreadsheet for the lecturer (feature 1, the main one), and live feedback and LLM help for one lesson (features 2–5).

**Scope.** One lesson at a time, in one classroom; out of scope as in the [SoW](03-SoW.md#2-scope).

**References**

- Ex2 assignment, *Vibe Coding & Deep Designing: Web-based Teaching Tool*, Intro2SE, Ariel University.
- Lecture 02a, *Software Engineering Documents*, B. Ben-Moshe, Ariel University.
- RIPE database, Ariel University inetnum `192.114.48.0 – 192.114.57.255`.
- Project documents: [SoW](03-SoW.md), [use cases](05-use-cases.md), [components](06-components.md), [design](07-design.md), [API](09-api.md), [testing](08-testing-strategy.md).

## 2. Overview

One FastAPI process serves the lecturer page (`/`) and the student page (`/student`) and keeps everything in memory. Phones use HTTPS. An LLM provider is optional and is called only with a key given in the request.

**User classes**

| User | Device | Needs |
| --- | --- | --- |
| Lecturer | Laptop + projector, desktop browser | Sign in with the key, run the lesson, read the dashboard, export the sheet. |
| Student in class | Own phone on the campus Wi-Fi | Check in within seconds, take part in polls, notes and questions, submit homework. |
| Student at home | Phone or laptop, any network | Join remotely and take part in the same way. |
| LLM provider | External system | Answers agent requests for features 4–5. |

**Operating environment and constraints.** iOS Safari and Android Chrome on the phone; any modern browser on the laptop. Server: Python 3.12, FastAPI, one Uvicorn worker on Render's free plan (see the deployment diagram in [components](06-components.md#deployment)). No database, no Moodle/Zoom integration and no university personal-data systems (assignment guideline 1).

## 3. Glossary

| Term | Meaning |
| --- | --- |
| Room | One lesson: roster, live barcode, check-ins, polls, notes, questions, homework, summary. |
| Roster | The class list imported from CSV. Only names (and an optional group) are kept; the ID and e-mail columns are not stored. |
| One-time code | 6 digits shown on the lecturer dashboard for a disputed name and typed by the lecturer on the real student's phone; stored only as an HMAC; renewed every 2 min, 3 tries per phone, a new code after 6 wrong tries, single use. |
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
| FR-3 | 1 | The lecturer imports a CSV roster (first/last name or full name, e-mail, optional group). Only names and the group are stored; the ID column is ignored and the e-mail column is used only to skip repeated rows. | M |
| FR-4 | 1 | The lecturer screen shows the live barcode: an HMAC-signed, room-bound QR per 250 ms slot and a 20 Hz shimmer border. | M |
| FR-5 | 1 | A student picks a name from the roster and chooses in class or remote. No ID or e-mail is asked. Each join gets its own signed session. | M |
| FR-6 | 1 | Remote: state `remote` (✓ remote). No network or barcode check. | M |
| FR-7a | 1 | In class requires the client IP inside the campus ranges, checked at join and again when the barcode capture arrives. | M |
| FR-7b | 1 | In class requires a barcode capture of ≥5 distinct codes spanning ≥2 s, each ≤3 s old by the server clock, in order, not reused for that name, from this room. | M |
| FR-7c | 1 | After FR-7a and FR-7b pass, the student picks one of 9 areas and becomes `present` with "ברוך הבא ‹name›". | M |
| FR-8 | 1 | Client IP: forwarded headers are honoured only from trusted proxies (loopback, and Render's private proxy ranges). From a trusted proxy the server uses `CF-Connecting-IP` / `True-Client-IP` (set by Cloudflare); otherwise the right-most `X-Forwarded-For` hop that is neither a trusted proxy nor a Cloudflare address; never a body field. | M |
| FR-9a | 1 | A verified in-class claim flags every remote claim of the same name for the lecturer. | S |
| FR-9b | 1 | Two verified in-class claims on one name → both phones must re-pick their name. | S |
| FR-9c | 1 | The same name again after a re-pick → the lecturer dashboard shows a 6-digit one-time code for that name, stored only as an HMAC, renewed every 2 min, single use. | S |
| FR-9d | 1 | The phone on which the lecturer types the code gets the name; the other claims on the name are rejected and those phones may check in again with another name. A phone that later re-picks that name is rejected. | S |
| FR-9e | 1 | A wrong code is refused: 3 tries per phone (then 429), and 6 wrong tries in total → a new code. | S |
| FR-9f | 1 | The lecturer can accept or reject any claim by hand; accepting also closes an open code. | S |
| FR-10 | 1 | **Online sheet:** the dashboard shows counts (in class, remote, in progress, conflicts), the list with ✓, a 3×3 map, conflicts. **Offline sheet:** CSV/XLSX export of name, mode, state, area, time. | M |
| FR-11 | 3 | Polls: 2–6 options, optional correct answer, one answer per student, close poll. Students see counts only after voting or closing. | M |
| FR-12 | 2 | Students in `present` or `remote` post notes and questions and up-vote questions. The dashboard lists notes and sorts questions by votes. | M |
| FR-13 | — | The lecturer uploads homework files (≤5 MB); checked-in students download them as attachments. | C |
| FR-14 | 4 | Summary: the lecturer uploads the lesson transcript (VTT/TXT from Zoom/Meet) and either writes a summary or gives provider/model/API key to have the agent write it from the transcript, polls and questions; then all students of the room see it. | S |
| FR-15 | 5 | Homework review: a checked-in student submits a text answer (paste or text/code file, ≤100,000 characters; a new one replaces the old). The student (own submission only) or the lecturer (any) asks for a review with provider/model/key. The agent reads the submission, compares it with the other submissions through a Jaccard-similarity tool, and returns strengths, issues and an anonymous comparison, marked "not a grade". Needs at least 2 submissions in the room. | S |

## 5. External interfaces

| Interface | Details |
| --- | --- |
| User interface | Two Hebrew RTL web pages: lecturer `/`, student `/student`, one step per screen. |
| REST API | JSON over HTTPS under `/api`; see the [API reference](09-api.md). |
| Phone camera | `getUserMedia` + jsQR in the browser; needs HTTPS. |
| Proxy headers | `CF-Connecting-IP`, `True-Client-IP`, `X-Forwarded-For`, honoured only from trusted proxies (FR-8). |
| LLM providers | HTTPS REST: OpenAI-compatible, Anthropic, Gemini; key in the request only. |
| Files | In: roster CSV, transcript VTT/TXT, homework file. Out: attendance CSV/XLSX. |

## 6. Non-functional requirements

| ID | Concern | Requirement | Verified by |
| --- | --- | --- | --- |
| NFR-P1 | Performance | A room handles a 150-student hall: 150 full in-class check-ins in < 15 s server time; dashboard response < 0.5 s. (Measured: ~10 ms per check-in, 6 ms dashboard.) | `test_a_class_of_150_checks_in_quickly` |
| NFR-P2 | Performance | Dashboard and phone refresh every 2 s; a poll answer appears on the dashboard within one refresh. | Demo script |
| NFR-U1 | Usability | Check-in takes at most 4 taps after scanning the join QR (name, mode, 2 s hold, area). Hebrew RTL pages, one step per screen, works in iOS Safari and Android Chrome. | Real-life table, tools report |
| NFR-U2 | Usability | No install: the student app is a web page opened from a QR. | Demo |
| NFR-S1 | Security | Lecturer key 256 bits, from env or a mode-600 file, never printed or committed. | `test_lecturer.py` |
| NFR-S2 | Security | Every student request after join is signed (HMAC-SHA256, timestamp ±60 s, single-use nonce). | `test_lesson.py::test_unsigned_or_pending_students_cannot_post` |
| NFR-S3 | Security | LLM API keys are used for one request only: never stored, logged or returned. | `test_lesson.py`, `test_homework_review.py` |
| NFR-PR1 | Privacy | No ID number or e-mail stored; none in any response, list or export; the one-time code is shown only on the lecturer dashboard, never in a student response, and is stored only as an HMAC; the LLM sees pseudonyms and `[name]` only. | `test_emails_and_id_numbers_are_not_stored_or_returned`, `test_lecturer_review_compares_anonymously_and_drops_the_key` |
| NFR-A1 | Availability | In memory; a restart loses lessons (export first). A model failure returns an error, never invented text. | `test_agent.py` |
| NFR-M1 | Maintainability | Automated tests ≥ 60, line coverage ≥ 80% (now 74 tests, 85%). | `pytest --cov` |

## 7. Threat model

| Threat | Mitigation | Residual |
| --- | --- | --- |
| Student at home gets a photo of the barcode | Codes change every 250 ms; ≥5 distinct over 2 s; 3 s freshness; campus network required | — (a photo holds one code; home is off campus) |
| Video of the screen replayed later | 3 s freshness; single use per name | A replay within 3 s from the campus network |
| Live video relay from a classmate | Off-campus IPs are refused | A relay to someone else on the campus network (e.g. a dorm) |
| Forged IP headers | Trusted-proxy rules (FR-8) | A compromised proxy |
| Reused or forged codes | Per-slot HMAC with the room key, single use per name, room binding | Leaked master secret |
| Picking a classmate's name | Re-pick, then the lecturer gives the name by typing a one-time code on the real student's phone | An absent classmate's name picked in class is not detected unless they also join |
| Guessing the one-time code | 10^6 codes, 3 tries per phone, a new code after 6 wrong tries, renewed every 2 min, single use, HMAC-stored | A student who reads the code off the lecturer's screen |
| Forged student requests | Per-session HMAC signature, timestamp and nonce | Stolen phone session |
| Lecturer key guessing | 256-bit key, HMAC compare, rate limit | Key disclosure by the lecturer |
| Data leakage to the LLM | Pseudonyms, name redaction, read-only tools | Personal details a student writes inside a free-text answer |
| Copying homework from a classmate | The review compares submissions and reports similarity | The tool flags similarity; the lecturer decides |
