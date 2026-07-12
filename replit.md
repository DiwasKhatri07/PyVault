# PyVault — Remote Code Execution & Hosting Platform

A secure remote code hosting and execution platform. Users paste Python scripts, receive a unique 21-digit hex Session ID, and execute code remotely via the `codemanager` PyPI module — without the source ever being exposed to the client.

## Run & Operate

- `cd artifacts/rce-platform && python app.py` — run Flask server (port 5000)
- Workflow name: `PyVault — RCE Platform`
- Database: `artifacts/rce-platform/sessions.db` (SQLite, auto-created on first run)

## Stack

- **Backend**: Python 3.11, Flask 3
- **Database**: SQLite (via Python `sqlite3` — no ORM)
- **Frontend**: Vanilla JS + CodeMirror 5 (Dracula theme)
- **PyPI Module**: `pypi-module/` — installable via `pip install .`

## Where things live

- `artifacts/rce-platform/app.py` — Flask app (routes, DB, API)
- `artifacts/rce-platform/templates/` — Jinja2 HTML templates
- `artifacts/rce-platform/static/` — CSS + JS assets
- `artifacts/rce-platform/sessions.db` — SQLite database (auto-created)
- `pypi-module/codemanager/` — PyPI package source
- `pypi-module/setup.py` — package installer

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Paste UI — upload code, get Session ID |
| GET | `/admin` | Admin panel — list all sessions |
| GET | `/admin/view/<session_id>` | View stored code for a session |
| POST | `/api/save` | Upload code → returns 21-char hex Session ID |
| GET | `/api/get/<session_id>` | Fetch code + increment execution_count |
| PUT | `/api/edit/<session_id>` | Replace stored code for existing session |
| DELETE | `/api/delete/<session_id>` | Delete a session |
| GET | `/api/stats` | Total sessions & execution counts |

## Database Schema

```sql
CREATE TABLE sessions (
    session_id      TEXT PRIMARY KEY,       -- 21-char hex string
    python_code     TEXT NOT NULL,          -- large payload supported
    execution_count INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
```

## PyPI Module Usage

```bash
pip install ./pypi-module   # install locally
# or publish to PyPI and: pip install codemanager
```

```python
from codemanager import CodeManager

session_id = CodeManager.enc("my_script.py")    # upload → get Session ID
CodeManager.run(session_id)                       # execute remotely
CodeManager.edit(session_id, "updated.py")        # update stored code
```

Set `PYVAULT_URL` env var to point at your server:
```bash
export PYVAULT_URL=https://your-server.replit.app
```

## Architecture decisions

- **SQLite over PostgreSQL**: zero-config, single-file DB ideal for this use case; no connection pooling overhead.
- **21-char hex IDs**: `secrets.token_hex(11)[:21]` — cryptographically random, collision-resistant, URL-safe.
- **`exec()` in isolated namespace**: remote code runs in a clean `{}` namespace, not the caller's globals, limiting side-effects.
- **No auth on `/api/get`**: by design — the Session ID IS the secret. Keep it private.
- **CodeMirror 5 (CDN)**: no build step required on the frontend; Dracula theme matches the dark UI.

## Product

- **Paste UI** (`/`): Monaco-style Python editor, save code, get Session ID, copy-to-clipboard, look-up existing sessions.
- **Admin Panel** (`/admin`): live stats (total sessions, executions), searchable table, delete sessions, view stored code.
- **PyPI Module**: `CodeManager.enc()` / `.run()` / `.edit()` — full remote RCE lifecycle with rich error messages.

## User preferences

_Populate as you build._

## Gotchas

- Session IDs are exactly 21 lowercase hex characters. Validation is strict on both server and client.
- `execution_count` increments on every `GET /api/get/<id>` call, including look-ups from the web UI.
- `python app.py` must be run from inside `artifacts/rce-platform/` so the relative `sessions.db` path resolves correctly.
- Flask dev server only — use gunicorn/waitress for production.
