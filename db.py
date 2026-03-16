"""
Creates all database tables. Run via Railway releaseCommand before app starts.
Usage: python3 db.py
"""

import os
import sys

database_url = os.environ.get("DATABASE_URL", "")
if not database_url:
    print("WARNING: DATABASE_URL not set, using SQLite.")

from app import app, db

with app.app_context():
    # SQLAlchemy ORM creates all model tables (works for MySQL, PostgreSQL, SQLite)
    try:
        db.create_all()
        print("db.create_all() completed.")
    except Exception as e:
        print(f"WARNING: db.create_all() failed: {e}")

    # Migration: rename old 'sql' column to 'sql_query' if needed
    try:
        with db.engine.connect() as conn:
            # MySQL syntax
            try:
                conn.execute(db.text("ALTER TABLE `query` CHANGE `sql` sql_query TEXT NOT NULL"))
                conn.commit()
                print("Renamed column sql -> sql_query (MySQL).")
            except Exception:
                pass

            # Add state_id if missing
            try:
                conn.execute(db.text("ALTER TABLE `query` ADD COLUMN state_id INTEGER"))
                conn.commit()
                print("Added state_id column.")
            except Exception:
                pass
    except Exception as e:
        print(f"WARNING: migration failed: {e}")

    print("Database setup complete.")
    sys.exit(0)
