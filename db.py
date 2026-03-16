"""
Creates all database tables. Run via Railway releaseCommand before app starts.
Usage: python3 db.py
"""

import os
import sys

# Ensure DATABASE_URL is available
database_url = os.environ.get("DATABASE_URL", "")
if not database_url:
    print("WARNING: DATABASE_URL not set, using SQLite.")

from app import app, db

with app.app_context():
    # Primary: SQLAlchemy ORM creates all model tables
    db.create_all()
    print("db.create_all() completed.")

    # Fallback: Ensure query table exists via raw SQL (safe on both SQLite and PostgreSQL)
    with db.engine.connect() as conn:
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS "query" (
                id SERIAL PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                sql_query TEXT NOT NULL,
                description TEXT DEFAULT '',
                tags VARCHAR(500) DEFAULT '',
                state_id INTEGER,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.commit()
        print("Table 'query' ensured via raw SQL.")

        # Rename sql -> sql_query if old column exists
        try:
            conn.execute(db.text('ALTER TABLE "query" RENAME COLUMN "sql" TO sql_query'))
            conn.commit()
            print("Renamed column sql -> sql_query.")
        except Exception:
            pass  # Already renamed or doesn't exist

        # Add state_id column to existing databases that predate this field
        try:
            conn.execute(db.text('ALTER TABLE "query" ADD COLUMN state_id INTEGER'))
            conn.commit()
            print("Added state_id column.")
        except Exception:
            pass  # Column already exists

    print("Database setup complete.")
    sys.exit(0)
