# Cleanup validation

Validated on Linux with Python 3.10 in a fresh virtual environment:

- Dependency installation from `requirements-dev.txt` succeeded.
- `python -m unittest discover -v`: 17 tests passed, without live devices or private config.
- `python tools/smoke_panel.py`: all six panel tabs, replay availability, mobile viewport, and no JavaScript errors.
- Live controller refuses to start without explicit interface and target parameters.
- DHCP imports and unit tests work without config.json; runtime requires initialized credentials and an explicit interface.
- Source scan found no original host paths, client/device MACs, private SSID password, captures, session tokens, or live config.

No live onboarding or speed test was repeated from this clean copy. Physical migration to the new host remains a separate step. The original working lab and evidence were preserved outside this repository.

The browser check starts and stops a temporary loopback panel. It is not a full hardware integration test. Dependencies are lower-bounded rather than locked; record exact versions for reproducible future measurements.
