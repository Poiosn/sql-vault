import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, timezone

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)
from rapidfuzz import fuzz
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------------
# Users & roles
# ---------------------------------------------------------------------------
def _hash(pw):
    return generate_password_hash(pw, method="pbkdf2:sha256")

USERS = {
    "ssswapnil250": {"password": _hash("Sharvari123@"), "role": "admin"},
    "Rajvir":       {"password": _hash("Rajvir"),       "role": "viewer"},
    "Smriti":       {"password": _hash("Smriti"),       "role": "viewer"},
    "Prem":         {"password": _hash("Prem"),         "role": "viewer"},
    "Balaji":       {"password": _hash("Balaji"),       "role": "viewer"},
}

SESSION_TIMEOUT_MINUTES = 30

# ---------------------------------------------------------------------------
# App & DB setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=SESSION_TIMEOUT_MINUTES)

database_url = os.environ.get("DATABASE_URL", "sqlite:///queries.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
elif database_url.startswith("mysql://"):
    database_url = database_url.replace("mysql://", "mysql+pymysql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------
STATES = {
    1: "Maharashtra", 2: "Delhi", 3: "Jharkhand", 4: "Haryana",
    5: "Lakshadweep", 6: "Andaman & Nicobar Islands", 7: "Himachal Pradesh",
    8: "UT-Chandigarh", 9: "Dadra & Nagar Haveli - Daman & Diu",
    11: "Mizoram", 12: "Puducherry", 13: "Sikkim", 14: "Arunachal Pradesh",
    15: "Rajasthan", 16: "J&K", 17: "Gujarat", 18: "Kerala",
    19: "Tamil Nadu", 20: "Telangana", 21: "Uttarakhand", 22: "Bihar",
    23: "Madhya Pradesh", 24: "Uttar Pradesh", 25: "Tripura", 26: "Assam",
    27: "Chhattisgarh", 28: "Nagaland", 29: "Manipur", 30: "Meghalaya",
    31: "Goa", 32: "Karnataka", 34: "Andhra Pradesh", 35: "Odisha",
    36: "Punjab", 37: "Ladakh", 38: "West Bengal",
}
STATES_LIST = sorted(STATES.items(), key=lambda x: x[1])
STATES_LOWER = {v.lower(): k for k, v in STATES.items()}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class Query(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    sql_query = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, default="")
    tags = db.Column(db.String(500), default="")
    state_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    def tag_list(self):
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    def state_name(self):
        return STATES.get(self.state_id)


class AuditLog(db.Model):
    __tablename__ = "audit_log"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    query_id = db.Column(db.Integer, nullable=True)
    query_title = db.Column(db.String(200), nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=utcnow)


# ---------------------------------------------------------------------------
# DB init & migrations
# ---------------------------------------------------------------------------
def init_db():
    is_mysql = database_url.startswith("mysql")
    db.create_all()
    with db.engine.connect() as conn:
        for sql in [
            ('ALTER TABLE `query` CHANGE `sql` sql_query TEXT NOT NULL' if is_mysql
             else 'ALTER TABLE "query" RENAME COLUMN sql TO sql_query'),
            ('ALTER TABLE `query` ADD COLUMN state_id INTEGER' if is_mysql
             else 'ALTER TABLE "query" ADD COLUMN state_id INTEGER'),
        ]:
            try:
                conn.execute(db.text(sql))
                conn.commit()
            except Exception:
                pass


with app.app_context():
    try:
        init_db()
        print("INFO: Database ready.")
    except Exception as e:
        print(f"WARNING: DB init failed: {e}")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def log_action(action, query_id=None, query_title=None):
    try:
        entry = AuditLog(
            username=session.get("username", "unknown"),
            action=action,
            query_id=query_id,
            query_title=query_title,
            ip_address=request.remote_addr,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        pass


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("username"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("username"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login", next=request.url))
        if session.get("role") != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated


@app.before_request
def enforce_login_and_timeout():
    public_endpoints = {"login", "health", "static"}
    if request.endpoint in public_endpoints:
        return

    if not session.get("username"):
        return redirect(url_for("login", next=request.url))

    # 30-min inactivity timeout
    last_active = session.get("last_active")
    if last_active:
        elapsed = (utcnow() - datetime.fromisoformat(last_active)).total_seconds()
        if elapsed > SESSION_TIMEOUT_MINUTES * 60:
            username = session.get("username")
            session.clear()
            log_action("session_timeout")
            flash("Session expired after 30 minutes of inactivity. Please log in again.", "warning")
            return redirect(url_for("login"))
    session["last_active"] = utcnow().isoformat()


# ---------------------------------------------------------------------------
# Fuzzy helpers
# ---------------------------------------------------------------------------
def fuzzy_state_match(text, state_name, threshold=78):
    if not text or not state_name:
        return False
    text_words = text.lower().split()
    for s_word in state_name.lower().split():
        if len(s_word) < 3:
            continue
        for t_word in text_words:
            if len(t_word) < 3:
                continue
            if fuzz.ratio(s_word, t_word) >= threshold:
                return True
    return False


def resolve_state_id(text):
    if not text:
        return None
    exact = STATES_LOWER.get(text.lower())
    if exact:
        return exact
    best_score, best_id = 0, None
    for name, sid in STATES_LOWER.items():
        score = fuzz.ratio(text.lower(), name)
        if score > best_score:
            best_score, best_id = score, sid
    return best_id if best_score >= 78 else None


def detect_state_in_title(title):
    words = title.split()
    for n in range(4, 0, -1):
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i:i + n])
            sid = resolve_state_id(phrase)
            if sid:
                return sid
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/health")
def health():
    return "OK", 200


@app.route("/")
def index():
    search = request.args.get("q", "").strip()
    tag = request.args.get("tag", "").strip()
    state_id = request.args.get("state_id", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    query = Query.query

    if search:
        like = f"%{search}%"
        query = query.filter(db.or_(
            Query.title.ilike(like),
            Query.sql_query.ilike(like),
            Query.description.ilike(like),
            Query.tags.ilike(like),
        ))

    if tag:
        query = query.filter(Query.tags.ilike(f"%{tag}%"))

    if date_from:
        try:
            query = query.filter(Query.created_at >= datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            query = query.filter(Query.created_at <= dt_to)
        except ValueError:
            pass

    page = request.args.get("page", 1, type=int)
    per_page = 50

    if state_id:
        sid = int(state_id)
        state_name_str = STATES.get(sid, "")
        candidates = query.order_by(Query.created_at.desc()).all()
        filtered = [
            q for q in candidates
            if q.state_id == sid or fuzzy_state_match(
                " ".join(filter(None, [q.title, q.description, q.tags])),
                state_name_str,
            )
        ]
        total = len(filtered)
        start = (page - 1) * per_page
        queries = filtered[start:start + per_page]
        total_pages = (total + per_page - 1) // per_page
    else:
        pagination = query.order_by(Query.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
        queries = pagination.items
        total = pagination.total
        total_pages = pagination.pages

    all_tags = sorted({t for q in Query.query.all() for t in q.tag_list()})

    return render_template(
        "index.html",
        queries=queries,
        search=search,
        tag=tag,
        all_tags=all_tags,
        states=STATES_LIST,
        selected_state_id=int(state_id) if state_id else None,
        page=page,
        total_pages=total_pages,
        total=total,
        date_from=date_from,
        date_to=date_to,
    )


@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        sql_query = request.form.get("sql_query", "").strip()
        description = request.form.get("description", "").strip()
        tags = request.form.get("tags", "").strip()
        state_id = request.form.get("state_id") or None
        if state_id:
            state_id = int(state_id)

        if not title or not sql_query:
            flash("Title and SQL are required.", "danger")
            return render_template("add.html", form=request.form, states=STATES_LIST)

        try:
            q = Query(title=title, sql_query=sql_query, description=description, tags=tags, state_id=state_id)
            db.session.add(q)
            db.session.commit()
            log_action("add_query", query_id=q.id, query_title=q.title)
            flash("Query saved successfully!", "success")
            return redirect(url_for("view", id=q.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Database error: {e}", "danger")
            return render_template("add.html", form=request.form, states=STATES_LIST)

    return render_template("add.html", form={}, states=STATES_LIST)


@app.route("/view/<int:id>")
def view(id):
    q = Query.query.get_or_404(id)
    log_action("view_query", query_id=q.id, query_title=q.title)
    return render_template("view.html", q=q, states=STATES_LIST)


@app.route("/edit/<int:id>", methods=["GET", "POST"])
@admin_required
def edit(id):
    q = Query.query.get_or_404(id)
    if request.method == "POST":
        q.title = request.form.get("title", "").strip()
        q.sql_query = request.form.get("sql_query", "").strip()
        q.description = request.form.get("description", "").strip()
        q.tags = request.form.get("tags", "").strip()
        state_id = request.form.get("state_id") or None
        q.state_id = int(state_id) if state_id else None
        q.updated_at = utcnow()

        if not q.title or not q.sql_query:
            flash("Title and SQL are required.", "danger")
            return render_template("add.html", form=request.form, edit=True, id=id, states=STATES_LIST)

        db.session.commit()
        log_action("edit_query", query_id=q.id, query_title=q.title)
        flash("Query updated!", "success")
        return redirect(url_for("view", id=q.id))

    return render_template("add.html", form={
        "title": q.title, "sql_query": q.sql_query,
        "description": q.description, "tags": q.tags, "state_id": q.state_id,
    }, edit=True, id=id, states=STATES_LIST)


@app.route("/delete/<int:id>", methods=["POST"])
@admin_required
def delete(id):
    q = Query.query.get_or_404(id)
    log_action("delete_query", query_id=q.id, query_title=q.title)
    db.session.delete(q)
    db.session.commit()
    flash("Query deleted.", "warning")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# API: serve SQL securely (not in page source)
# ---------------------------------------------------------------------------
@app.route("/api/sql/<int:id>")
def api_sql(id):
    q = Query.query.get_or_404(id)
    return jsonify({"sql": q.sql_query})


@app.route("/api/copy/<int:id>")
def api_copy(id):
    q = Query.query.get_or_404(id)
    log_action("copy_sql", query_id=q.id, query_title=q.title)
    return jsonify({"sql": q.sql_query})


# ---------------------------------------------------------------------------
# Audit log (admin only)
# ---------------------------------------------------------------------------
@app.route("/audit")
@admin_required
def audit():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(500).all()
    return render_template("audit.html", logs=logs)


# ---------------------------------------------------------------------------
# Import (admin only)
# ---------------------------------------------------------------------------
def parse_comment_format(text):
    lines = text.splitlines()
    blocks = []
    current = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("--"):
            if current is not None:
                blocks.append(current)
            current = {"title_raw": stripped[2:].strip(), "sql_lines": []}
        elif current is not None:
            current["sql_lines"].append(line)
    if current is not None:
        blocks.append(current)

    rows, errors = [], []
    for i, block in enumerate(blocks, start=1):
        title = block["title_raw"]
        sql = "\n".join(block["sql_lines"]).strip()
        if not title:
            errors.append((i, "Empty comment line used as title"))
            continue
        if not sql:
            errors.append((i, f'"{title}" — no SQL found after comment'))
            continue
        state_id = detect_state_in_title(title)
        rows.append({"title": title, "sql_query": sql, "description": "", "tags": "", "state_id": state_id})
    return rows, errors


def parse_block_format(text):
    blocks = [b.strip() for b in text.split("---") if b.strip()]
    rows, errors = [], []
    for i, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        meta, sql_lines, in_sql = {}, [], False
        for line in lines:
            if in_sql:
                sql_lines.append(line)
            elif line.lower().startswith("sql:"):
                in_sql = True
                rest = line[4:].strip()
                if rest:
                    sql_lines.append(rest)
            elif ":" in line:
                key, _, val = line.partition(":")
                meta[key.strip().lower()] = val.strip()
        title = meta.get("title", "").strip()
        sql = "\n".join(sql_lines).strip()
        if not title:
            errors.append((i, "Missing Title"))
            continue
        if not sql:
            errors.append((i, f'"{title}" — missing SQL'))
            continue
        state_id = resolve_state_id(meta.get("state", "").strip()) or detect_state_in_title(title)
        rows.append({"title": title, "sql_query": sql, "description": meta.get("description", ""),
                     "tags": meta.get("tags", ""), "state_id": state_id})
    return rows, errors


def parse_import_file(text):
    has_title_key = any(l.strip().lower().startswith("title:") for l in text.splitlines())
    if has_title_key:
        return parse_block_format(text)
    return parse_comment_format(text)


@app.route("/import", methods=["GET", "POST"])
@admin_required
def import_queries():
    if request.method == "POST":
        f = request.files.get("file")
        if not f or not f.filename.endswith(".txt"):
            flash("Please upload a .txt file.", "danger")
            return render_template("import.html")
        text = f.read().decode("utf-8", errors="replace")
        rows, errors = parse_import_file(text)
        for row in rows:
            db.session.add(Query(**row))
        if rows:
            db.session.commit()
            log_action("import_queries", query_title=f"{len(rows)} queries imported")
        for block_num, reason in errors:
            flash(f"Block {block_num} skipped: {reason}", "warning")
        flash(f"Imported {len(rows)} quer{'y' if len(rows)==1 else 'ies'} successfully.", "success")
        return redirect(url_for("index"))
    return render_template("import.html")


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = USERS.get(username)
        if user and check_password_hash(user["password"], password):
            session.permanent = True
            session["username"] = username
            session["role"] = user["role"]
            session["last_active"] = utcnow().isoformat()
            log_action("login")
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    log_action("logout")
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    import subprocess, threading
    port = int(os.environ.get("PORT", 5001))

    def start_ngrok():
        subprocess.Popen(
            ["ngrok", "http", "--url=singular-clobber-blighted.ngrok-free.dev", str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        print(f" * Public URL: https://singular-clobber-blighted.ngrok-free.dev")

    threading.Thread(target=start_ngrok, daemon=True).start()
    app.run(host="0.0.0.0", port=port, debug=False)
