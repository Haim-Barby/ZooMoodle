# Statement of work

ZooMoodle, Introduction to Software Engineering, Exercise 2. Individual project.

## Objective and scope

Deliver an implementable design and a ten-minute classroom demo of a teaching tool. Attendance is the priority; students use a phone web page and the lecturer uses a laptop.

The demo covers lesson rooms, acoustic or typed-code attendance, device signatures and anomaly flags, separate remote attendance, seat zones, CSV/XLSX export, comments, polls, transcript import, and lesson/homework agents. Model configuration and a connection test support the agents. Full requirements are in the [SRS](04-SRS.md); the [README](../README.md) maps deliverables 1–11 to their files.

The attention extension uses labeled sample aggregates only. Native apps, university accounts, a durable database, live camera processing, and integrations with university systems are outside this demo. Converting recordings to transcripts is an external prerequisite.

## Work sequence and status

No calendar deadlines have been assigned.

1. Define the problem, scope, and tool choices — written; VM experiments recorded.
2. Specify requirements, use cases, components, classes, sequences, and testing — documents and diagrams present.
3. Compose the demo and run automated tests — implemented; known implementation gaps remain in [conclusions](11-conclusions.md).
4. Validate real phones, campus networking, HTTPS, and a live model — pending.
5. Give the classroom demo and complete the final results — pending.

## Assumptions

- A single laptop process holds lesson data in memory. Restarting clears rooms regardless of whether the master secret is stable.
- Phones access the same application through an HTTPS tunnel. The lecturer uses the HTTPS origin when sharing generated links.
- Broadcast tokens are single-use **per device**, so the same signal can admit the whole class.
- The configured Ariel subnets are a supporting signal; the acoustic path and the campus tunnel still need validation.
- A lecturer-supplied model configuration is required for the agents; tests use scripted responses. Known names and ids are redacted on the agent path, with limits described in the SRS.

## Principal risks

| Risk | Response and remaining limit |
| --- | --- |
| Speakers or phone mics drop 18–19 kHz | Typed-code fallback; test on real phones before claiming automatic attendance. |
| A code or signal is relayed | Short lifetime, device signatures, and flags. Fast sharing can still succeed; see the SRS threat model. |
| Tunnel or subnet check fails on campus | Test the HTTPS origin and forwarded IP on campus; subnet is a confidence flag, not an admission gate. |
| Model is unavailable or gives an invalid report | Connection test, read-only tools, report validation, and a bounded loop; return an error rather than a substitute report. |
| Process stops | Export attendance before shutdown; the demo does not provide recovery or persistence. |

## Acceptance

- Lecturer authentication gates room creation, current codes, attendance, exports, configuration, and lecturer AI actions.
- A student can select a zone, check in, answer a poll, comment, and submit homework. Current codes work for multiple devices; reuse on one device fails. Anomalies remain visible.
- CSV and XLSX contain identity, mode, zone, time, confidence, flags, subnet, and device id.
- Without model configuration, AI routes return a configuration error. With a tool-calling provider, the agents must read data before returning a validated report; homework reviews require `not_a_grade: true`.
- Completion requires recorded classroom and live-model results, not just written plans. Use the [demo script](10-demo-script.md) and fill the results tables.
