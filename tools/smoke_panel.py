"""Optional fresh-checkout browser check; no raw sockets or device commands."""
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
proc = subprocess.Popen([sys.executable, str(root/'panel_server.py'), '--port', str(port)], cwd=root)
url = f'http://127.0.0.1:{port}'
try:
    for _ in range(50):
        try:
            with urllib.request.urlopen(url+'/api/bootstrap', timeout=1) as response:
                boot = json.load(response)
            break
        except (OSError, urllib.error.URLError):
            time.sleep(.1)
    else:
        raise RuntimeError('Panel did not start')
    assert len(boot['catalog']) >= 25
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(url, wait_until='networkidle')
        for tab in ('studio', 'telemetry', 'topology', 'speed', 'learn', 'experiments', 'wire'):
            page.locator(f'.nav[data-tab="{tab}"]').click()
        assert page.locator('#sessionSource option').count() == 1 + len(boot['replays'])
        page.set_viewport_size({'width':390, 'height':844})
        page.locator('.nav[data-tab="topology"]').click()
        assert not errors, errors
        browser.close()
    print('Panel smoke check passed: all tabs, replay availability, mobile, no JavaScript errors')
finally:
    proc.terminate()
    proc.wait(timeout=5)
