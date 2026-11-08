# Hotspot presence and the class roster

English first. עברית אחר כך.

This is the lecturer setup for the classroom Wi-Fi check. It is **not** fully automatic provisioning.

## What one click means

| After this is already true | Double-click does this | It does not |
| --- | --- | --- |
| Python is installed, the repo is on the laptop, and `~/.zoomoodle/lecturer-setup.json` has the server, room, bind address, and helper key | Starts the local verifier on the address you saved | Turn the hotspot on, change the firewall, or approve a system dialog |
| That file does not exist yet | Prints the manual steps and can open the documented settings page if you answer yes | Invent a hotspot, share the same Wi-Fi adapter on a Mac, or store the Wi-Fi password |

The Wi-Fi password is typed only in the lecturer browser to draw a QR. It is not sent to the server and not written to the setup file. The network name is saved only as that QR label. Presence uses the verifier address and the phone address range instead.

On the lecturer page, enter:

- Network name, for example the name you gave the hotspot. This does not prove a phone joined it.
- Verifier address: the laptop's address on that network. Windows Mobile Hotspot is often `192.168.137.1`. macOS Internet Sharing is often `192.168.2.1`.
- Phone address range: the subnet the hotspot hands out, often `192.168.137.0/24` or `192.168.2.0/24`. A missing range, a public range, or anything wider than a /24 is rejected. The verifier address has to sit inside the range.

The helper reads those values from the mode-`0600` setup file. For each phone it reads the socket's local address and the socket's peer address. It does not read X-Forwarded-For, a claimed SSID, or the public address Render sees. A peer outside the range, or a connection that arrived on a different interface, is rejected. Someone who can already reach the verifier from inside the range can still relay a challenge. That is a path check, not a check of the person. If another network uses the same subnet, the operating system may not deliver the phone to this address; the tool does not paper over that by accepting every private address.

## macOS

Apple does not offer a supported API this tool can call to turn Internet Sharing on, and Internet Sharing cannot use the same Wi-Fi adapter as both the internet source and the network the phones join. The usual case is Ethernet (or another upstream) shared **to** Wi-Fi.

Remaining step, done by you:

1. System Settings → General → Sharing → Internet Sharing.
2. Share from the upstream interface to Wi-Fi. Approve the system prompt yourself. This launcher never clicks that prompt.
3. Note the Wi-Fi name, password, and the Mac's address on that network (often `192.168.2.1`).

With opt-in, the launcher only opens Sharing settings: `x-apple.systempreferences:com.apple.Sharing-Settings.extension`. It does not run `sudo`, `launchctl load`, or `defaults write`.

## Windows

Mobile Hotspot is the documented Windows Runtime API `NetworkOperatorTetheringManager`. It depends on the adapter. The old `netsh wlan hostednetwork` command is not used.

With opt-in, `helper/windows_hotspot.ps1` tries `StartTetheringAsync` and prints whether Windows reported success. If the adapter cannot tether, the script stops and the launcher opens `ms-settings:network-mobilehotspot`. That settings page is the remaining step. Nothing here disables security or edits the firewall.

## Two QR codes

1. **Wi-Fi QR** (`WIFI:T:WPA;...`). The phone asks the operating system before joining. It does not open ZooMoodle.
2. **Join QR**. The HTTPS (or local demo) student link. It does not contain the Wi-Fi password.

A phone that is on the hotspot then taps **אני על הרשת של המרצה**. That is a normal page navigation to `http://<hotspot-address>:8787/prove?c=...`, not a hidden request from the HTTPS page. The helper accepts the connection only on the address it was bound to, tells the server it saw the challenge, and sends the phone back. The server marks the roster row only after that observation and the same student session.

## Launch

macOS: double-click `demo-web/launch/macos/ZooMoodle Lecturer.command`.

Windows: double-click `demo-web/launch/windows/ZooMoodle Lecturer.bat`.

The helper refuses to listen on `0.0.0.0`. Pair it from the lecturer page, copy the one-time key into the setup file's `helper_key` field (mode `0600`), and set `bind_host` to the hotspot address.

## Tested vs not tested

Tested in this repo, on the cloud Linux runner, with synthetic names:

- CSV groups, blank groups, duplicates, and discarded email and full id
- Last-four failures lock out, and a claimed IP or SSID does not check the roster
- Forged helper signature, expired challenge, replay, cross-room, cross-student, revoke, and close
- Launcher plan: macOS never reports the hotspot started; Windows without an API success stays manual; the Wi-Fi password is not stored
- The helper rejects a connection whose local address is not the bind address, and a real socket whose peer is outside the configured range
- A forged X-Forwarded-For header does not move an out-of-range peer inside the range

Not tested, and not claimed:

- A real Mac or Windows PC, a real personal hotspot, iOS Safari, or Android Chrome
- Whether a particular Windows adapter can start Mobile Hotspot
- Client isolation, VPNs, or a phone reaching the laptop on the hotspot
- HTTPS page to HTTP helper on a physical phone (the cloud check used loopback HTTP)

If the phone cannot open the verifier, there is no checkmark. That is intentional.

## עברית

זה לא הקמה אוטומטית מלאה של הרשת.

לחיצה כפולה אחרי שהקובץ `~/.zoomoodle/lecturer-setup.json` כבר מכיל שרת, חדר, כתובת ומפתח מפעילה רק את המאמת המקומי. היא לא מדליקה את הנקודה החמה ולא מאשרת חלון של מערכת ההפעלה.

ב-macOS אי אפשר, מכאן, להפעיל Internet Sharing ואי אפשר לשתף את אותו מתאם Wi-Fi שממנו מגיע האינטרנט. נשאר לכם: הגדרות המערכת → General → Sharing → Internet Sharing, לאשר בעצמכם, ולרשום את כתובת המק ברשת (לרוב `192.168.2.1`).

ב-Windows יש API רשמי ל-Mobile Hotspot, אבל הוא תלוי במתאם. אם הוא נכשל, נפתח מסך ההגדרות ואתם מפעילים את הנקודה החמה בעצמכם. הפקודה הישנה `netsh hostednetwork` לא בשימוש.

בעמוד המרצה ממלאים גם את טווח הכתובות שהנקודה החמה מחלקת, לרוב `192.168.137.0/24` בווינדוס או `192.168.2.0/24` במק. בלי טווח, או עם טווח ציבורי או רחב מ-/24, אין סימון. המאמת בודק את הכתובת שהגיעה בשקע, לא כתובת שהטלפון טוען לה ולא את הכתובת הציבורית של Render.

שני קודים נפרדים: אחד רק לרשת Wi-Fi, והטלפון שואל את מערכת ההפעלה; השני רק לפתיחת ZooMoodle. סימון ברשימה מגיע רק אחרי בחירת שם, ארבע ספרות, והגעה למאמת על הכתובת שנבחרה. כתובת או שם רשת שהטלפון מדווח עליהם לא מספיקים.

לא נבדק על מק, ווינדוס, אייפון או אנדרואיד אמיתיים.
