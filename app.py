import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from rapidfuzz import fuzz
from functools import wraps

ADMIN_USERNAME = "ssswapnil250"
ADMIN_PASSWORD = "Sharvari123@"


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Please log in to perform that action.", "warning")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")

# Use database from DATABASE_URL if set, else SQLite locally
database_url = os.environ.get("DATABASE_URL", "sqlite:///queries.db")
# Fix URL prefixes for SQLAlchemy compatibility
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
elif database_url.startswith("mysql://"):
    database_url = database_url.replace("mysql://", "mysql+pymysql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

STATES = {
    1: "Maharashtra",
    2: "Delhi",
    3: "Jharkhand",
    4: "Haryana",
    5: "Lakshadweep",
    6: "Andaman & Nicobar Islands",
    7: "Himachal Pradesh",
    8: "UT-Chandigarh",
    9: "Dadra & Nagar Haveli - Daman & Diu",
    11: "Mizoram",
    12: "Puducherry",
    13: "Sikkim",
    14: "Arunachal Pradesh",
    15: "Rajasthan",
    16: "J&K",
    17: "Gujarat",
    18: "Kerala",
    19: "Tamil Nadu",
    20: "Telangana",
    21: "Uttarakhand",
    22: "Bihar",
    23: "Madhya Pradesh",
    24: "Uttar Pradesh",
    25: "Tripura",
    26: "Assam",
    27: "Chhattisgarh",
    28: "Nagaland",
    29: "Manipur",
    30: "Meghalaya",
    31: "Goa",
    32: "Karnataka",
    34: "Andhra Pradesh",
    35: "Odisha",
    36: "Punjab",
    37: "Ladakh",
    38: "West Bengal",
}

# Sorted list of (id, name) for templates
STATES_LIST = sorted(STATES.items(), key=lambda x: x[1])


def fuzzy_state_match(text, state_name, threshold=78):
    """Return True if any word in text is a fuzzy match for any word in state_name."""
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


class Query(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    sql_query = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, default="")
    tags = db.Column(db.String(500), default="")
    state_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def tag_list(self):
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    def state_name(self):
        return STATES.get(self.state_id)


with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print(f"WARNING: db.create_all() failed: {e}")
    try:
        with db.engine.connect() as conn:
            try:
                conn.execute(db.text("ALTER TABLE query ADD COLUMN state_id INTEGER"))
                conn.commit()
            except Exception:
                pass
    except Exception as e:
        print(f"WARNING: migration check failed: {e}")


@app.route("/health")
def health():
    return "OK", 200


@app.route("/db-check")
def db_check():
    try:
        with db.engine.connect() as conn:
            result = conn.execute(db.text(
                "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='query' ORDER BY ordinal_position"
            ))
            cols = [f"{r[0]} ({r[1]})" for r in result]
        return "<br>".join(cols) or "No columns found", 200
    except Exception as e:
        return str(e), 500


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
        query = query.filter(
            db.or_(
                Query.title.ilike(like),
                Query.sql_query.ilike(like),
                Query.description.ilike(like),
                Query.tags.ilike(like),
            )
        )

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
            if q.state_id == sid
            or fuzzy_state_match(
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

    # Collect all unique tags for the sidebar
    all_queries = Query.query.all()
    all_tags = set()
    for q in all_queries:
        for t in q.tag_list():
            all_tags.add(t)
    all_tags = sorted(all_tags)

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
    return render_template("view.html", q=q, states=STATES_LIST)


@app.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit(id):
    q = Query.query.get_or_404(id)

    if request.method == "POST":
        q.title = request.form.get("title", "").strip()
        q.sql_query = request.form.get("sql_query", "").strip()
        q.description = request.form.get("description", "").strip()
        q.tags = request.form.get("tags", "").strip()
        state_id = request.form.get("state_id") or None
        q.state_id = int(state_id) if state_id else None
        q.updated_at = datetime.utcnow()

        if not q.title or not q.sql_query:
            flash("Title and SQL are required.", "danger")
            return render_template("add.html", form=request.form, edit=True, id=id, states=STATES_LIST)

        db.session.commit()
        flash("Query updated!", "success")
        return redirect(url_for("view", id=q.id))

    return render_template("add.html", form={
        "title": q.title,
        "sql_query": q.sql_query,
        "description": q.description,
        "tags": q.tags,
        "state_id": q.state_id,
    }, edit=True, id=id, states=STATES_LIST)


@app.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete(id):
    q = Query.query.get_or_404(id)
    db.session.delete(q)
    db.session.commit()
    flash("Query deleted.", "warning")
    return redirect(url_for("index"))


# Reverse lookup: lowercase state name -> state_id
STATES_LOWER = {v.lower(): k for k, v in STATES.items()}


def resolve_state_id(text):
    """Return state_id by exact then fuzzy match against text, or None."""
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
    """Scan each word/phrase in title for a fuzzy state name match."""
    words = title.split()
    # try progressively longer n-grams (up to 4 words) to catch "West Bengal" etc.
    for n in range(4, 0, -1):
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i:i + n])
            sid = resolve_state_id(phrase)
            if sid:
                return sid
    return None


def parse_comment_format(text):
    """
    Parse files where each query starts with a '--' comment line as the title,
    followed immediately by the SQL body. Multiple queries are separated by the
    next '--' comment line.
    """
    lines = text.splitlines()
    blocks = []   # list of (title_line_index, [lines])
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
    """
    Parse files where blocks are separated by '---' and use 'Key: value' metadata
    followed by 'SQL:' and the query body.
    """
    blocks = [b.strip() for b in text.split("---") if b.strip()]
    rows, errors = [], []

    for i, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        meta = {}
        sql_lines = []
        in_sql = False

        for line in lines:
            if in_sql:
                sql_lines.append(line)
            elif line.lower().startswith("sql:"):
                in_sql = True
                rest = line[4:].strip()
                if rest:
                    sql_lines.append(rest)
            else:
                if ":" in line:
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

        rows.append({
            "title": title,
            "sql_query": sql,
            "description": meta.get("description", ""),
            "tags": meta.get("tags", ""),
            "state_id": state_id,
        })

    return rows, errors


def parse_import_file(text):
    """Auto-detect format and parse accordingly."""
    # If any non-comment line contains 'Title:' it's the block format
    has_title_key = any(
        l.strip().lower().startswith("title:") for l in text.splitlines()
    )
    if has_title_key:
        return parse_block_format(text)
    return parse_comment_format(text)


@app.route("/import", methods=["GET", "POST"])
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

        if errors:
            for block_num, reason in errors:
                flash(f"Block {block_num} skipped: {reason}", "warning")

        flash(f"Imported {len(rows)} quer{'y' if len(rows)==1 else 'ies'} successfully.", "success")
        return redirect(url_for("index"))

    return render_template("import.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["logged_in"] = True
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
