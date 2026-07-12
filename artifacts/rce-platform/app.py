import os
import secrets
import sqlite3
import traceback
from datetime import datetime
from functools import wraps
from flask import (
    Flask, request, jsonify, render_template,
    abort, g, session, redirect, url_for
)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", secrets.token_hex(32))

DATABASE = os.path.join(os.path.dirname(__file__), "sessions.db")
MAX_CODE_CHARS = 10_000


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
                session_id      TEXT PRIMARY KEY,
                python_code     TEXT NOT NULL,
                execution_count INTEGER NOT NULL DEFAULT 0,
                created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        db.commit()
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


def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_authed"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


def require_admin_api(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        provided = request.headers.get("X-Admin-Token", "").strip()
        if not provided or provided != _get_admin_token():
            return jsonify({"error": "Admin authentication required. Provide X-Admin-Token header."}), 403
        return f(*args, **kwargs)
    return decorated


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


# ── Public pages ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── Admin auth ─────────────────────────────────────────────────────────────────

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_authed"):
        return redirect(url_for("admin"))
    error = None
    if request.method == "POST":
        token = request.form.get("token", "").strip()
        if token and token == _get_admin_token():
            session["admin_authed"] = True
            session.permanent = False
            return redirect(url_for("admin"))
        error = "Invalid access token."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


# ── Protected admin pages ─────────────────────────────────────────────────────

@app.route("/admin")
@require_admin
def admin():
    db = get_db()
    rows = db.execute(
        "SELECT session_id, execution_count, created_at, LENGTH(python_code) AS code_size "
        "FROM sessions ORDER BY created_at DESC"
    ).fetchall()
    sessions_list = [dict(r) for r in rows]
    return render_template("admin.html", sessions=sessions_list, admin_token=_get_admin_token())


@app.route("/admin/view/<session_id>")
@require_admin
def admin_view(session_id):
    db = get_db()
    row = db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if not row:
        abort(404)
    return render_template("admin_view.html", session=dict(row), admin_token=_get_admin_token())


# ── Public API ─────────────────────────────────────────────────────────────────

@app.route("/pyv/save", methods=["POST"])
def api_save():
    code = ""
    if request.content_type and "multipart" in request.content_type:
        f = request.files.get("file")
        if f:
            if not f.filename.endswith(".py"):
                return jsonify({"error": "Only .py files are accepted."}), 400
            code = f.read().decode("utf-8", errors="replace")
    else:
        data = request.get_json(silent=True) or {}
        code = data.get("code", "")

    if not code or not code.strip():
        return jsonify({"error": "No Python code provided."}), 400
    if len(code) > MAX_CODE_CHARS:
        return jsonify({"error": f"Code exceeds the {MAX_CODE_CHARS:,}-character limit."}), 400

    session_id = generate_session_id()
    db = get_db()
    db.execute(
        "INSERT INTO sessions (session_id, python_code, execution_count, created_at) VALUES (?, ?, 0, ?)",
        (session_id, code, datetime.utcnow().isoformat()),
    )
    db.commit()
    return jsonify({"session_id": session_id, "message": "Code saved successfully."}), 201


@app.route("/pyv/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided. Send a .py file as the 'file' field."}), 400
    f = request.files["file"]
    if not f.filename.endswith(".py"):
        return jsonify({"error": "Only .py files are accepted."}), 400
    code = f.read().decode("utf-8", errors="replace")
    if not code.strip():
        return jsonify({"error": "The uploaded file is empty."}), 400
    if len(code) > MAX_CODE_CHARS:
        return jsonify({"error": f"File exceeds the {MAX_CODE_CHARS:,}-character limit."}), 400

    session_id = generate_session_id()
    db = get_db()
    db.execute(
        "INSERT INTO sessions (session_id, python_code, execution_count, created_at) VALUES (?, ?, 0, ?)",
        (session_id, code, datetime.utcnow().isoformat()),
    )
    db.commit()
    return jsonify({"session_id": session_id, "message": "File uploaded successfully."}), 201


@app.route("/pyv/get/<session_id>", methods=["GET"])
def api_get(session_id):
    if not _validate_sid(session_id):
        return jsonify({"error": "Invalid session ID. Must be exactly 21 lowercase hex characters."}), 400
    db = get_db()
    row = db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if not row:
        return jsonify({"error": f"Session '{session_id}' not found."}), 404
    db.execute(
        "UPDATE sessions SET execution_count = execution_count + 1 WHERE session_id = ?",
        (session_id,),
    )
    db.commit()
    return jsonify({
        "session_id": session_id,
        "code": row["python_code"],
        "execution_count": row["execution_count"] + 1,
        "created_at": row["created_at"],
    })


@app.route("/pyv/info/<session_id>", methods=["GET"])
def api_info(session_id):
    if not _validate_sid(session_id):
        return jsonify({"error": "Invalid session ID. Must be exactly 21 lowercase hex characters."}), 400
    db = get_db()
    row = db.execute(
        "SELECT session_id, execution_count, created_at, LENGTH(python_code) AS code_size "
        "FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        return jsonify({"error": f"Session '{session_id}' not found."}), 404
    return jsonify({
        "session_id": session_id,
        "execution_count": row["execution_count"],
        "created_at": row["created_at"],
        "code_size": row["code_size"],
    })


@app.route("/pyv/stats", methods=["GET"])
def api_stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) AS cnt FROM sessions").fetchone()["cnt"]
    total_exec = db.execute("SELECT SUM(execution_count) AS s FROM sessions").fetchone()["s"] or 0
    return jsonify({"total_sessions": total, "total_executions": total_exec})


# ── Admin-only API (require X-Admin-Token header) ─────────────────────────────

@app.route("/pyv/edit/<session_id>", methods=["PUT"])
@require_admin_api
def api_edit(session_id):
    if not _validate_sid(session_id):
        return jsonify({"error": "Invalid session ID."}), 400
    db = get_db()
    row = db.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if not row:
        return jsonify({"error": f"Session '{session_id}' not found."}), 404
    data = request.get_json(silent=True) or {}
    new_code = data.get("code", "")
    if not new_code or not new_code.strip():
        return jsonify({"error": "No updated code provided."}), 400
    if len(new_code) > MAX_CODE_CHARS:
        return jsonify({"error": f"Code exceeds the {MAX_CODE_CHARS:,}-character limit."}), 400
    db.execute("UPDATE sessions SET python_code = ? WHERE session_id = ?", (new_code, session_id))
    db.commit()
    return jsonify({"session_id": session_id, "message": "Code updated successfully."})


@app.route("/pyv/delete/<session_id>", methods=["DELETE"])
@require_admin_api
def api_delete(session_id):
    db = get_db()
    result = db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    db.commit()
    if result.rowcount == 0:
        return jsonify({"error": "Session not found."}), 404
    return jsonify({"message": "Session deleted successfully."})


# ── Error handlers ─────────────────────────────────────────────────────────────

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
