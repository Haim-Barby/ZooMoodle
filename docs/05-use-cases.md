# Use cases and user stories

Actors: Lecturer, Student. The lesson agent is the software that carries UC-9 and UC-10. Acceptance criteria are what the demo can be checked against. Items that need a real phone or a real provider are marked.

## UC-1 Lecturer opens a room

**Story.** As a lecturer, I open a room for this lesson so students have one place to check in.

**Main flow.** Unlock the lecturer page with the lecturer token. Enter a title. Open the room. The page shows the room id and a student link.

**Acceptance.**

- Missing or wrong lecturer token: HTTP 401, no room.
- Response contains `id`, `title`, and `student_path`. It does not contain the master secret, the room key, or the salt.
- A second room gets a different salt and a different key.

## UC-2 Student checks in from the room

**Story.** As a student in the room, I want my phone to pick up the lecturer's tone, or to type the code on the screen if it cannot.

**Main flow.** Enter name and student id. Pick a seat zone (UC-4). Tap listen. The page decodes the FSK payload into the same code the lecturer sees and submits it with a signed challenge. Alternatively type the code.

**Acceptance.**

- A current code and a valid device signature produce `mode=in_class` and confidence `high` when the subnet list is unset or the IP matches.
- Two different devices can submit that same code.
- The same device submitting that code again is rejected with `reused_token`.
- A code from the previous window is accepted with `late_token` and a lower confidence.
- An older code, a bad signature, a reused challenge, or a challenge older than the limit is rejected and no attendance row is stored.
- The student API does not offer `GET` of the current code.
- **Owner, not done here:** the tone is actually heard by an iPhone and an Android phone. The VM only round-tripped WAV files.

## UC-3 Student joins remotely

**Story.** As a student who is not in the room, I mark myself remote so I am not listed as present in class.

**Main flow.** Tap "I'm joining remotely". The server issues an external token and stores a `remote` row.

**Acceptance.**

- The row's mode is `remote`. The acoustic code is not required.
- The response includes the external token once.
- Confidence is `medium` when no other flag applies.
- If that student id already has an in-class row, both rows gain `both_modes` and confidence `low`.

## UC-4 Seat zone

**Story.** As a student, I tap where I am sitting so later results can be grouped.

**Acceptance.**

- The six zones are front/middle/back × left/right.
- Check-in without one of those values is `bad_zone`.
- Poll answers carry the same zone.

## UC-5 Lecturer reviews anomalies

**Story.** As a lecturer, I want odd check-ins flagged on the sheet rather than hidden.

**Acceptance.**

- The sheet shows mode, confidence, flags, and subnet.
- Flags used by the demo: `late_token`, `subnet_mismatch`, `both_modes`, `shared_device`, `multi_device`.
- A shared device or two devices for one student stays on the sheet at confidence `low`.

## UC-6 Export

**Story.** As a lecturer, I download the sheet for the lesson.

**Acceptance.**

- CSV and XLSX require the lecturer token.
- Columns: student id, name, mode, seat zone, UTC time, confidence, flags, subnet, device id.
- The file is not sent to the model.

## UC-7 Poll

**Story.** As a lecturer, I ask one short question about what I just taught and see answers by seat zone. As a student, I tap one option.

**Acceptance.**

- 2 to 6 options. Optional correct option must be one of them.
- Student `GET` omits `correct_option` and the counts.
- Lecturer `GET` includes counts and `by_zone`.
- A second answer from the same student id is `already_answered`.

## UC-8 Comments

**Story.** As a student, I send a comment during the lesson or after it. As a lecturer, I read it with the student's name.

**Acceptance.**

- The lecturer list shows the name.
- The agent snapshot shows a pseudonym and redacts that name inside the text.

## UC-9 Transcript and lesson summary

**Story.** As a lecturer, after class I import a transcript file and get a report that ties topics and times to poll mistakes and to attention drops per zone, with a suggestion for the next lesson.

**Main flow.** Choose a text file. The page uploads it and calls the summary agent. The agent must call a data tool, then `produce_report`.

**Acceptance.**

- No configured model: HTTP 503, body states that no model was called, and there is no summary text.
- With a tool-calling provider, the response is `kind: lesson_summary`, `stub: false`, and includes topics, zone findings, recommendations, missing data, and citations.
- Known names in the transcript do not appear in the snapshot or the returned report.
- If the loop hits the step limit, the API errors and does not invent a report.
- **Owner, not done here:** a real provider and a real lesson transcript.

## UC-10 Homework review

**Story.** As a student, I want a deep review of my homework and an anonymized comparison with other submissions. As a lecturer, I want the same review for a submission I pick.

**Acceptance.**

- Submit text, receive a submission id. The lecturer list shows the name and the id. The agent does not.
- Student audience does not need the lecturer token. Lecturer audience does.
- The report has `not_a_grade: true`. A report that sets it false is refused by the tool, so the loop can retry.
- Comparison uses `compare_submissions` (Jaccard on word tokens), not a second hidden model.
- No key: same 503 as UC-9, no fabricated review.

## UC-11 Attention map

**Story.** As a lecturer, I want a zone-level attention indicator over time, without identifying students.

**Demo acceptance (this repository).**

- The page states that no camera is running.
- `POST` of samples whose source is not `sample-not-camera` is rejected.
- The agent tool returns the disclaimer and, if samples exist, means by zone.
- **Not in this demo:** a live MediaPipe head-pose pipeline. The VM spike only showed that a blank image yields no face.

## UC-12 Test the model connection

**Story.** As a lecturer, after I choose a provider and enter a key, I press Test connection and see whether that model answers and whether it can call a tool.

**Main flow.** Select provider (OpenAI, Anthropic, Gemini, xAI, Ollama, or another OpenAI-compatible URL). Enter model and, if needed, base URL and key. Press Test connection. Optionally press Save. The key field is cleared after the request.

**Acceptance.**

- Lecturer token required.
- Success JSON includes `status: ok`, `provider`, `model`, `latency_ms`, and `tool_calling` (`supported` or `not_supported`).
- Failure JSON uses a category: `invalid_key`, `no_access`, `rate_limit`, `timeout`, `network`, `unknown_provider`, and does not contain the key even if the provider echoed it.
- A key typed only into the test is not stored unless Save is used.
- `GET /api/llm/config` never includes the key.
- **Owner, not done here:** press the button against the real account. The automated tests mock HTTP.
