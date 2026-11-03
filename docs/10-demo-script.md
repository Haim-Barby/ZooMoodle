# Demo script (about 10 minutes)

This is a script and a checklist for the owner. It is not a record of a demo. Nothing below has been performed in class.

Beforehand, on the laptop:

1. In `demo-web/`, create a venv, install `requirements.txt`, and copy `.env.example` to `.env`.
2. Set `ZOOMODLE_MASTER_SECRET` and `ZOOMODLE_LECTURER_TOKEN`. The copied `.env` already allows Ariel public ranges `192.114.48.0/21` and `192.114.56.0/23` (RIPE netname Ariel-segments, measured 2026-11-03 from egress 192.114.52.1). That registration also covers dorms and the campus VPN, so a subnet match only supports the ultrasonic token. Local `10.6.0.0/20` is not usable through NAT or cloudflared. Forwarded client IPs count only from `ZOOMODLE_TRUSTED_PROXIES` (default loopback).
3. Leave the LLM key empty until the connection-test minute, or put it only in the lecturer page.
4. Start Uvicorn. In another terminal start cloudflared (or another tunnel) to `http://127.0.0.1:8000`.
5. Open the lecturer page through the tunnel's `https://` URL, so its generated student link uses the same public origin. Open that link on a phone and allow the microphone. A link generated at localhost must have its origin replaced before sharing.
6. Put the phone where it can hear the laptop speakers. Unmute the laptop. Do not play the beacon through headphones.

| Minute | Who | Do this | Pass looks like |
| --- | --- | --- | --- |
| 0:00 | Lecturer | Unlock, open a room, read the student URL aloud. | Room id on screen. Phone loads the student page. |
| 0:45 | Lecturer | Point at the big code. Press Play ultrasonic beacon. | Code rotates about every 5 seconds. Phone energy bar moves if the tone arrives. |
| 1:30 | Student | Name, id, seat zone, Listen and check in. | Row appears as in-class, confidence high or medium, zone filled in. |
| 2:30 | Student | If the bar stays flat, type the on-screen code instead. | Same row, without claiming the mic worked. |
| 3:15 | Second phone or a laptop browser | I'm joining remotely. | A second row, mode remote, its own token. |
| 4:00 | Lecturer | Show flags if you also check the same id in both modes, or two names on one phone. | `both_modes` or `shared_device`, confidence low. |
| 4:45 | Lecturer | Download CSV and XLSX. Open one file. | Columns include mode, zone, confidence, flags. |
| 5:30 | Lecturer | Ask a two-option poll. Student answers. | Counts, and counts for that seat zone. |
| 6:15 | Student | Send a one-line comment. | It shows on the lecturer page with the name. |
| 7:00 | Lecturer | Enter provider/model/key, Save settings, then Test connection. Test alone clears the input without saving. | `ok` or a specific error category. Latency and tool-calling shown. Key not visible afterwards. |
| 8:00 | Lecturer | Upload a short transcript prepared from a recording, with a couple of `mm:ss` lines. Run lesson summary. | A JSON report with citations, or a clear configuration/provider error. Not a canned paragraph. |
| 9:00 | Student | Paste a short homework answer and ask for a review. | Report with `not_a_grade: true`, peers only as ids, or the same clear error if no key. |
| 9:40 | Lecturer | Show the attention panel and say it is a labeled sample, not a camera. | Disclaimer visible. No claim of face recognition. |

Say this out loud if you are asked whether attendance can be faked: the tone and the short code make it harder, and the sheet shows late, shared-device, and both-mode rows. A photograph of the code during those few seconds can still get someone in. That limit is intentional.

## Checklist

- [ ] Phone opened the `https://` URL, not the laptop's localhost.
- [ ] Microphone permission granted on the phone you care about.
- [ ] Either the ultrasonic check-in worked, or you recorded that it did not and used the code.
- [ ] Remote and in-class are different rows.
- [ ] Export opened.
- [ ] Poll result visible by zone.
- [ ] Test connection result written down (provider, model, latency, tool calling, or the error category).
- [ ] Agent result written down, or the exact error if the key or the model failed.
- [ ] Classroom table in `docs/02-tools-report.md` filled in.
- [ ] No API key left in a screenshot or a commit.

## If the tone does not arrive

The energy bar on the phone stays near zero. Try volume, distance, and a different browser. Then use the on-screen code and mark the ultrasonic row as failed in the classroom table. Do not describe the WAV tests on the development VM as a phone pass.
