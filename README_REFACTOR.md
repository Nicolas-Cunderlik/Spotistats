Refactor notes

New structure (added):
- spotistats/
  - __init__.py
  - config.py
  - utils/logging_config.py
  - services/
    - spotify_service.py
    - ai_service.py
    - scraper_service.py
  - workers/
    - network_worker.py
  - ui/
    - main_window.py
- run.py
- requirements.txt

How to run
1. Install deps from `requirements.txt`.
2. Ensure `venv/auth.env` contains the same keys as before (SPOTIPY_CLIENT_ID, etc.).
3. Run:

```bash
python run.py
```

Notes
- Logging is configured to console and `spotistats.log`.
- The scraper is controlled by `ENABLE_SCRAPER` env var (set to 1 to enable).
- Network tasks run in a worker thread to avoid UI stalls.

Next debugging steps
- Start with `ENABLE_SCRAPER=0` to confirm UI responsiveness.
- Re-enable scraper and check `spotistats.log` for HTTP/500 details.
