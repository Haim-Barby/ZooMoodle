# Testing strategy

Tests map to the classes in the [design](07-design.md) and the requirement ids in the [SRS](04-SRS.md). Run from `demo-web/`:

```bash
python -m pytest -q                      # 74 tests
python -m pytest -q --cov=app            # line coverage (85% on 15 Nov 2026)
```

## 1. Layers

| Layer | Proves | How | Count |
| --- | --- | --- | --- |
| Unit | Barcode signing, liveness, freshness, room binding; client-IP rules; LLM adapters; agent loop | `test_screen_qr.py`, `test_net.py`, `test_llm_connection.py`, `test_agent.py` | 28 |
| API / integration | Full flows through `create_app` with a test client whose peer is a trusted proxy; fake LLM providers that follow the real tool-calling loop | `test_lecturer.py`, `test_checkin.py`, `test_duplicates.py`, `test_lesson.py`, `test_homework_review.py`, `test_pages.py`, `test_render_blueprint.py` | 46 |
| Load | A 150-student hall checks in; the dashboard stays fast (NFR-P1) | `test_checkin.py::test_a_class_of_150_checks_in_quickly` | (in API count) |
| Browser (manual) | Real pages in headless Chrome: sign-in, roster, live barcode, student submissions, review error path; duplicate name → re-pick → code box → right code wins → other phone rejected → start over | [`tests/manual/browser_run.py`](../demo-web/tests/manual/browser_run.py), [`tests/manual/browser_duplicates.py`](../demo-web/tests/manual/browser_duplicates.py) (Playwright), not in the suite | — |
| Real life | Real phones, campus Wi-Fi, live model | [Demo script](10-demo-script.md), table in the [tools report](02-tools-report.md#5-real-life-checks) | — |

## 2. Test design rules

- **Negative paths are first-class.** Every gate has a test for each way to fail: off-campus IP, spoofed headers, still photo, short capture, stale code, other room, replay, bad area, unsigned request, wrong key, rate limit, someone else's submission, missing key.
- **No network in the suite.** LLM providers are replaced by fakes injected through `app.state.provider_factory`; HTTP to vendors uses a mock transport.
- **Secrets are checked by search.** Tests assert the API key, e-mails and the one-time code do not appear in responses, logs (`caplog`, `capsys`) or the room's state.
- **Time is controlled.** Barcode codes are issued for real 250 ms slots ending "now", so freshness and order are tested with the real clock rules.

## 3. Traceability (requirement → class → tests)

| Requirement | Class | Tests |
| --- | --- | --- |
| FR-1 key sign-in, greeting | `LecturerAuth`, `Settings` | `test_lecturer.py` (8): greeting, wrong key + rate limit, session required, key file mode 600, Render refuses without secrets, key never printed |
| FR-2, FR-4 room, barcode | `Store`, `ScreenQrService` | `test_checkin.py::test_barcode_frame_is_lecturer_only_and_signed`, `test_screen_qr.py` (10, incl. the 3 s age limit) |
| FR-3, FR-5 roster, no ID/e-mail at entry | `RoomRoster` | `test_checkin.py::test_no_id_or_email_is_asked_at_entry`, `test_lesson.py::test_emails_and_id_numbers_are_not_stored_or_returned` |
| FR-6 remote | `CheckinBook` | `test_checkin.py::test_remote_path_needs_no_network_or_barcode` |
| FR-7a–FR-7c in class = network + live barcode + area | `CheckinBook`, `ScreenQrService` | `test_checkin.py`: happy path, out-of-range IP, network re-checked at scan, still photo / short, other room + replay, bad area |
| FR-8 client IP | `net.client_ip` | `test_checkin.py`: spoofed headers, forged left-most hop, cloudflared on loopback; `test_net.py` (7) |
| FR-9a–FR-9f duplicates + one-time code | `CheckinBook`, `LecturerChallenge` | `test_duplicates.py` (10): in class beats remote, re-pick resolves, same name again → lecturer code gives the name to the right phone and a wrong code is refused, single use, the removed phone re-enters with another name, wrong tries limited per phone and renew the code, an expired code renews, a re-pick of a name given by the lecturer is rejected, dashboard accept closes the code, lecturer accept/reject of remote claims |
| FR-10 online/offline sheet | `main`, `ExportService` | counts and zones in the check-in tests; CSV/XLSX in the privacy test |
| FR-11, FR-12 polls, notes, questions | `Store` | `test_lesson.py::test_poll_note_and_question_from_the_phone_reach_the_dashboard`, `test_poll_accepts_typed_separators_and_reaches_the_phone`, `test_unsigned_or_pending_students_cannot_post` |
| FR-13 homework files | `Store`, `HomeworkFile` | `test_lesson.py::test_lecturer_uploads_homework_and_students_view_it` |
| FR-14 summary, key not kept | `SummaryService`, `LessonAgent` | `test_lesson.py`: lecturer summary published + key absent from logs/state/response, only the lecturer generates it, manual summary; `test_agent.py` (4) |
| FR-15 homework review + comparison | `HomeworkReviewService`, `ToolRegistry`, `Submission` | `test_homework_review.py` (5): submit/replace/list, lecturer review is anonymous + calls `compare_submissions` + drops the key, student only own, needs two submissions, Hebrew similarity |
| NFR-P1 150 students | `CheckinBook`, `main` | `test_a_class_of_150_checks_in_quickly` |
| LLM adapters | `BaseProvider` subclasses | `test_llm_connection.py` (7) |

## 4. Test cases (STD)

The main automated cases, step by step. Every other test is listed by requirement in §3. Result: run with `python -m pytest -q` on 16 Nov 2026.

| ID | Verifies | Precondition | Steps | Expected | Test | Result |
| --- | --- | --- | --- | --- | --- | --- |
| TC-01 | FR-1 | Server with a lecturer key | 1. Sign in with the right key. 2. On a fresh server: a wrong key 10 times, then the right key. | 1. Session token and the greeting. 2. 401 ×10, then 429. | `test_lecturer.py::test_wrong_key_is_rejected_and_rate_limited`, `::test_lecturer_key_sign_in_shows_the_greeting` | Pass |
| TC-02 | FR-7a–FR-7c | Open room, roster, campus IP | 1. Join בכיתה. 2. Send ≥5 live codes spanning 2 s. 3. Choose an area. | `present`, "ברוך הבא ‹name›"; dashboard shows 1 in class. | `test_checkin.py::test_in_class_needs_campus_network_and_live_barcode_then_area` | Pass |
| TC-03 | FR-7a, FR-8 | IP outside the campus ranges | 1. Join בכיתה. 2. Repeat with forged forwarding headers. | 403 `not_on_campus_network` both times. | `test_checkin.py::test_out_of_range_ip_cannot_choose_in_class`, `::test_spoofed_forwarding_headers_do_not_pass_the_network_check` | Pass |
| TC-04 | FR-7b | Claim waiting for the barcode | 1. Send one code repeated. 2. Send a capture shorter than 2 s. | 1. `qr_static`. 2. `qr_short`. | `test_checkin.py::test_still_photo_and_short_capture_are_rejected` | Pass |
| TC-05 | FR-6 | Open room, any IP | Join מרחוק. | `remote`; no network or barcode check. | `test_checkin.py::test_remote_path_needs_no_network_or_barcode` | Pass |
| TC-06 | FR-9b–FR-9d | Two phones verified in class with one name | 1. Both re-pick the same name. 2. Read the code on the dashboard. 3. Type it on phone A. | Phone A `present` with the name; phone B `rejected`; the code is not in any student response. | `test_duplicates.py::test_same_name_again_shows_a_lecturer_code_that_gives_the_name_to_the_right_phone` | Pass |
| TC-07 | FR-11, FR-12 | Lecturer signed in, student checked in | 1. Lecturer opens a poll. 2. Student answers, sends a note and a question. | The dashboard shows the count, the note and the question. | `test_lesson.py::test_poll_note_and_question_from_the_phone_reach_the_dashboard` | Pass |
| TC-08 | FR-14, NFR-S3 | Transcript uploaded, fake LLM provider | Lecturer generates the summary with a key. | Summary published to the students; the key is absent from logs, state and response. | `test_lesson.py::test_lecturer_summary_with_optional_key_is_published_and_key_not_kept` | Pass |
| TC-09 | FR-15, NFR-PR1 | Two submissions, fake LLM provider | Lecturer asks for a review of one submission. | Agent calls `compare_submissions`; the model sees pseudonyms only; report marked not a grade; key dropped. | `test_homework_review.py::test_lecturer_review_compares_anonymously_and_drops_the_key` | Pass |
| TC-10 | FR-10, NFR-PR1 | Roster with ID and e-mail columns, check-ins | Download CSV and XLSX. | Name, mode, state, area, time; no e-mail or ID anywhere. | `test_lesson.py::test_emails_and_id_numbers_are_not_stored_or_returned` | Pass |

## 5. Coverage

| Module | Line coverage |
| --- | --- |
| `checkin.py` | 95% |
| `store.py` | 90% |
| `screen_qr.py` | 88% |
| `main.py` | 88% |
| `llm/agent.py` | 98% |
| `llm/providers.py` | 80% |
| `llm/tools.py` | 69% (transcript time filters are not exercised) |
| **Total** | **85%** |

## 6. Exit criteria

- `pytest` exits 0 and total coverage stays ≥ 80%.
- A failure in check-in, duplicate/lecturer-code, privacy or key-handling tests blocks the demo.
- A green suite does not replace the real-life checks in the tools report.
