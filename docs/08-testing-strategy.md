# Testing strategy

Tests map to the classes in the [design](07-design.md) and the requirement ids in the [SRS](04-SRS.md). Run from `demo-web/`: `python -m pytest -q`.

## Layers

| Layer | Proves | How |
| --- | --- | --- |
| Unit | Barcode signing, liveness, freshness, room binding; client IP rules; LLM adapters; agent loop | `test_screen_qr.py`, `test_net.py`, `test_llm_connection.py`, `test_agent.py` |
| API | Full flows through `create_app` with a test client whose peer is a trusted proxy | `test_lecturer.py`, `test_checkin.py`, `test_duplicates.py`, `test_lesson.py`, `test_pages.py` |
| Browser (manual run) | Real pages in headless Chrome: signing, scan → area → ✓, duplicate popup and code | Playwright script run by hand; not in the suite |
| Classroom | Real phones, campus Wi-Fi, SMTP, live model | [Demo script](10-demo-script.md) |

## Traceability

| Requirement | Class | Tests |
| --- | --- | --- |
| FR-1 key sign-in, greeting | `LecturerAuth`, `Settings` | `test_lecturer.py`: greeting, wrong key + rate limit, session required, key file mode 600, Render refuses without secrets |
| FR-2, FR-4 room, barcode | `Store`, `ScreenQrService` | `test_lecturer.py`, `test_checkin.py::test_barcode_frame_is_lecturer_only_and_signed`, `test_screen_qr.py` |
| FR-3, FR-5 roster, no id/email at entry | `RoomRoster` | `test_checkin.py::test_no_id_or_email_is_asked_at_entry`, `test_lesson.py::test_emails_and_id_numbers_never_leave_the_server` |
| FR-6 remote | `CheckinBook` | `test_checkin.py::test_remote_path_needs_no_network_or_barcode` |
| FR-7 in class = network + live barcode + area | `CheckinBook`, `ScreenQrService` | in-class happy path, out-of-range IP, network re-checked at scan, still photo / short, other room, replay, bad area |
| FR-8 client IP | `net.client_ip` | spoofed `X-Forwarded-For` / `CF-Connecting-IP` / `X-Real-IP`, forged left-most hop, body field, cloudflared on loopback; `test_net.py` |
| FR-9 duplicates | `CheckinBook`, `Mailer` | `test_duplicates.py`: in class beats remote, re-pick popup, e-mail code wins, attempt limit → lecturer, expiry → lecturer, accept/reject, SMTP to override, SMTP to roster address |
| FR-10 dashboard, export | `main`, `ExportService` | counts and zones in the check-in tests; export in the privacy test |
| FR-11, FR-12 polls, notes, questions | `Store` | `test_lesson.py::test_poll_note_and_question_from_the_phone_reach_the_dashboard`, `test_unsigned_or_pending_students_cannot_post` |
| FR-13 homework | `Store`, `HomeworkFile` | `test_lesson.py::test_lecturer_uploads_homework_and_students_view_it` |
| FR-14 summary, key not kept | `SummaryService` | lecturer summary published and key absent from logs/state/response; student summary private; manual summary |

## Exit criteria

- `pytest` exits 0.
- A failure in check-in, duplicates or privacy tests blocks the demo.
- A green suite does not replace the classroom checks in the tools report.
