"""Migration: Add protocol_link column to question table"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from sqlalchemy import text, inspect


def upgrade():
    """Add protocol_link column"""
    with app.app_context():
        # Check if column exists
        inspector = inspect(db.engine)
        columns = [col["name"] for col in inspector.get_columns("question")]

        if "protocol_link" not in columns:
            db.session.execute(
                text("ALTER TABLE question ADD COLUMN protocol_link VARCHAR(500)")
            )
            db.session.commit()
            print("✓ Added protocol_link column to question table")
        else:
            print("✓ protocol_link column already exists")


def downgrade():
    """Remove protocol_link column"""
    with app.app_context():
        db.session.execute(text("ALTER TABLE question DROP COLUMN protocol_link"))
        db.session.commit()
        print("✓ Removed protocol_link column")


if __name__ == "__main__":
    upgrade()
