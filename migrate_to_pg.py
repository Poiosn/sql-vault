"""
Run this once to copy local SQLite data to Railway PostgreSQL.
Usage: python3 migrate_to_pg.py
"""
import sqlite3
import os
import sys

database_url = os.environ.get("DATABASE_URL", "")
if not database_url:
    print("ERROR: DATABASE_URL not set.")
    print("Run: export DATABASE_URL=<your railway postgres url>")
    sys.exit(1)

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

try:
    import psycopg2
except ImportError:
    print("Installing psycopg2...")
    os.system("pip install psycopg2-binary")
    import psycopg2

# Read from local SQLite
sqlite_path = os.path.join(os.path.dirname(__file__), "instance", "queries.db")
con = sqlite3.connect(sqlite_path)
con.row_factory = sqlite3.Row
cur = con.cursor()
cur.execute("SELECT id, title, sql, description, tags, state_id, created_at, updated_at FROM query")
rows = cur.fetchall()
con.close()
print(f"Found {len(rows)} queries in local SQLite.")

# Write to PostgreSQL
pg = psycopg2.connect(database_url)
pgcur = pg.cursor()

# Create table if not exists
pgcur.execute("""
CREATE TABLE IF NOT EXISTS query (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    sql TEXT NOT NULL,
    description TEXT DEFAULT '',
    tags VARCHAR(500) DEFAULT '',
    state_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
)
""")

pgcur.execute("SELECT COUNT(*) FROM query")
existing = pgcur.fetchone()[0]
if existing > 0:
    print(f"PostgreSQL already has {existing} rows. Skipping to avoid duplicates.")
    print("If you want to re-import, run: DELETE FROM query; in your Railway DB first.")
    pg.close()
    sys.exit(0)

inserted = 0
for row in rows:
    pgcur.execute("""
        INSERT INTO query (id, title, sql, description, tags, state_id, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        row["id"], row["title"], row["sql"],
        row["description"] or "", row["tags"] or "",
        row["state_id"], row["created_at"], row["updated_at"]
    ))
    inserted += 1

# Sync the serial sequence so new inserts don't conflict
pgcur.execute("SELECT setval('query_id_seq', (SELECT MAX(id) FROM query))")

pg.commit()
pg.close()
print(f"Done! {inserted} queries migrated to Railway PostgreSQL.")
