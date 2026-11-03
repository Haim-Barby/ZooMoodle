# Testing strategy

Tests are mapped to the classes in `docs/07-design.md` and the requirement ids in `docs/04-SRS.md`. The VM run is recorded in `docs/11-conclusions.md`. This document does not claim a classroom pass.

## Layers

| Layer | What it proves | How |
| --- | --- | --- |
| Unit | Crypto, token windows, check-in rules, anomalies, export bytes, FSK framing, agent control flow, provider error mapping | `pytest` in `tests/`. No network. |
| API | Lecturer token, hidden poll answer, key is absent from JSON, 503 when the model is not configured, summary path with a scripted provider, name redaction on a real snapshot | `fastapi.testclient` against `create_app(Settings(...))`. |
| Security / abuse | Forged and expired tokens, reused device redemption, bad signature, expired challenge, echoed API key scrubbed, unknown provider, 401/403/404/429, timeout, connection error | Unit tests above. Not a penetration test. |
| Agent | Scripted tool calls. Premature `produce_report` is rejected. `not_a_grade: false` is rejected. Names in a model report are scrubbed. The loop stops with an error instead of inventing text. | `tests/test_agent.py`. The scripted provider is not wired to HTTP unless a test installs it. |
| Manual, in class | Real speakers, real mics, campus network, tunnel, real provider | `docs/10-demo-script.md` and the empty table in `docs/02-tools-report.md`. Owner only. |

Playwright was not installed and is not part of the strategy for this demo. The phone page is checked by hand during the owner's demo.

A voice-band lowpass inside `tests/test_fsk.py` shows the lab signal does not survive a 3400 Hz cut. That is not a substitute for holding a phone call up to the laptop.

## Traceability

| Requirement | Class / module | Test |
| --- | --- | --- |
| FR-2 room key | `KeyManager` | `test_hkdf_is_stable_and_salt_separates_rooms` |
| FR-3, FR-5 token life | `TokenService` | `test_token_round_trip_and_rejection`, `test_previous_window_is_late_and_older_window_fails` |
| FR-4, FR-5, FR-6 check-in | `AttendanceService` | `test_two_devices_can_redeem_one_broadcast_and_one_device_cannot_reuse_it`, `test_bad_signature_and_expired_challenge_are_rejected`, API check-in |
| FR-7 seat zone | `SeatZone` | Valid zones occur in check-in tests; a dedicated invalid-zone rejection test is still missing. |
| FR-8 anomalies | `AnomalyDetector`, `DeviceBinding` | `test_late_token_remote_and_anomalies` |
| FR-9 subnet | `client_ip`, `subnet_status` | `tests/test_net.py`: trusted/untrusted proxies, Ariel ranges, mismatches, unconfigured list. Physical campus validation pending. |
| FR-10 export | `ExportService` | `test_csv_and_xlsx_contain_the_same_columns`, API CSV/XLSX |
| FR-11 polls | `Store.add_poll` | `test_checkin_export_and_hidden_poll_answer` |
| FR-12, privacy of names | `Store.snapshot`, `redact` | `test_summary_agent_and_name_redaction`, `test_redaction_helpers` |
| FR-13 transcript | `Store.set_transcript`, upload API | Summary tests use a short transcript; upload/size-limit edge cases need dedicated coverage. |
| FR-14, FR-15 agent | `LessonAgent`, `ToolRegistry`, `SummaryService` | `test_summary_agent_must_call_a_tool_then_report`, `test_homework_review_requires_not_a_grade_and_hides_names`, `test_agent_stops_without_inventing_a_report`, API summary |
| FR-16 no key | API gate `_require_llm` | `test_summary_without_a_key_does_not_invent_output` |
| FR-17, FR-18 connection | `LLMClient.test_connection`, adapters | `tests/test_llm_connection.py`, `test_llm_config_never_returns_the_key_and_test_classifies_errors` |
| FR-19 attention label | `AttentionAggregator` | Source validation exists in code; dedicated automated rejection coverage is missing. |
| FR-20 lecturer token | API | `test_health_and_lecturer_token_gate`, token GET without a header |
| Acoustic framing | `audio_fsk`, `fsk.js` | `test_clean_noise_and_voice_band`, `test_wav_round_trip_matches_the_on_screen_code`, plus the Node interop in the tools report |

## Connection-test cases (mocked HTTP)

| Outcome | Expected category or flag |
| --- | --- |
| HTTP 200 with a `ping` tool call | `ok`, `tool_calling=supported` |
| HTTP 200 with no tool call | `ok`, `tool_calling=not_supported` |
| HTTP 400 on the tool request, then HTTP 200 without tools | `ok`, `tool_calling=not_supported` |
| HTTP 401, or a missing key | `invalid_key` |
| HTTP 403 and HTTP 404 | `no_access` |
| HTTP 429 | `rate_limit` |
| `httpx.ReadTimeout` | `timeout` |
| `httpx.ConnectError` | `network` |
| Provider name not in the known set | `unknown_provider`, no HTTP call |
| Provider error text contains the key | the key is replaced with `[redacted]` |
| Anthropic `tool_use` and Gemini `functionCall` bodies | parsed as a supported tool call |

These rows were executed against `httpx.MockTransport`. They do not prove the owner's account or model id.

## Exit criteria for the automated suite

- `python -m pytest` exits 0 in a clean venv created from `requirements.txt`.
- A failure in token, anomaly, export, agent, or connection tests blocks calling the demo "ready on the laptop."
- A green suite does not close known UI gaps or the physical/live-model results table.

## Manual acceptance (owner)

Follow `docs/10-demo-script.md`. Record pass or fail in the table in `docs/02-tools-report.md`. Do not treat a VM WAV round trip as a phone pass.
