# Testing strategy

Tests map to the classes in the [design](07-design.md) and the requirement ids in the [SRS](04-SRS.md). Run from `demo-web/`:

```bash
python -m pytest -q                      # 73 tests
python -m pytest -q --cov=app            # line coverage (85% on 15 Nov 2026)
```

## 1. Layers

| Layer | Proves | How | Count |
| --- | --- | --- | --- |
| Unit | Barcode signing, liveness, freshness, room binding; client-IP rules; LLM adapters; agent loop; Hebrew similarity | `test_screen_qr.py`, `test_net.py`, `test_llm_connection.py`, `test_agent.py`, part of `test_homework_review.py` | 26 |
| API / integration | Full flows through `create_app` with a test client whose peer is a trusted proxy; fake LLM providers that follow the real tool-calling loop | `test_lecturer.py`, `test_checkin.py`, `test_duplicates.py`, `test_lesson.py`, `test_homework_review.py`, `test_pages.py`, `test_render_blueprint.py` | 47 |
| Load | A 150-student hall checks in; the dashboard stays fast (NFR-P1) | `test_checkin.py::test_a_class_of_150_checks_in_quickly` | (in API count) |
| Browser (manual) | Real pages in headless Chrome: sign-in, roster, live barcode, student submissions, review error path; duplicate name → re-pick → code box → right code wins → other phone rejected → start over | [`tests/manual/browser_run.py`](../demo-web/tests/manual/browser_run.py), [`tests/manual/browser_duplicates.py`](../demo-web/tests/manual/browser_duplicates.py) (Playwright), not in the suite | — |
| Real life | Real phones, campus Wi-Fi, live model | [Demo script](10-demo-script.md), table in the [tools report](02-tools-report.md#5-real-life-checks) | — |

## 2. Test design rules

- **Negative paths are first-class.** Every gate has a test for each way to fail: off-campus IP, spoofed headers, still photo, short capture, stale code, other room, replay, bad area, unsigned request, wrong key, rate limit, someone else's submission, missing key.
- **No network in the suite.** LLM providers are replaced by fakes injected through `app.state.provider_factory`; HTTP to vendors uses a mock transport.
- **Secrets are checked by search.** Tests assert the API key and e-mails do not appear in responses, logs (`caplog`, `capsys`) or the room's state.
- **Time is controlled.** Barcode codes are issued for real 250 ms slots ending "now", so freshness and order are tested with the real clock rules.

## 3. Traceability (requirement → class → tests)

| Requirement | Class | Tests |
| --- | --- | --- |
| FR-1 key sign-in, greeting | `LecturerAuth`, `Settings` | `test_lecturer.py` (8): greeting, wrong key + rate limit, session required, key file mode 600, Render refuses without secrets, key never printed |
| FR-2, FR-4 room, barcode | `Store`, `ScreenQrService` | `test_checkin.py::test_barcode_frame_is_lecturer_only_and_signed`, `test_screen_qr.py` (7, incl. the 3 s age limit) |
| FR-3, FR-5 roster, no ID/e-mail at entry | `RoomRoster` | `test_checkin.py::test_no_id_or_email_is_asked_at_entry`, `test_lesson.py::test_emails_and_id_numbers_never_leave_the_server` |
| FR-6 remote | `CheckinBook` | `test_checkin.py::test_remote_path_needs_no_network_or_barcode` |
| FR-7 in class = network + live barcode + area | `CheckinBook`, `ScreenQrService` | `test_checkin.py`: happy path, out-of-range IP, network re-checked at scan, still photo / short, other room + replay, bad area |
| FR-8 client IP | `net.client_ip` | `test_checkin.py`: spoofed headers, forged left-most hop, cloudflared on loopback; `test_net.py` (7) |
| FR-9 duplicates + one-time code | `CheckinBook`, `EmailChallenge`, `Mailer` | `test_duplicates.py` (9): in class beats remote, re-pick resolves, same name again → e-mail code and the right code wins (other rejected), wrong codes reject all, expiry rejects all, a re-pick of a code-proven name is rejected, lecturer accept/reject, SMTP to the demo override, SMTP to the roster address |
| FR-10 online/offline sheet | `main`, `ExportService` | counts and zones in the check-in tests; CSV/XLSX in the privacy test |
| FR-11, FR-12 polls, notes, questions | `Store` | `test_lesson.py::test_poll_note_and_question_from_the_phone_reach_the_dashboard`, `test_poll_accepts_typed_separators_and_reaches_the_phone`, `test_unsigned_or_pending_students_cannot_post` |
| FR-13 homework files | `Store`, `HomeworkFile` | `test_lesson.py::test_lecturer_uploads_homework_and_students_view_it` |
| FR-14 summary, key not kept | `SummaryService`, `LessonAgent` | `test_lesson.py`: lecturer summary published + key absent from logs/state/response, only the lecturer generates it, manual summary; `test_agent.py` (4) |
| FR-15 homework review + comparison | `HomeworkReviewService`, `ToolRegistry`, `Submission` | `test_homework_review.py` (5): submit/replace/list, lecturer review is anonymous + calls `compare_submissions` + drops the key, student only own, needs two submissions, Hebrew similarity |
| NFR-P1 150 students | `CheckinBook`, `main` | `test_a_class_of_150_checks_in_quickly` |
| LLM adapters | `BaseProvider` subclasses | `test_llm_connection.py` (7) |

## 4. Coverage

| Module | Line coverage |
| --- | --- |
| `checkin.py` | 93% |
| `mailer.py` | 87% |
| `store.py` | 90% |
| `screen_qr.py` | 88% |
| `main.py` | 88% |
| `llm/agent.py` | 98% |
| `llm/providers.py` | 80% |
| `llm/tools.py` | 69% (transcript time filters are not exercised) |
| **Total** | **85%** |

## 5. Exit criteria

- `pytest` exits 0 and total coverage stays ≥ 80%.
- A failure in check-in, duplicate/e-mail-code, privacy or key-handling tests blocks the demo.
- A green suite does not replace the real-life checks in the tools report.
