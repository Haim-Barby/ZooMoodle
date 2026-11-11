# Demo script (about 10 minutes)

This is a script and a checklist for the owner. It is not a record of a demo. Nothing below has been performed in class.

Beforehand, on the laptop:

1. In `demo-web/`, create a venv, install `requirements.txt`, and copy `.env.example` to `.env`. Set `ZOOMODLE_MASTER_SECRET` and `ZOOMODLE_LECTURER_TOKEN`. Never commit `.env`.
2. Start the app. For phones, start an HTTPS tunnel to `http://127.0.0.1:8000` (or use the Render HTTPS origin). Open the lecturer page through that `https://` URL so student links match. A localhost link must have its origin replaced.
3. Import the class list and select the group. Enter the network name, verifier address, and phone range (often `192.168.2.1` + `192.168.2.0/24` on a Mac, or `192.168.137.1` + `192.168.137.0/24` on Windows). Start Internet Sharing or Mobile Hotspot by hand if needed, then start the helper from the launcher or the documented command. Launchers do not fully provision the hotspot.
4. Leave the LLM key empty until the connection-test minute, or enter it only on the lecturer page.

| Minute | Who | Do this | Pass looks like |
| --- | --- | --- | --- |
| 0:00 | Lecturer | Unlock, open a room, show the student HTTPS link and the flickering barcode. | Room id on screen. The barcode changes continuously, not as a still image. |
| 0:45 | Student | Open the link, pick a name from the list, confirm with that email. | Name list only; no typing of a new name; email is not shown in the list. |
| 1:15 | Student | Hold the camera on the live barcode for about two seconds, then join the lecturer network and open the helper. | Roster checkmark and `ברוך הבא` with that name. |
| 2:30 | Lecturer or second phone | Show a still photo or screenshot of the barcode, or stop the scan early. | No checkmark; `qr_static` or `qr_short`. |
| 3:15 | Second phone or a laptop | Join remotely. | A separate remote row, no roster checkmark. |
| 4:00 | Lecturer | Download CSV and XLSX and open one file. | Name, mode, zone, flags; no national id or raw email. |
| 5:00 | Lecturer / Student | Two-option poll; the student answers. | Counts, and counts for that seat zone. |
| 5:45 | Student | Send a one-line comment. | It shows on the lecturer page with the name. |
| 6:30 | Lecturer | Provider, model, key: Save settings, then Test connection. | `ok` or a specific error category. Key not visible afterwards. |
| 8:00 | Lecturer | Upload a short transcript and run lesson summary. | A JSON report with citations, or a clear configuration error — not a canned paragraph. |
| 9:00 | Student | Paste a short homework answer and ask for a review. | Report with `not_a_grade: true`, or the same clear error if no key. |
| 9:40 | Lecturer | Attention panel: labeled sample, not a camera. | Disclaimer visible. |

Say this out loud if asked whether attendance can be faked: a still photo is not enough, and a student who is not on the lecturer's network should fail the helper. A classmate who live-streams the screen may still pass liveness; the network check is what covers that case. Real phone and hotspot behavior should be reported honestly if they fail.

## Checklist

- [ ] Phone opened the `https://` URL, not the laptop's localhost.
- [ ] Camera permission granted; two-second live scan produced a checkmark and welcome.
- [ ] Still photo or short capture did not mark the roster.
- [ ] Helper used the entered range; a claimed IP was not enough.
- [ ] Remote and in-class are different rows; remote has no checkmark.
- [ ] Export opened, without a national id or the raw email.
- [ ] Poll by zone and a named comment visible.
- [ ] Test connection and agent results written down, or the exact error.
- [ ] Classroom table in `docs/02-tools-report.md` filled in.
- [ ] No API key left in a screenshot or a commit.
