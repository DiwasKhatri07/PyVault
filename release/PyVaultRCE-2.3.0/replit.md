# PyVault — Remote Code Execution & Hosting Platform

A secure remote code hosting and execution platform. Users paste Python scripts, receive a unique 21-digit hex Session ID, and execute code remotely via the `PyVaultRCE` PyPI module — without the source ever being exposed to the client.

## Run & Operate

- `cd artifacts/rce-platform && python app.py` — run Flask server (port 5000)
- Workflow name: `artifacts/rce-platform: web`
- Database: `artifacts/rce-platform/sessions.db` (SQLite, auto-created on first run)
- **Admin token** is printed to server console on first startup — look for `[PyVault] ADMIN ACCESS TOKEN`

## Stack

- **Backend**: Python 3.11, Flask 3
- **Database**: SQLite (via Python `sqlite3` — no ORM)
- **Frontend**: Vanilla JS + CodeMirror 5 (Dracula theme)
- **PyPI Module**: `pypi-module/pyvaultrce/` — published as `PyVaultRCE` on PyPI

## Where things live

- `artifacts/rce-platform/app.py` — Flask app (routes, DB, API)
- `artifacts/rce-platform/templates/` — Jinja2 HTML templates (index, admin_login, admin, admin_view)
- `artifacts/rce-platform/static/` — CSS + JS assets
- `artifacts/rce-platform/sessions.db` — SQLite database (auto-created)
- `pypi-module/pyvaultrce/` — PyPI package source (`PyVaultRCE` on PyPI)
- `pypi-module/codemanager/` — legacy package (kept for backward compat)
- `pypi-module/setup.py` — package installer

## API Endpoints

### Public (no auth)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Paste UI |
| GET | `/admin/login` | Admin login page |
| POST | `/admin/login` | Submit token → set session cookie |
| GET | `/admin/logout` | Clear session |
| POST | `/pyv/save` | Upload code (JSON or multipart .py) → returns Session ID |
| POST | `/pyv/upload` | Multipart .py file upload |
| GET | `/pyv/get/<session_id>` | Fetch code + increment `execution_count` |
| GET | `/pyv/info/<session_id>` | Session metadata only (no exec count increment) |
| GET | `/pyv/stats` | Total sessions & executions |

### Admin-only (session cookie for web, `X-Admin-Token` header for API)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin` | Session monitor |
| GET | `/admin/view/<session_id>` | View + edit stored code |
| PUT | `/pyv/edit/<session_id>` | Replace stored code — requires `X-Admin-Token` header |
| DELETE | `/pyv/delete/<session_id>` | Delete session — requires `X-Admin-Token` header |

## Database Schema

```sql
CREATE TABLE sessions (
    session_id      TEXT PRIMARY KEY,
    python_code     TEXT NOT NULL,
    execution_count INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
    -- stores: admin_token
);
```

## PyVaultRCE Module Usage

```bash
pip install PyVaultRCE
```

```python
from pyvaultrce import CodeManager

sid = CodeManager.enc("script.py")             # upload local file → Session ID
sid = CodeManager.enc_url("https://...")        # upload from paste URL → Session ID
CodeManager.run(sid)                            # execute remotely
CodeManager.info(sid)                           # metadata (no exec count bump)
CodeManager.ping()                              # check server is up
CodeManager.edit(sid, "v2.py", admin_token)    # admin-only update
```

```bash
export PYVAULT_URL=https://your-server.replit.app
```

## Architecture decisions

- **SQLite over PostgreSQL**: zero-config, single-file DB ideal for this use case.
- **21-char hex IDs**: `secrets.token_hex(11)[:21]` — cryptographically random, URL-safe.
- **`/pyv/` prefix**: avoids collision with the Express API server which owns `/api/`.
- **Session-cookie admin auth**: Flask `session` signed with `SESSION_SECRET` env var.
- **`X-Admin-Token` for API edit/delete**: allows curl-based admin without a browser session.
- **Admin token in DB**: auto-generated on first run, stored in `config` table, printed to console once.
- **No public edit endpoint**: `PUT /pyv/edit` requires `X-Admin-Token` — random users cannot modify code.
- **10,000-char limit**: enforced on both server and client editor.
- **`exec()` in isolated namespace**: code runs in `{"__name__": "__pyvault__"}`, not caller globals.

## Security notes

- The Session ID IS the secret — anyone who has it can execute the stored code.
- `/pyv/get/<id>` is intentionally public: execution requires the code to be transmitted to the client.
- Edit and delete are locked behind admin token — users can only upload, not modify.
- Admin panel protected by session cookie; token never appears in URLs.

## User preferences

_Populate as you build._

## Gotchas

- Session IDs are exactly 21 lowercase hex characters. Validation is strict on server and client.
- `execution_count` increments on every `/pyv/get/<id>` call. Use `/pyv/info/<id>` for metadata-only lookups.
- `python app.py` must be run from inside `artifacts/rce-platform/` so `sessions.db` resolves correctly.
- Flask dev server only — use gunicorn/waitress for production.
- PyPI package name is `PyVaultRCE`; Python import is `from pyvaultrce import CodeManager`.
