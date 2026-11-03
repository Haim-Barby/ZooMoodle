# Use cases and user stories

Actors: Lecturer and Student. UC-9/10 are carried out by the lesson agent. These are acceptance criteria, not a claim that every scenario has passed. Real-phone and live-model trials remain pending.

## UC-1 Lecturer opens a room

**Story and flow.** As a lecturer, I unlock the page, enter a lesson title, and open a room so students share one lesson link.

**Acceptance.** Missing/wrong lecturer token gives HTTP 401. The response includes `id`, `title`, and `student_path`, with no key, master secret, or salt. Different rooms have different salts/keys. A shared phone link must use the HTTPS origin.

## UC-2 Student checks in from the room

**Story and flow.** As a student, I enter name/id, select a zone, and tap Listen. The phone decodes the broadcast and submits it with a signed challenge. If audio fails, I type the code.

**Acceptance.**

- A fresh code and valid signature give `in_class`, confidence `high` if subnet matches or is unconfigured.
- Multiple devices can redeem the broadcast; a second redemption by the same device gives `reused_token`.
- The previous window is accepted with `late_token` and lower confidence. Older codes, invalid signatures, reused challenges, and expired challenges store no row.
- Anonymous clients cannot fetch the current code.
- Physical reception must be tested on iPhone/Android; a WAV round trip is insufficient. Repeated listening after success is a known implementation gap.

## UC-3 Student joins remotely

**Story and flow.** As a remote student, I tap “I'm joining remotely” to keep my attendance separate.

**Acceptance.** No acoustic code is needed. Store `remote`, return its separate external token once, and assign confidence `medium` without other flags. If the id already appears in-class, mark both rows `both_modes` with confidence `low`.

## UC-4 Seat zone

**Story.** As a student, I choose my position so poll results can be grouped.

**Acceptance.** Six values: front/middle/back × left/right. A missing/invalid zone gives `bad_zone`; poll answers include a valid zone. The browser uses the selected zone for both actions.

## UC-5 Lecturer reviews anomalies

**Story.** As a lecturer, I inspect suspicious attendance instead of silently losing records.

**Acceptance.** Show mode, confidence, subnet, and flags: `late_token`, `subnet_mismatch`, `both_modes`, `shared_device`, `multi_device`. Shared/multiple-device rows remain visible with low confidence.

## UC-6 Export

**Story.** As a lecturer, I download the lesson's attendance sheet.

**Acceptance.** CSV/XLSX require the lecturer token and include student id, name, mode, zone, UTC time, confidence, flags, subnet, and device id. The export is not model input.

## UC-7 Poll

**Story and flow.** As a lecturer, I ask a short question; as a student, I choose one answer.

**Acceptance.** Two to six options; optional correct option must belong to the list. Students cannot read the correct option or per-option/zone counts. Lecturer results include both. A repeat answer from the same student id gives `already_answered`.

## UC-8 Comments

**Story.** As a student, I comment during or after the lesson; as a lecturer, I read it with its author.

**Acceptance.** Lecturer output includes the name. Agent tools use a pseudonym and redact known names/ids from comment text. Sending requires connectivity and a live room; disconnected synchronization is not implemented.

## UC-9 Transcript and lesson summary

**Story and flow.** As a lecturer, I import a transcript prepared from a recording and run the agent to connect topics/times with poll mistakes, available zone aggregates, and recommendations. The agent calls a data tool before `produce_report`.

**Acceptance.** Missing model configuration gives HTTP 503 stating that no model was called. A successful report has `kind: lesson_summary`, `stub: false`, topics, zone findings, recommendations, missing data, and citations. Known names are scrubbed from the snapshot/report. Exceeding the step limit returns an error, not invented output. Validate against an actual provider and transcript before claiming live success.

## UC-10 Homework review

**Story.** As a student or lecturer, I request feedback on one submission with an anonymous comparison to peers.

**Acceptance.** Submission returns an id; the lecturer list includes author/id, while agent tools use pseudonyms. Lecturer audience requires the lecturer token; student audience is public in this demo. Reports require boolean `not_a_grade: true`; false is rejected. `compare_submissions` supplies word-token Jaccard, not a second model. Missing configuration behaves as in UC-9. Live quality and Hebrew token comparison remain open.

## UC-11 Attention samples (extension)

**Story.** As a lecturer, I inspect a zone-level indicator without tracking students.

**Acceptance.** UI and tool output state that no camera is running. Reject samples unless `source=sample-not-camera`; return zone means and the disclaimer. A live MediaPipe pipeline is outside this demo.

## UC-12 Model connection

**Story and flow.** As a lecturer, I choose provider/model/base URL/key, Save settings for later agent calls, then Test connection. A test-only key may be used without saving, but its input is cleared afterwards.

**Acceptance.** Lecturer token required. Success includes `status: ok`, provider, model, latency, and `tool_calling` (`supported`/`not_supported`). Failures use the [FR-18 categories](04-SRS.md#3-functional-requirements) and never echo the key. `GET /api/llm/config` reports only whether a key is set. Automated HTTP mocks do not validate the real account/model.
