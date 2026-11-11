# Conclusions (draft)

The design and demo are present, with in-class attendance built as a combined roster, live flickering barcode, and local network check. Real-phone camera trials, a real lecturer hotspot, live-model validation, and the classroom demonstration have not been performed. Complete the result table below after the demo.

## Built and tested

The application combines lesson rooms, the attendance chain above, a roster checkmark and welcome, separate remote rows, anomaly flags, CSV/XLSX export, polls, comments, transcript import, and tool-calling lesson/homework agents. The architecture is a single FastAPI process, static browser pages, an in-memory store, and a local helper on the lecturer laptop. Attention is a labeled-sample stub. An optional ultrasonic FSK tab remains in the UI and is not required for the checkmark.

Recorded automated runs:

| Environment | Command | Result |
| --- | --- | --- |
| Development VM, Python 3.12.3 / pytest 9.2.0 — historical run | `pytest -v` | 25 passed (earlier, smaller suite) |
| Local review, 2026-11-03, Python 3.14.3 / pytest 9.2.0 | `python -m pytest -q` | 29 passed (earlier, smaller suite) |
| Owner's Mac, 2026-11-11, from `demo-web/` | `pytest` | **103 passed** |

The 103 tests include roster import, confirmation lockout, barcode liveness and freshness, and helper range checks (including a real socket peer outside the range). They do not demonstrate a physical phone camera or a real hotspot. Agent tests use scripted or mocked providers, not real model output.

## Remaining work

- Validate the two-second camera scan on iPhone and Android, and the helper on a real macOS or Windows hotspot.
- Use an HTTPS origin for phone links. Confirm that a still photo is rejected on a real device.
- Validate actual lesson and homework reports with a live model. Then perform the classroom demo and conclude from the observed results.
- Known product limits remain: a live video relay may pass liveness; rooms are lost on restart; launchers do not fully provision the hotspot.

## Classroom results

| Item | Result | Notes |
| --- | --- | --- |
| Date, room, phones | | |
| Live barcode, checkmark, and welcome | | |
| Still photo or short capture rejected | | |
| Helper range on the lecturer hotspot | | |
| Remote/in-class separation and flags | | |
| Export opened | | |
| Poll by zone and student comment | | |
| Model connection: provider, model, latency, tool calling | | |
| Lesson summary and homework review | | |
| Limitations and next changes | | |
