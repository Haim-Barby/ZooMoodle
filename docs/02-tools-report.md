# Technical tools report

This report chooses a tool for each concern in the ZooMoodle demo and records what was actually run on the development VM. It does not record a classroom result. The empty table at the end is for the owner to fill on real phones, on the university network, and with a tunnel from campus.

Nothing in the VM spikes used a live LLM key. No phone microphone was attached. `cloudflared` and `ngrok` are not installed here.

## Choices

| Concern | Candidates | Choice | Why |
| --- | --- | --- | --- |
| Backend | FastAPI, Flask, Django | FastAPI 0.162.0 + Uvicorn 0.54.0 | Small JSON API, file upload, static files. A hello route answered on this VM. |
| Data over sound | ggwave, custom FSK in the Web Audio API | Custom FSK, 18 kHz = 0 and 19 kHz = 1 | The agreed signal is near 18–20 kHz, and the student app is a browser. ggwave works on this VM but its ultrasound protocol is not that band (see the spike). Web Bluetooth is not used: iOS Safari does not support it. |
| Room crypto | `hmac` + `hashlib` only, or `cryptography` HKDF | HKDF-SHA256 via `cryptography` 50.0.2, HMAC-SHA256 via `hmac` | Matches the room-key design. Round trip ran on this VM. |
| Spreadsheet | CSV only, openpyxl, pandas | CSV in the standard library, XLSX via openpyxl 3.1.5 | Both writers ran. Pandas is more than this demo needs. |
| HTTPS tunnel | cloudflared, ngrok | cloudflared, documented, not run here | Phone microphone access needs a secure context. Neither binary is installed on this VM. |
| Attention / head pose | MediaPipe Face Landmarker, a manual stub | Stub in the demo. MediaPipe was only spiked. | The library imports. A blank image produced no face and no pose matrix. There is no camera on this VM, so the demo does not pretend to see the room. |
| LLM | One vendor SDK, or a small adapter | Adapter for OpenAI, Anthropic, Gemini, xAI, Ollama, and any OpenAI-compatible base URL | The lecturer picks the provider in the UI or in `.env`. No live call was made. Tests use a fake HTTP transport or a scripted tool-calling provider. |
| Transcript | Live Zoom/Meet API, file import | UTF-8 text file import | The assignment says not to integrate with Zoom. |
| Automated tests | pytest, Playwright | pytest 9.2.0 | 25 tests passed on this VM. Playwright is not installed and was not run. |
| Diagrams | PlantUML, Graphviz-only, a drawing tool | PlantUML 1.2025.2 sources plus SVG | Rendered locally with Java and Graphviz. |

Python on the VM: 3.12.3. Demo dependencies are pinned in `requirements.txt`. ggwave, MediaPipe, and NumPy were installed only inside the spike environment. They are not demo dependencies.

## VM spikes

Commands were run from `/workspace` with `.venv/bin/python` unless noted. Outputs below are copied from that run.

### FastAPI hello

A one-file app served `GET /ping` on `127.0.0.1:8765`.

```text
{"pong":true}
```

### HKDF and HMAC

```text
room_key_len 32
keys_differ True
code AEBBQ4IW5Y
fresh TokenVerdict(ok=True, late=False, window=200, reason='ok')
other_room TokenVerdict(ok=False, late=False, window=None, reason='mismatch')
late TokenVerdict(ok=True, late=True, window=200, reason='late')
expired TokenVerdict(ok=False, late=False, window=None, reason='mismatch')
```

Same master secret and same salt derive the same 32-byte key. A different salt derives a different key. The token verifies in its window, verifies as late in the next window, and fails after that and in another room.

### CSV and XLSX

One fixed record (`at = 1700000000`, so the UTC time is 2023-11-14, not "today"):

```text
student_id,name,mode,seat_zone,time_utc,confidence,flags,subnet,device_id
s1,Ada,in_class,front-left,2023-11-14T22:13:20Z,high,late_token,match,dev1

xlsx_bytes 5006 zip True
```

The XLSX bytes start with `PK`, which is the xlsx zip header.

### Ultrasonic FSK

`python -m app.audio_fsk` at 48 kHz, payload `010203040506`, bit length 20 ms, 6 bytes plus an 8-bit preamble (1.120 s):

```text
payload_hex=010203040506
samples=53760 seconds=1.120 rate=48000
clean_decode=010203040506 match=True
noise_0.05_decode=010203040506 match=True
voice_band_3400Hz_x4_decode=None match=False
```

The voice-band row is four cascaded biquad lowpasses at 3400 Hz. It is a simulation of a telephony cut, not a recording of a real phone call. After that filter the decoder returned no payload.

The same framing is implemented in `app/static/fsk.js`. Node and Python decoded each other's WAV files:

```text
js_roundtrip_hex=010203040506
js_roundtrip_match=true
js_base32=AEBAGBAFAY
python_decode_of_js_wav 010203040506
python_base32 AEBAGBAFAY
js_decode_of_py_wav 010203040506
```

`AEBAGBAFAY` is the on-screen code for that payload. This was file I/O, not a speaker and a microphone.

### ggwave (candidate, not selected)

`pip install ggwave` failed first:

```text
fatal error: Python.h: No such file or directory
```

After the VM's `python3-dev` package was installed, import succeeded. Protocol 5 (ggwave's "ultrasound fastest") encoded and decoded `ZK7Q`:

```text
protocol 5 samples 90112 seconds 1.877
decoded b'ZK7Q'
top_freqs_hz [16477.1, 8203.7, 7499.5, 7992.2, 16499.5]
```

The strongest bins in that file sit near 7.5–8.2 kHz and near 16.5 kHz. That is a real round trip, and it is not the 18–20 kHz signal this design uses to make a voice relay unlikely. The demo therefore keeps the small FSK modem, which has no native build and runs in the browser.

### PlantUML

```text
PlantUML version 1.2025.2
java -jar plantuml.jar -tsvg hello.puml
hello.svg  2650 bytes
```

Graphviz on the VM: `dot - graphviz version 2.43.0`. The diagrams in `docs/diagrams/` were rendered the same way (`-tsvg` next to each `.puml` file).

### MediaPipe

`mediapipe` 1.2.0 imports. Its public surface is `Image`, `ImageFormat`, and `tasks` (the old `mp.solutions` API is not in this version). `FaceLandmarker` is present.

The first call failed:

```text
OSError: libEGL.so.1: cannot open shared object file: No such file or directory
```

After `libegl1` was installed, the float16 face landmarker model (3,758,596 bytes, downloaded from the MediaPipe model bucket) loaded. A blank 64×64 image returned:

```text
blank_image_faces 0
matrixes 0
face_landmarker_ok
```

No face, so no facial transformation matrix and no head-pose angle. No camera was opened. The demo does not call MediaPipe. Attention data in the app is accepted only with the label `sample-not-camera`.

### What was not run on this VM

- cloudflared: `command -v cloudflared` printed `cloudflared: not installed`. Same for ngrok.
- Playwright: not installed.
- A live provider call: no API key was available. Connection-test tests use a mocked HTTP transport. Agent tests use a scripted provider that emits tool calls. Those are not model output.
- A speaker, a phone mic, iOS or Android permission prompts, or the university subnet.

### Automated tests

`pytest -v` on this tree: **25 passed**, 1 warning. The warning is Starlette's deprecation notice that `TestClient` still uses `httpx` and would prefer `httpx2`. The full list is in [11-conclusions.md](11-conclusions.md).

## Classroom results (owner)

Leave this blank until the demo. Do not copy the VM rows into it.

| Check | Device / place | Result | Notes |
| --- | --- | --- | --- |
| Mic permission in the student page | iPhone Safari | | |
| Mic permission in the student page | Android Chrome | | |
| Laptop speakers to phone at 18–19 kHz | | | Watch the energy bar. Silence there means the tone is not arriving. |
| On-screen code fallback | | | |
| Remote row stays separate from in-class | | | |
| Anomaly flags (both modes, shared device, late code) | | | |
| University Wi-Fi subnet check | campus SSID | | Set `ZOOMODLE_ALLOWED_SUBNETS` first. A tunnel often hides the campus IP. |
| cloudflared (or similar) HTTPS from campus | | | The phone must open the `https://` URL, not the laptop's `http://127.0.0.1`. |
| Relay attempt (phone call or recording) does not carry the tone | | | |
| Test connection with the real key | lecturer laptop | | Confirm provider, model, latency, and tool-calling. |
| Lesson agent with a real transcript | | | |
| Homework agent | | | |
