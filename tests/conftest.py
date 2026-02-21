"""
Test configuration and fixtures for EMS Learning Platform.
"""

import os
import sys

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import Question, User, app, db


@pytest.fixture
def client():
    """Test client with in-memory SQLite database."""
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["WTF_CSRF_ENABLED"] = False

    with app.test_client() as client, app.app_context():
        db.create_all()
        yield client
        db.drop_all()


@pytest.fixture
def auth_client(client):
    """Authenticated test client with logged-in user."""
    with client.session_transaction() as sess:
        sess["user_id"] = 1
    return client


@pytest.fixture
def admin_client(client):
    """Admin authenticated test client."""
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    return client


@pytest.fixture
def sample_question():
    """Create a basic question without mnemonic."""
    q = Question(
        level="EMT",
        category="Test",
        subcategory="Unit",
        question="What is the test answer?",
        options='["A", "B", "C", "D"]',
        correct_answer=0,
        explanation="A is correct because it is first.",
        source="Test Source",
    )
    db.session.add(q)
    db.session.commit()
    return q


@pytest.fixture
def sample_question_with_mnemonic():
    """Create a question with full mnemonic data."""
    q = Question(
        level="EMT",
        category="Cardiovascular",
        subcategory="Assessment",
        question="A patient reports chest pain. What assessment tool should you use?",
        options='["AVPU", "SAMPLE", "OPQRST", "DCAP-BTLS"]',
        correct_answer=2,
        explanation="OPQRST is the standard mnemonic for assessing chest pain.",
        source="SNHD Protocols",
        mnemonic_enabled=True,
        mnemonic_acronym="OPQRST",
        mnemonic_expansion="O - Onset (when did it start?)\n"
        "P - Provocation (what makes it better/worse?)\n"
        "Q - Quality (sharp, dull, pressure?)\n"
        "R - Radiation (does it move?)\n"
        "S - Severity (rate 1-10)\n"
        "T - Time (how long has it lasted?)",
        mnemonic_teaching_context="This question asks about chest pain assessment, "
        "the classic use case for OPQRST.",
    )
    db.session.add(q)
    db.session.commit()
    return q


@pytest.fixture
def sample_user():
    """Create a test user."""
    u = User(name="Test User", level="EMT")
    db.session.add(u)
    db.session.commit()
    return u
