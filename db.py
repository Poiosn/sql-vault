"""
Run this script once to create all database tables on Railway (or any environment).
Usage: python db.py
Railway will run this automatically via the releaseCommand in railway.toml.
"""

from app import app, db

with app.app_context():
    db.create_all()

    # Add state_id column to existing databases that predate this field
    with db.engine.connect() as conn:
        try:
            conn.execute(db.text("ALTER TABLE query ADD COLUMN state_id INTEGER"))
            conn.commit()
            print("Added state_id column.")
        except Exception:
            pass  # Column already exists

    print("All tables created successfully.")
