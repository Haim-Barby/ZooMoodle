# Conclusions (draft)

The design and demo are present. Real-phone trials, live-model validation, and the classroom demonstration have not been performed. Complete the result table below after the demo.

## Built and tested

The application combines lesson rooms, acoustic and typed attendance, device signatures, anomaly flags, CSV/XLSX export, polls, comments, transcript import, and tool-calling lesson/homework agents. The architecture is a single FastAPI process with static browser pages and an in-memory store. Attention is a labeled-sample stub.

Recorded automated runs:

| Environment | Command | Result |
| --- | --- | --- |
| Development VM, Python 3.12.3 / pytest 9.2.0 — historical run | `pytest -v` | 25 passed, 1 warning in 0.52s |
| Local review, 2026-11-03, Python 3.14.3 / pytest 9.2.0 | `python -m pytest -q` | 29 passed, 1 warning |

The warning concerns Starlette's deprecated `httpx` TestClient integration. Direct `pytest` failed to import `app` in the local review; the module command above worked. The [testing strategy](08-testing-strategy.md) maps coverage to classes; the [tools report](02-tools-report.md) preserves the original VM experiment outputs.

Local browser checks confirmed typed and remote attendance. FSK tests exchange WAV data or use simulated input; they do not demonstrate physical reception on a phone. Agent tests use scripted or mocked providers, not real model output.

## Remaining work

- Fix repeated acoustic check-ins, duplicate attendance rows, room restoration after refresh, first-use model-settings loading, and raw student error messages.
- Use an HTTPS origin for phone links and Save settings before Test connection. Improve Hebrew word-token comparison and prevent synchronous model calls from blocking other requests.
- Validate physical audio, campus HTTPS/network behavior, and actual lesson/homework reports. Then perform the classroom demo and conclude from the observed results.

## Classroom results

| Item | Result | Notes |
| --- | --- | --- |
| Date, room, phones | | |
| Acoustic attendance and code fallback | | |
| Remote/in-class separation and anomaly flags | | |
| Export opened | | |
| Poll by zone and student comment | | |
| Model connection: provider, model, latency, tool calling | | |
| Lesson summary and homework review | | |
| Limitations and next changes | | |
