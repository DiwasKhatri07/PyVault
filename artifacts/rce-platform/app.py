import hashlib
import os
import secrets
import sqlite3
import traceback
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask, request, jsonify, render_template,
    abort, g, session, redirect, url_for
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from cryptography.fernet import Fernet, InvalidToken

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", secrets.token_hex(32))

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri="memory://",
    default_limits=[],
)

DATABASE = os.path.join(os.path.dirname(__file__), "sessions.db")
MAX_CODE_LINES = 10_000

_CIPHER_KEY = os.environ.get(
    "PYVAULT_CIPHER_KEY",
    "aK3vytd8SaduKCt6D8-yL-DA2pDNOGiNLfZhnBPJebo="
).encode()
_cipher = Fernet(_CIPHER_KEY)


# ── Crypto helpers ─────────────────────────────────────────────────────────────

def _encrypt_code(code: str) -> str:
    return _cipher.encrypt(code.encode("utf-8")).decode("ascii")


def _decrypt_code(data: str) -> str:
    try:
        return _cipher.decrypt(data.encode("ascii")).decode("utf-8")
    except (InvalidToken, Exception):
        return data


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _make_owner_token() -> str:
    return secrets.token_urlsafe(24)


# ── Time helpers ───────────────────────────────────────────────────────────────

def _is_expired(expires_at) -> bool:
    if not expires_at:
        return False
    try:
        return datetime.utcnow() > datetime.fromisoformat(str(expires_at))
    except Exception:
        return False


def _max_exec_reached(execution_count: int, max_executions) -> bool:
    if not max_executions:
        return False
    try:
        me = int(max_executions)
        return me > 0 and execution_count >= me
    except Exception:
        return False


def _expiry_from_hours(hours) -> str | None:
    try:
        h = float(hours)
        if h <= 0:
            return None
        return (datetime.utcnow() + timedelta(hours=h)).isoformat()
    except Exception:
        return None


# ── DB ─────────────────────────────────────────────────────────────────────────

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id        TEXT PRIMARY KEY,
                python_code       TEXT NOT NULL,
                execution_count   INTEGER NOT NULL DEFAULT 0,
                created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                owner_token_hash  TEXT,
                expires_at        TEXT,
                max_executions    INTEGER DEFAULT 0,
                label             TEXT DEFAULT ''
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        db.commit()

        for col, defval in [
            ("owner_token_hash", "NULL"),
            ("expires_at",       "NULL"),
            ("max_executions",   "0"),
            ("label",            "''"),
        ]:
            try:
                db.execute(f"ALTER TABLE sessions ADD COLUMN {col} TEXT DEFAULT {defval}")
                db.commit()
            except Exception:
                pass

        row = db.execute("SELECT value FROM config WHERE key='admin_token'").fetchone()
        if not row:
            token = secrets.token_hex(11)[:21]
            db.execute(
                "INSERT INTO config (key, value) VALUES ('admin_token', ?)", (token,)
            )
            db.commit()
            print(f"\n{'='*56}", flush=True)
            print(f"[PyVault] ADMIN ACCESS TOKEN  :  {token}", flush=True)
            print(f"[PyVault] Visit /admin/login and enter this token.", flush=True)
            print(f"{'='*56}\n", flush=True)
        else:
            print("[PyVault] Admin token loaded.", flush=True)


def _get_admin_token():
    db = get_db()
    row = db.execute("SELECT value FROM config WHERE key='admin_token'").fetchone()
    return row["value"] if row else None


# ── Auth decorators ────────────────────────────────────────────────────────────

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_authed"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


def _is_admin_request() -> bool:
    if session.get("admin_authed"):
        return True
    provided = request.headers.get("X-Admin-Token", "").strip()
    return bool(provided and provided == _get_admin_token())


def require_admin_api(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _is_admin_request():
            return jsonify({"error": "Admin authentication required."}), 403
        return f(*args, **kwargs)
    return decorated


# ── Misc helpers ───────────────────────────────────────────────────────────────

def generate_session_id():
    while True:
        sid = secrets.token_hex(11)[:21]
        db = get_db()
        row = db.execute("SELECT 1 FROM sessions WHERE session_id = ?", (sid,)).fetchone()
        if not row:
            return sid


def _validate_sid(session_id):
    return (
        isinstance(session_id, str)
        and len(session_id) == 21
        and all(c in "0123456789abcdef" for c in session_id)
    )


def _validate_code(code):
    if not code or not code.strip():
        return False, "No Python code provided."
    lines = code.splitlines()
    if len(lines) > MAX_CODE_LINES:
        return False, f"Code exceeds the {MAX_CODE_LINES:,}-line limit ({len(lines):,} lines submitted)."
    return True, None


def _session_status(row) -> str:
    if _is_expired(row["expires_at"]):
        return "expired"
    if _max_exec_reached(row["execution_count"], row["max_executions"]):
        return "maxed"
    return "active"


# ── Public pages ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── Admin auth ─────────────────────────────────────────────────────────────────

@app.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("10 per minute; 30 per hour", error_message="Too many login attempts.")
def admin_login():
    if session.get("admin_authed"):
        return redirect(url_for("admin"))
    error = None
    if request.method == "POST":
        token = request.form.get("token", "").strip()
        if not token:
            error = "Access token is required."
        elif len(token) > 64:
            error = "Invalid access token."
        elif token == _get_admin_token():
            session["admin_authed"] = True
            session.permanent = False
            return redirect(url_for("admin"))
        else:
            error = "Invalid access token."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


# ── Protected admin pages ──────────────────────────────────────────────────────

@app.route("/admin")
@require_admin
def admin():
    db = get_db()
    rows = db.execute(
        "SELECT session_id, execution_count, created_at, "
        "LENGTH(python_code) AS encrypted_size, "
        "expires_at, max_executions, label "
        "FROM sessions ORDER BY created_at DESC"
    ).fetchall()
    sessions_list = []
    for r in rows:
        d = dict(r)
        d["status"] = _session_status(r)
        sessions_list.append(d)

    total_expired  = sum(1 for s in sessions_list if s["status"] in ("expired", "maxed"))
    total_active   = len(sessions_list) - total_expired

    return render_template(
        "admin.html",
        sessions=sessions_list,
        admin_token=_get_admin_token(),
        total_active=total_active,
        total_expired=total_expired,
    )


@app.route("/admin/view/<session_id>")
@require_admin
def admin_view(session_id):
    if not _validate_sid(session_id):
        abort(400)
    db = get_db()
    row = db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if not row:
        abort(404)
    data = dict(row)
    data["python_code"] = _decrypt_code(data["python_code"])
    data["status"]      = _session_status(row)
    data["line_count"]  = len(data["python_code"].splitlines())
    return render_template("admin_view.html", session=data, admin_token=_get_admin_token())


# ── Public API ─────────────────────────────────────────────────────────────────

def _do_save(code: str, expires_in_hours=None, max_executions=0):
    ok, err = _validate_code(code)
    if ok is False:
        return None, None, err

    owner_token      = _make_owner_token()
    owner_token_hash = _hash_token(owner_token)
    encrypted        = _encrypt_code(code)
    session_id       = generate_session_id()
    expires_at       = _expiry_from_hours(expires_in_hours) if expires_in_hours else None

    try:
        me = max(0, int(max_executions or 0))
    except Exception:
        me = 0

    db = get_db()
    db.execute(
        "INSERT INTO sessions "
        "(session_id, python_code, execution_count, created_at, owner_token_hash, expires_at, max_executions, label) "
        "VALUES (?, ?, 0, ?, ?, ?, ?, '')",
        (session_id, encrypted, datetime.utcnow().isoformat(),
         owner_token_hash, expires_at, me),
    )
    db.commit()
    return session_id, owner_token, None


@app.route("/pyv/save", methods=["POST"])
@limiter.limit("30 per minute; 200 per hour")
def api_save():
    ct = request.content_type or ""
    if "multipart" in ct:
        f = request.files.get("file")
        if not f:
            return jsonify({"error": "No file provided in multipart upload."}), 400
        if not f.filename.endswith(".py"):
            return jsonify({"error": "Only .py files are accepted."}), 400
        raw  = f.read(1_000_000)
        code = raw.decode("utf-8", errors="replace")
        expires_in_hours = request.form.get("expires_in_hours")
        max_executions   = request.form.get("max_executions", 0)
    elif "application/json" in ct:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"error": "Invalid JSON body."}), 400
        code = data.get("code", "")
        if not isinstance(code, str):
            return jsonify({"error": "'code' must be a string."}), 400
        expires_in_hours = data.get("expires_in_hours")
        max_executions   = data.get("max_executions", 0)
    else:
        return jsonify({"error": "Content-Type must be application/json or multipart/form-data."}), 415

    sid, owner_token, err = _do_save(code, expires_in_hours, max_executions)
    if err:
        return jsonify({"error": err}), 400

    resp = {
        "session_id":   sid,
        "owner_token":  owner_token,
        "message":      "Code saved successfully. Store your owner_token — it will never be shown again.",
    }
    if expires_in_hours:
        resp["expires_at"] = _expiry_from_hours(expires_in_hours)
    return jsonify(resp), 201


@app.route("/pyv/upload", methods=["POST"])
@limiter.limit("30 per minute; 200 per hour")
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided."}), 400
    f = request.files["file"]
    if not f.filename or not f.filename.endswith(".py"):
        return jsonify({"error": "Only .py files are accepted."}), 400
    raw  = f.read(1_000_000)
    code = raw.decode("utf-8", errors="replace")

    sid, owner_token, err = _do_save(code)
    if err:
        return jsonify({"error": err}), 400

    return jsonify({
        "session_id":  sid,
        "owner_token": owner_token,
        "message":     "File uploaded successfully.",
    }), 201


@app.route("/pyv/get/<session_id>", methods=["GET"])
@limiter.limit("120 per minute")
def api_get(session_id):
    if not _validate_sid(session_id):
        return jsonify({"error": "Invalid session ID."}), 400
    db = get_db()
    row = db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if not row:
        return jsonify({"error": f"Session '{session_id}' not found."}), 404

    if _is_expired(row["expires_at"]):
        return jsonify({
            "error":   "This session has expired and is no longer available.",
            "expired": True,
        }), 410

    if _max_exec_reached(row["execution_count"], row["max_executions"]):
        return jsonify({
            "error":  f"This session has reached its maximum execution limit of {row['max_executions']}.",
            "maxed":  True,
        }), 410

    db.execute(
        "UPDATE sessions SET execution_count = execution_count + 1 WHERE session_id = ?",
        (session_id,),
    )
    db.commit()
    return jsonify({
        "session_id":      session_id,
        "code":            row["python_code"],
        "execution_count": row["execution_count"] + 1,
        "created_at":      row["created_at"],
    })


@app.route("/pyv/info/<session_id>", methods=["GET"])
@limiter.limit("60 per minute")
def api_info(session_id):
    if not _validate_sid(session_id):
        return jsonify({"error": "Invalid session ID."}), 400
    db = get_db()
    row = db.execute(
        "SELECT session_id, execution_count, created_at, LENGTH(python_code) AS encrypted_size, "
        "expires_at, max_executions "
        "FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        return jsonify({"error": f"Session '{session_id}' not found."}), 404

    status = _session_status(row)
    return jsonify({
        "session_id":      session_id,
        "execution_count": row["execution_count"],
        "created_at":      row["created_at"],
        "expires_at":      row["expires_at"],
        "max_executions":  row["max_executions"],
        "status":          status,
    })


@app.route("/pyv/stats", methods=["GET"])
@limiter.limit("30 per minute")
def api_stats():
    db = get_db()
    total      = db.execute("SELECT COUNT(*) AS cnt FROM sessions").fetchone()["cnt"]
    total_exec = db.execute("SELECT SUM(execution_count) AS s FROM sessions").fetchone()["s"] or 0
    return jsonify({"total_sessions": total, "total_executions": total_exec})


# ── Owner self-service API ─────────────────────────────────────────────────────

def _verify_owner(session_id: str):
    """Returns (row, error_response). error_response is None if auth OK."""
    provided = request.headers.get("X-Owner-Token", "").strip()
    if not provided:
        return None, (jsonify({"error": "X-Owner-Token header is required."}), 403)
    db = get_db()
    row = db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if not row:
        return None, (jsonify({"error": f"Session '{session_id}' not found."}), 404)
    if not row["owner_token_hash"]:
        return None, (jsonify({"error": "This session has no owner token set."}), 403)
    if _hash_token(provided) != row["owner_token_hash"]:
        return None, (jsonify({"error": "Invalid owner token."}), 403)
    return row, None


@app.route("/pyv/my/<session_id>", methods=["DELETE"])
@limiter.limit("20 per minute")
def api_owner_delete(session_id):
    if not _validate_sid(session_id):
        return jsonify({"error": "Invalid session ID."}), 400
    row, err = _verify_owner(session_id)
    if err:
        return err
    db = get_db()
    db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    db.commit()
    return jsonify({"message": f"Session '{session_id}' deleted successfully."})


@app.route("/pyv/my/<session_id>", methods=["PUT"])
@limiter.limit("20 per minute")
def api_owner_edit(session_id):
    if not _validate_sid(session_id):
        return jsonify({"error": "Invalid session ID."}), 400
    row, err = _verify_owner(session_id)
    if err:
        return err
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON body."}), 400
    new_code = data.get("code", "")
    if not isinstance(new_code, str):
        return jsonify({"error": "'code' must be a string."}), 400
    ok, verr = _validate_code(new_code)
    if not ok:
        return jsonify({"error": verr}), 400
    encrypted = _encrypt_code(new_code)
    db = get_db()
    db.execute("UPDATE sessions SET python_code = ? WHERE session_id = ?", (encrypted, session_id))
    db.commit()
    return jsonify({"session_id": session_id, "message": "Code updated successfully."})


# ── Admin-only API ─────────────────────────────────────────────────────────────

@app.route("/pyv/edit/<session_id>", methods=["PUT"])
@require_admin_api
def api_edit(session_id):
    if not _validate_sid(session_id):
        return jsonify({"error": "Invalid session ID."}), 400
    db = get_db()
    if not db.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)).fetchone():
        return jsonify({"error": f"Session '{session_id}' not found."}), 404
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON body."}), 400
    new_code = data.get("code", "")
    if not isinstance(new_code, str):
        return jsonify({"error": "'code' must be a string."}), 400
    ok, err = _validate_code(new_code)
    if not ok:
        return jsonify({"error": err}), 400
    encrypted = _encrypt_code(new_code)
    db.execute("UPDATE sessions SET python_code = ? WHERE session_id = ?", (encrypted, session_id))
    db.commit()
    return jsonify({"session_id": session_id, "message": "Code updated successfully."})


@app.route("/pyv/delete/<session_id>", methods=["DELETE"])
@require_admin_api
def api_delete(session_id):
    if not _validate_sid(session_id):
        return jsonify({"error": "Invalid session ID."}), 400
    db = get_db()
    result = db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    db.commit()
    if result.rowcount == 0:
        return jsonify({"error": "Session not found."}), 404
    return jsonify({"message": "Session deleted successfully."})


@app.route("/pyv/admin/set/<session_id>", methods=["PATCH"])
@require_admin_api
def api_admin_set(session_id):
    if not _validate_sid(session_id):
        return jsonify({"error": "Invalid session ID."}), 400
    db = get_db()
    if not db.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)).fetchone():
        return jsonify({"error": "Session not found."}), 404
    data = request.get_json(silent=True) or {}

    updates = []
    params  = []

    if "label" in data:
        updates.append("label = ?")
        params.append(str(data["label"])[:200])

    if "max_executions" in data:
        try:
            me = max(0, int(data["max_executions"]))
        except Exception:
            me = 0
        updates.append("max_executions = ?")
        params.append(me)

    if "expires_at" in data:
        ea = data["expires_at"]
        if ea in (None, "", "never"):
            updates.append("expires_at = NULL")
        else:
            updates.append("expires_at = ?")
            params.append(str(ea))

    if "expires_in_hours" in data:
        ea = _expiry_from_hours(data["expires_in_hours"])
        if ea is None:
            updates.append("expires_at = NULL")
        else:
            updates.append("expires_at = ?")
            params.append(ea)

    if not updates:
        return jsonify({"error": "No fields to update."}), 400

    params.append(session_id)
    db.execute(f"UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?", params)
    db.commit()
    return jsonify({"session_id": session_id, "message": "Session settings updated."})


@app.route("/pyv/admin/cleanup", methods=["POST"])
@require_admin_api
def api_admin_cleanup():
    db    = get_db()
    now   = datetime.utcnow().isoformat()
    rows  = db.execute("SELECT session_id, max_executions, execution_count FROM sessions").fetchall()
    to_delete = []
    for r in rows:
        if r["expires_at"] and r["expires_at"] < now:
            to_delete.append(r["session_id"])
        elif _max_exec_reached(r["execution_count"], r["max_executions"]):
            to_delete.append(r["session_id"])

    for sid in to_delete:
        db.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))
    db.commit()
    return jsonify({"deleted": len(to_delete), "message": f"Cleaned up {len(to_delete)} expired/maxed session(s)."})


# ── Error handlers ─────────────────────────────────────────────────────────────

@app.errorhandler(429)
def ratelimit_error(e):
    return jsonify({"error": f"Rate limit exceeded: {e.description}"}), 429


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Resource not found."}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error.", "detail": traceback.format_exc()}), 500


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
