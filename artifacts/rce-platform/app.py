import os
import secrets
import sqlite3
import traceback
from datetime import datetime
from flask import Flask, request, jsonify, render_template, abort, g

app = Flask(__name__)

DATABASE = os.path.join(os.path.dirname(__file__), "sessions.db")


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
                session_id   TEXT PRIMARY KEY,
                python_code  TEXT NOT NULL,
                execution_count INTEGER NOT NULL DEFAULT 0,
                created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.commit()


def generate_session_id():
    while True:
        sid = secrets.token_hex(11)[:21]
        db = get_db()
        row = db.execute(
            "SELECT 1 FROM sessions WHERE session_id = ?", (sid,)
        ).fetchone()
        if not row:
            return sid


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/admin")
def admin():
    db = get_db()
    rows = db.execute(
        "SELECT session_id, execution_count, created_at, LENGTH(python_code) AS code_size FROM sessions ORDER BY created_at DESC"
    ).fetchall()
    sessions = [dict(r) for r in rows]
    return render_template("admin.html", sessions=sessions)


@app.route("/admin/view/<session_id>")
def admin_view(session_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if not row:
        abort(404)
    return render_template("admin_view.html", session=dict(row))


@app.route("/pyv/save", methods=["POST"])
def api_save():
    data = request.get_json(silent=True) or {}
    code = data.get("code", "")
    if not code or not code.strip():
        return jsonify({"error": "No Python code provided"}), 400

    session_id = generate_session_id()
    db = get_db()
    db.execute(
        "INSERT INTO sessions (session_id, python_code, execution_count, created_at) VALUES (?, ?, 0, ?)",
        (session_id, code, datetime.utcnow().isoformat()),
    )
    db.commit()
    return jsonify({"session_id": session_id, "message": "Code saved successfully"}), 201


@app.route("/pyv/get/<session_id>", methods=["GET"])
def api_get(session_id):
    if len(session_id) != 21 or not all(c in "0123456789abcdef" for c in session_id):
        return jsonify({"error": "Invalid session ID format. Must be a 21-character hex string."}), 400

    db = get_db()
    row = db.execute(
        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": f"Session ID '{session_id}' not found or has expired."}), 404

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


@app.route("/pyv/edit/<session_id>", methods=["PUT"])
def api_edit(session_id):
    if len(session_id) != 21 or not all(c in "0123456789abcdef" for c in session_id):
        return jsonify({"error": "Invalid session ID format. Must be a 21-character hex string."}), 400

    db = get_db()
    row = db.execute(
        "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": f"Session ID '{session_id}' not found. Cannot edit a non-existent session."}), 404

    data = request.get_json(silent=True) or {}
    new_code = data.get("code", "")
    if not new_code or not new_code.strip():
        return jsonify({"error": "No updated code provided"}), 400

    db.execute(
        "UPDATE sessions SET python_code = ? WHERE session_id = ?",
        (new_code, session_id),
    )
    db.commit()
    return jsonify({"session_id": session_id, "message": "Code updated successfully"})


@app.route("/pyv/delete/<session_id>", methods=["DELETE"])
def api_delete(session_id):
    db = get_db()
    result = db.execute(
        "DELETE FROM sessions WHERE session_id = ?", (session_id,)
    )
    db.commit()
    if result.rowcount == 0:
        return jsonify({"error": "Session not found"}), 404
    return jsonify({"message": "Session deleted successfully"})


@app.route("/pyv/stats", methods=["GET"])
def api_stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) AS cnt FROM sessions").fetchone()["cnt"]
    total_exec = db.execute("SELECT SUM(execution_count) AS s FROM sessions").fetchone()["s"] or 0
    return jsonify({"total_sessions": total, "total_executions": total_exec})


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Resource not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error", "detail": traceback.format_exc()}), 500


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
