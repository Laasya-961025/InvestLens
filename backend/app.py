"""InvestLens API + static file server.

Run:  python app.py      ->  http://localhost:5000
"""
import json
import math
import os
import re
import secrets
from datetime import timedelta
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

import db
import scoring

ROOT = db.ROOT
FRONTEND_DIR = os.path.join(ROOT, "frontend")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MAX_COMPANIES = 50
MAX_PRICES = 1000


def load_secret_key():
    """SECRET_KEY env var wins; otherwise generate one once and keep it next to the DB."""
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    path = os.path.join(ROOT, "database", ".secret_key")
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    key = secrets.token_hex(32)
    with open(path, "w") as f:
        f.write(key)
    return key


def create_app():
    app = Flask(__name__, static_folder=None)
    app.config.update(
        SECRET_KEY=load_secret_key(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",  # set to 1 behind HTTPS
        PERMANENT_SESSION_LIFETIME=timedelta(days=7),
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    db.init_db()
    app.teardown_appcontext(db.close_db)

    # ---------- helpers ----------
    def err(msg, code=400):
        return jsonify({"error": msg}), code

    def login_required(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if "uid" not in session:
                return err("Please log in.", 401)
            return fn(*a, **kw)
        return wrapper

    def body():
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}

    def num(v, default=0.0):
        try:
            x = float(v)
        except (TypeError, ValueError):
            return default
        return x if math.isfinite(x) else default

    def clean_company(raw):
        name = str(raw.get("name", "")).strip()[:100] or "Unnamed"
        c = {"name": name}
        for f in scoring.FIELDS:
            c[f] = num(raw.get(f))
        return c

    def current_user_row():
        return db.get_db().execute(
            "SELECT id, username, email FROM users WHERE id = ?", (session["uid"],)
        ).fetchone()

    def latest_analysis(uid):
        row = db.get_db().execute(
            "SELECT result_json, budget, risk FROM analyses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (uid,),
        ).fetchone()
        if not row:
            return None
        return {"budget": row["budget"], "risk": row["risk"], "results": json.loads(row["result_json"])}

    def find_company(uid, name):
        la = latest_analysis(uid)
        if not la:
            return None
        for c in la["results"]:
            if c["name"] == name:
                return c
        return None

    def latest_timing(uid, name):
        row = db.get_db().execute(
            "SELECT timing_score FROM signals WHERE user_id = ? AND company_name = ? ORDER BY id DESC LIMIT 1",
            (uid, name),
        ).fetchone()
        return row["timing_score"] if row else None

    # ---------- auth ----------
    @app.post("/api/auth/register")
    def register():
        d = body()
        username = str(d.get("username", "")).strip()
        email = str(d.get("email", "")).strip().lower()
        password = str(d.get("password", ""))
        if not username or not email or not password:
            return err("Please enter your name, email ID and password.")
        if len(username) > 80:
            return err("Name is too long.")
        if not EMAIL_RE.match(email):
            return err("Please enter a valid email ID.")
        if len(password) < 4:
            return err("Password must contain at least 4 characters.")
        conn = db.get_db()
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            return err("An account already exists with this email ID. Please log in instead.", 409)
        cur = conn.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, generate_password_hash(password)),
        )
        conn.execute("INSERT INTO settings (user_id) VALUES (?)", (cur.lastrowid,))
        conn.commit()
        session.clear()
        session.permanent = True
        session["uid"] = cur.lastrowid
        return jsonify({"username": username, "email": email}), 201

    @app.post("/api/auth/login")
    def login():
        d = body()
        email = str(d.get("email", "")).strip().lower()
        password = str(d.get("password", ""))
        if not email or not password:
            return err("Please enter your email ID and password.")
        row = db.get_db().execute(
            "SELECT id, username, email, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
        if not row:
            return err("No account exists with this email ID. Please create an account first.", 404)
        if not check_password_hash(row["password_hash"], password):
            return err("Incorrect password for this email ID.", 401)
        session.clear()
        session.permanent = True
        session["uid"] = row["id"]
        return jsonify({"username": row["username"], "email": row["email"]})

    @app.post("/api/auth/logout")
    def logout():
        session.clear()
        return jsonify({"ok": True})

    @app.get("/api/auth/me")
    def me():
        if "uid" not in session:
            return err("Not logged in.", 401)
        u = current_user_row()
        if not u:
            session.clear()
            return err("Not logged in.", 401)
        return jsonify({"username": u["username"], "email": u["email"]})

    @app.get("/api/accounts/exist")
    def accounts_exist():
        n = db.get_db().execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        return jsonify({"exist": n > 0})

    # ---------- portfolio (saved inputs + last analysis) ----------
    @app.get("/api/portfolio")
    @login_required
    def get_portfolio():
        conn = db.get_db()
        uid = session["uid"]
        s = conn.execute("SELECT budget, risk, horizon FROM settings WHERE user_id = ?", (uid,)).fetchone()
        rows = conn.execute(
            "SELECT name, ca, cl, debt, eq, cash, rev, ni FROM companies WHERE user_id = ? ORDER BY position",
            (uid,),
        ).fetchall()
        return jsonify({
            "settings": dict(s) if s else {"budget": 100000, "risk": 2, "horizon": "medium"},
            "companies": [dict(r) for r in rows],
            "latest_analysis": latest_analysis(uid),
        })

    # ---------- Layer 1 ----------
    @app.post("/api/analyze")
    @login_required
    def analyze():
        d = body()
        raw = d.get("companies")
        if not isinstance(raw, list) or not raw:
            return err("Add at least one company.")
        if len(raw) > MAX_COMPANIES:
            return err(f"Up to {MAX_COMPANIES} companies are allowed.")
        budget = max(0.0, num(d.get("budget")))
        risk = int(num(d.get("risk"), 2))
        if risk not in (1, 2, 3):
            return err("Risk appetite must be 1, 2 or 3.")
        companies = [clean_company(c) for c in raw if isinstance(c, dict)]
        if not companies:
            return err("Add at least one company.")

        results = scoring.analyze(companies, budget, risk)

        conn = db.get_db()
        uid = session["uid"]
        conn.execute("DELETE FROM companies WHERE user_id = ?", (uid,))
        conn.executemany(
            "INSERT INTO companies (user_id, position, name, ca, cl, debt, eq, cash, rev, ni) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(uid, i, c["name"], c["ca"], c["cl"], c["debt"], c["eq"], c["cash"], c["rev"], c["ni"])
             for i, c in enumerate(companies)],
        )
        conn.execute(
            "INSERT INTO settings (user_id, budget, risk) VALUES (?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET budget = excluded.budget, risk = excluded.risk",
            (uid, budget, risk),
        )
        conn.execute(
            "INSERT INTO analyses (user_id, budget, risk, result_json) VALUES (?,?,?,?)",
            (uid, budget, risk, json.dumps(results)),
        )
        conn.commit()
        return jsonify({"budget": budget, "risk": risk, "results": results})

    # ---------- Layer 2 ----------
    @app.post("/api/signal")
    @login_required
    def signal():
        d = body()
        name = str(d.get("company", ""))
        c = find_company(session["uid"], name)
        if not c:
            return err("Run the analysis on page 1 first.", 409)
        raw = d.get("prices")
        if isinstance(raw, str):
            raw = re.split(r"[,\s]+", raw.strip())
        if not isinstance(raw, list):
            return err("Enter at least 6 prices.")
        prices = [x for x in (num(p, 0) for p in raw) if x > 0]
        if len(prices) < 6:
            return err("Enter at least 6 prices.")
        if len(prices) > MAX_PRICES:
            return err(f"Up to {MAX_PRICES} prices are allowed.")

        res = scoring.price_signal(c["s"], prices)
        res["company"] = c["name"]
        conn = db.get_db()
        conn.execute(
            "INSERT INTO signals (user_id, company_name, prices_json, timing_score, final_score, signal) VALUES (?,?,?,?,?,?)",
            (session["uid"], c["name"], json.dumps(prices), res["timing_score"], res["final_score"], res["signal"]),
        )
        conn.commit()
        return jsonify(res)

    # ---------- AI assistant ----------
    def assistant_inputs():
        src = request.args if request.method == "GET" else body()
        name = str(src.get("company", ""))
        horizon = str(src.get("horizon", "medium"))
        if horizon not in scoring.HORIZONS:
            horizon = "medium"
        return name, horizon, src

    @app.get("/api/assistant/summary")
    @login_required
    def assistant_summary():
        name, horizon, _ = assistant_inputs()
        c = find_company(session["uid"], name)
        if not c:
            return err("Run the analysis on page 1 first.", 409)
        return jsonify(scoring.assistant_summary(c, horizon, latest_timing(session["uid"], c["name"])))

    @app.get("/api/assistant/history")
    @login_required
    def assistant_history():
        name, _, _ = assistant_inputs()
        rows = db.get_db().execute(
            "SELECT role, content FROM chat_messages WHERE user_id = ? AND company_name = ? ORDER BY id DESC LIMIT 100",
            (session["uid"], name),
        ).fetchall()
        return jsonify({"messages": [dict(r) for r in reversed(rows)]})

    @app.post("/api/assistant")
    @login_required
    def assistant():
        name, horizon, d = assistant_inputs()
        question = str(d.get("question", "")).strip()[:500]
        if not question:
            return err("Please type a question.")
        c = find_company(session["uid"], name)
        if not c:
            return err("Please run the company analysis on Page 1 first.", 409)
        answer = scoring.assistant_answer(c, horizon, question)
        conn = db.get_db()
        uid = session["uid"]
        conn.executemany(
            "INSERT INTO chat_messages (user_id, company_name, horizon, role, content) VALUES (?,?,?,?,?)",
            [(uid, c["name"], horizon, "user", question), (uid, c["name"], horizon, "bot", answer)],
        )
        conn.execute("UPDATE settings SET horizon = ? WHERE user_id = ?", (horizon, uid))
        conn.commit()
        return jsonify({"answer": answer})

    # ---------- frontend ----------
    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/<path:path>")
    def static_files(path):
        if path.startswith("api/"):
            return err("Not found.", 404)
        return send_from_directory(FRONTEND_DIR, path)

    @app.errorhandler(404)
    def not_found(_e):
        return err("Not found.", 404)

    @app.errorhandler(413)
    def too_large(_e):
        return err("Request too large.", 413)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG") == "1")
