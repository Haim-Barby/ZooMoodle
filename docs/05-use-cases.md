# Use cases and user stories

Actors: Lecturer and Student. UC-9/10 are carried out by the lesson agent. These are acceptance criteria, not a claim that every scenario has passed. Real-phone camera, hotspot, and live-model trials remain pending.

## UC-1 Lecturer opens a room

**Story.** As a lecturer, I unlock the page, enter a lesson title, and open a room so students share one lesson link.

**Acceptance.** Missing or wrong lecturer token gives HTTP 401. The response includes `id`, `title`, and `student_path`, with no key, master secret, or salt. A shared phone link must use the HTTPS origin.

## UC-2 Student checks in from the room

**Story.** As a student, I pick my name from the imported list, confirm with that person's email, hold the camera on the lecturer's flickering barcode for about two seconds, and then join the lecturer's network so the local verifier can see my phone.

**Acceptance.**

- After a correct name and email confirmation, a valid two-second live capture (≥5 distinct frames), and a helper observation from a peer inside the configured range, the roster shows a checkmark and the phone shows `ברוך הבא` with that name.
- A still photo or repeated frame gives `qr_static`. A capture shorter than two seconds gives `qr_short`. A stale frame (older than 6 seconds by the server clock), a replay, a wrong-room code, or a large gap stores no checkmark.
- A claimed IP or Wi-Fi name, a forwarded header, or a socket peer outside the range is not enough. Network success without the live sequence is not enough, unless the lecturer turned the barcode off.
- Repeated wrong email attempts lock out. The list does not expose national ids, raw emails, or the email hash.
- Anonymous clients cannot fetch the current barcode token stream without the designed student session. Physical camera and hotspot behavior must be tested on iPhone/Android; the automated suite is insufficient.

## UC-3 Student joins remotely

**Story.** As a remote student, I join remotely so my attendance stays separate.

**Acceptance.** No barcode or helper is required. Store `remote` with no roster checkmark. If the same person already appears in class, mark both-mode flags as in FR-9.

## UC-4 Seat zone

**Story.** As a student, I choose my position so poll results can be grouped.

**Acceptance.** Six values: front/middle/back × left/right. A missing or invalid zone is rejected. The browser uses the selected zone for later answers.

## UC-5 Lecturer reviews anomalies

**Story.** As a lecturer, I inspect suspicious attendance instead of silently losing records.

**Acceptance.** Show mode, confidence, flags, and whether the roster checkmark is present. Shared or multiple-device rows remain visible with low confidence.

## UC-6 Export

**Story.** As a lecturer, I download the lesson's attendance sheet.

**Acceptance.** CSV/XLSX require the lecturer token. They include stored attendance fields and not a national id or the raw email. The export is not model input.

## UC-7 Poll

**Story.** As a lecturer, I ask a short question; as a student, I choose one answer.

**Acceptance.** Two to six options; an optional correct option must belong to the list. Students cannot read the correct option or per-option/zone counts. Lecturer results include both. A repeat answer from the same student gives `already_answered`.

## UC-8 Comments

**Story.** As a student, I comment during or after the lesson; as a lecturer, I read it with its author.

**Acceptance.** Lecturer output includes the name. Agent tools use a pseudonym and redact known names/ids. Sending requires a live room; disconnected synchronization is not implemented.

## UC-9 Transcript and lesson summary

**Story.** As a lecturer, I import a transcript and run the agent to connect topics with poll mistakes, comments, and zone aggregates. The agent calls a data tool before `produce_report`.

**Acceptance.** Missing model configuration gives HTTP 503 and states that no model was called. A successful report has `kind: lesson_summary`, topics, recommendations, missing data, and citations, with names scrubbed. Hitting the step limit returns an error, not invented output. Live quality remains open.

## UC-10 Homework review

**Story.** As a student or lecturer, I request feedback on one submission with an anonymous comparison to peers.

**Acceptance.** Lecturer lists include author identity; agent tools use pseudonyms. Reports require `not_a_grade: true`. Missing configuration behaves as in UC-9. Live quality remains open.

## UC-11 Attention samples (extension)

**Story.** As a lecturer, I inspect a zone-level indicator without tracking students.

**Acceptance.** UI and tool output state that no camera is running. Reject samples unless `source=sample-not-camera`. A live MediaPipe pipeline is outside this demo.

## UC-12 Model connection

**Story.** As a lecturer, I choose provider, model, base URL, and key, Save settings, then Test connection. A test-only key is not saved.

**Acceptance.** Lecturer token required. Success includes `status: ok`, latency, and `tool_calling`. Failures use the FR-18 categories and never echo the key. Automated mocks do not validate a real account.
