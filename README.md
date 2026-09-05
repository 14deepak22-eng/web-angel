# NSE Stock Screener — full web version

A real, always-on website: password-protected, backed by a small SQLite
database, auto-refreshing prices from Angel One during market hours, and
editable from your phone or laptop from anywhere.

```
Angel One SmartAPI ──(every 30 min, market hours)──► APScheduler ──► SQLite
                                                                        │
                                                                        ▼
                                                    FastAPI (auth + API + static files)
                                                                        │
                                                                        ▼
                                                         dashboard.html (your browser)
```

## Run it locally first

1. **Install dependencies** (Python 3.9+):
   ```
   pip install -r requirements.txt
   ```

2. **Configure**:
   ```
   cp .env.example .env
   ```
   Fill in:
   - `DASHBOARD_PASSWORD` — whatever you want to log in with
   - `SESSION_SECRET` — any long random string (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`)
   - `ANGEL_API_KEY`, `ANGEL_CLIENT_CODE`, `ANGEL_MPIN`, `ANGEL_TOTP_SECRET` — see the Angel One
     setup steps in the earlier `angel-one-screener` package's README if you haven't done this yet

3. **Start it**:
   ```
   cd backend
   uvicorn main:app --reload --port 8000
   ```
   Open http://localhost:8000 — you'll be redirected to a login page. Sign in
   with `DASHBOARD_PASSWORD`, then use **+ Add Stock** to add your first
   ticker (you'll need its exact Angel One trading symbol, usually `SYMBOL-EQ`).

4. Click **Refresh Now** to pull live prices immediately, or just wait — the
   scheduler refreshes everything automatically every `REFRESH_INTERVAL_MINUTES`
   during NSE market hours (9:15–15:30 IST, weekdays).

Fundamentals (ROCE, P/E, debt, etc.) still need to be entered by hand in each
stock's detail panel — Angel One's API doesn't provide financial-statement data.

## Deploy it as a real website

**Render (recommended for a first deploy — free tier available):**

1. Push this folder to a GitHub repo (or use Render's "Deploy from a zip"-style flow)
2. In Render: **New → Blueprint**, point it at your repo — it'll read `render.yaml` automatically
3. Fill in the secret env vars it asks for (`DASHBOARD_PASSWORD`, Angel One credentials)
4. Deploy — Render gives you a free HTTPS URL and keeps the service running continuously

**Railway / PythonAnywhere** work similarly — the key requirements are: run
`uvicorn main:app --host 0.0.0.0 --port $PORT` from the `backend/` folder, set
the same environment variables, and give the SQLite file (`screener.db`) a
persistent disk so it survives restarts and redeploys.

## Things worth knowing before you rely on this

- **This is single-user.** One password protects the whole dashboard. Don't
  reuse a password you use elsewhere, and don't share the URL.
- **Session login lasts 7 days** by default (`auth.py` → `MAX_AGE_SECONDS`).
- **The scheduler logs in fresh on every refresh cycle** rather than caching
  the Angel One session token — simple and reliable, but means slightly more
  login calls than strictly necessary. Fine at a 30-minute interval; if you
  push the interval much lower, consider caching the session between runs.
- **Free hosting tiers often sleep when idle** — if Render's free tier spins
  your service down after inactivity, the scheduler won't fire until the next
  request wakes it up. A paid "always-on" tier (or a $5–7/mo VPS) avoids this
  if you want genuinely continuous refreshing.
- **Back up `screener.db` occasionally** — it holds all your manually-entered
  fundamentals, hypotheses, and portfolio thinking. Losing the disk loses that.
