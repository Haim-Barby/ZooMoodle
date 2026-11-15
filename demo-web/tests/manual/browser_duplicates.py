"""Manual browser run of the duplicate-name flow (not part of the pytest suite).

Two phones check in class with the same name -> both re-pick the same name ->
one-time code on the lecturer dashboard -> the lecturer types it on the real
student's phone, which gets the name; the other phone is removed from the name
and can start over with another name.
The camera is replaced by feeding the student page the codes really shown on
the lecturer screen for >2 s. Start the server as in browser_run.py, then:
    ZM_KEY=<key> python tests/manual/browser_duplicates.py tests/fixtures/roster_sample.csv /tmp/zm-dup"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("ZM_BASE", "http://127.0.0.1:8765")
KEY = os.environ["ZM_KEY"]
ROSTER, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)

GRAB = """async () => { const out = []; const t0 = Date.now();
  while (Date.now() - t0 < 2600) { const b = await api('/api/rooms/' + state.roomId + '/barcode'); if (!out.includes(b.code)) out.push(b.code); await new Promise(r => setTimeout(r, 120)); }
  return out; }"""

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("ZM_CHROME") or None)
    lect = browser.new_page(viewport={"width": 1280, "height": 900})
    lect.goto(BASE + "/")
    lect.fill("#lecturer-key", KEY)
    lect.click("#login-form button[type=submit]")
    lect.wait_for_selector("#home:not([hidden])")
    lect.click("#new-room")
    lect.wait_for_selector("#room:not([hidden])")
    lect.set_input_files("#roster-file", ROSTER)
    time.sleep(1.2)
    url = lect.inner_text("#join-link")

    phones = []
    for i, zone in enumerate(("front-left", "back-right")):
        s = browser.new_context(viewport={"width": 390, "height": 844}).new_page()
        s.goto(url)
        s.wait_for_selector("#step-name:not([hidden])")
        s.select_option("#name", label="דנה לוי")
        s.click("#go-class")
        s.wait_for_selector("#step-scan:not([hidden])")
        codes = lect.evaluate(GRAB)
        res = s.evaluate("async (codes) => { const r = await call(R('/barcode'), 'POST', { codes }); render(r); return r.state; }", codes)
        print(f"phone {i}: {len(codes)} live codes -> {res}")
        if res == "needs_area":
            s.click(f"[data-zone={zone}]")
        phones.append(s)
    time.sleep(2.5)
    for i, s in enumerate(phones):
        print(f"phone {i} popup visible:", s.is_visible("#repick"))
        s.select_option("#repick-name", label="דנה לוי")
        s.click("#repick-send")
        time.sleep(0.5)
    time.sleep(2.5)
    for i, s in enumerate(phones):
        print(f"phone {i}:", s.inner_text("#wait-title"), "| code box:", s.is_visible("#code-box"))
    time.sleep(2.5)
    conflict = lect.inner_text("#conflicts")
    print("lecturer conflicts:", conflict.replace("\n", " | "))
    lect.screenshot(path=f"{OUT}/lecturer-code.png", full_page=True)
    code = lect.inner_text(".demo-code").strip()
    phones[1].screenshot(path=f"{OUT}/phone-code.png")
    phones[0].fill("#code", code)
    phones[0].click("#code-send")
    time.sleep(2.5)
    print("phone 0 after code:", phones[0].inner_text("#welcome") if phones[0].is_visible("#welcome") else phones[0].inner_text("#wait-title"))
    print("phone 1:", phones[1].inner_text("#wait-title"), "| start over:", phones[1].is_visible("#start-over"))
    phones[1].screenshot(path=f"{OUT}/phone-rejected.png")
    phones[1].click("#start-over")
    print("phone 1 after start over -> name step:", phones[1].is_visible("#step-name"))
    time.sleep(2.5)
    print("dashboard:", lect.inner_text("#c-in"), "in class,", lect.inner_text("#c-conflicts"), "conflicts")
    browser.close()
