"""Manual browser run (not part of the pytest suite).

Start the server first, with the in-class range open to localhost:
    ZOOMODLE_LECTURER_KEY=<key> ZOOMODLE_CAMPUS_RANGES=127.0.0.1/32 ZOOMODLE_PORT=8765 python -m app.main
Then:
    pip install playwright && python -m playwright install chromium
    ZM_KEY=<key> python tests/manual/browser_run.py tests/fixtures/roster_sample.csv /tmp/zm-run

Checks: lecturer sign-in + greeting, lesson + roster, live barcode frames,
two remote students submit homework, a review without a key is refused,
the lecturer sees both submissions, no console errors except that refusal."""
import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("ZM_BASE", "http://127.0.0.1:8765")
KEY = os.environ["ZM_KEY"]
ROSTER = sys.argv[1]
OUT = sys.argv[2]
FRAMES = os.path.join(OUT, "frames")
os.makedirs(FRAMES, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("ZM_CHROME") or None)
    lect = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
    errors = []
    lect.on("console", lambda m: m.type == "error" and errors.append("lect: " + m.text))
    lect.goto(BASE + "/")
    lect.fill("#lecturer-key", KEY)
    lect.click("#login-form button[type=submit]")
    lect.wait_for_selector("#home:not([hidden])")
    print("greeting:", lect.inner_text("#greeting"))
    lect.click("#new-room")
    lect.wait_for_selector("#room:not([hidden])")
    lect.set_input_files("#roster-file", ROSTER)
    time.sleep(1.5)
    print("roster:", lect.inner_text("#roster-state"))
    room_url = lect.inner_text("#join-link")
    print("join:", room_url)
    # Barcode frames for the GIF: the live QR + shimmer box.
    box = lect.locator("#live-qr").locator("xpath=..")
    box.scroll_into_view_if_needed()
    time.sleep(1)
    t0 = time.time()
    i = 0
    while time.time() - t0 < 4.0:
        box.screenshot(path=f"{FRAMES}/f{i:04d}.png")
        i += 1
    print("frames:", i, "in", round(time.time() - t0, 2), "s")

    students = []
    for name in ("דנה לוי", "יוסי כהן"):
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        s = ctx.new_page()
        s.on("console", lambda m, n=name: m.type == "error" and errors.append(n + ": " + m.text))
        s.goto(room_url)
        s.wait_for_selector("#step-name:not([hidden])")
        s.select_option("#name", label=name)
        s.click("#go-remote")
        s.wait_for_selector("#sub-send", state="visible", timeout=10000)
        s.fill("#sub-text", f"פרספטרון: סכום משוקלל ופונקציית סף. ({name})")
        s.click("#sub-send")
        s.wait_for_function("document.querySelector('#sub-state').textContent.includes('הוגש')", timeout=5000)
        print(name, "->", s.inner_text("#sub-state"))
        students.append(s)
    s = students[0]
    s.click("text=קבל ביקורת AI")
    s.fill("#rv-model", "gpt-4o-mini")
    s.click("#sub-review")
    s.wait_for_function("document.querySelector('#sub-review-out').textContent.length > 0 && !document.querySelector('#sub-review-out').textContent.includes('בודק')", timeout=5000)
    print("student review without key ->", s.inner_text("#sub-review-out"))
    s.screenshot(path=f"{OUT}/student.png", full_page=True)

    time.sleep(3)
    print("lecturer submissions:", lect.inner_text("#submissions").replace("\n", " | "))
    print("conflicts card:", lect.inner_text("#conflicts"))
    lect.screenshot(path=f"{OUT}/lecturer.png", full_page=True)
    print("console errors:", errors or "none")
    browser.close()
