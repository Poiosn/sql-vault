import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")

# Use PostgreSQL on Railway if DATABASE_URL is set, else SQLite locally
database_url = os.environ.get("DATABASE_URL", "sqlite:///queries.db")
# Railway uses postgres:// but SQLAlchemy needs postgresql://
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class Query(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    sql = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, default="")
    tags = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def tag_list(self):
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]


with app.app_context():
    db.create_all()


@app.route("/")
def index():
    search = request.args.get("q", "").strip()
    tag = request.args.get("tag", "").strip()

    query = Query.query

    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                Query.title.ilike(like),
                Query.sql.ilike(like),
                Query.description.ilike(like),
                Query.tags.ilike(like),
            )
        )

    if tag:
        query = query.filter(Query.tags.ilike(f"%{tag}%"))

    queries = query.order_by(Query.created_at.desc()).all()

    # Collect all unique tags for the sidebar
    all_queries = Query.query.all()
    all_tags = set()
    for q in all_queries:
        for t in q.tag_list():
            all_tags.add(t)
    all_tags = sorted(all_tags)

    return render_template("index.html", queries=queries, search=search, tag=tag, all_tags=all_tags)


@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        sql = request.form.get("sql", "").strip()
        description = request.form.get("description", "").strip()
        tags = request.form.get("tags", "").strip()

        if not title or not sql:
            flash("Title and SQL are required.", "danger")
            return render_template("add.html", form=request.form)

        q = Query(title=title, sql=sql, description=description, tags=tags)
        db.session.add(q)
        db.session.commit()
        flash("Query saved successfully!", "success")
        return redirect(url_for("view", id=q.id))

    return render_template("add.html", form={})


@app.route("/view/<int:id>")
def view(id):
    q = Query.query.get_or_404(id)
    return render_template("view.html", q=q)


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    q = Query.query.get_or_404(id)

    if request.method == "POST":
        q.title = request.form.get("title", "").strip()
        q.sql = request.form.get("sql", "").strip()
        q.description = request.form.get("description", "").strip()
        q.tags = request.form.get("tags", "").strip()
        q.updated_at = datetime.utcnow()

        if not q.title or not q.sql:
            flash("Title and SQL are required.", "danger")
            return render_template("add.html", form=request.form, edit=True, id=id)

        db.session.commit()
        flash("Query updated!", "success")
        return redirect(url_for("view", id=q.id))

    return render_template("add.html", form={
        "title": q.title,
        "sql": q.sql,
        "description": q.description,
        "tags": q.tags,
    }, edit=True, id=id)


@app.route("/delete/<int:id>", methods=["POST"])
def delete(id):
    q = Query.query.get_or_404(id)
    db.session.delete(q)
    db.session.commit()
    flash("Query deleted.", "warning")
    return redirect(url_for("index"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
