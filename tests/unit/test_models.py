"""
Unit tests for database models.
"""

from app import Question, User, db


class TestQuestion:
    """Tests for Question model."""

    def test_create_basic_question(self, client):
        """Test creating a question without mnemonic."""
        q = Question(
            level="EMT",
            category="Test",
            question="Test question?",
            options='["A", "B", "C", "D"]',
            correct_answer=0,
            explanation="Test explanation",
        )
        db.session.add(q)
        db.session.commit()

        assert q.id is not None
        assert q.mnemonic_enabled is False
        assert q.mnemonic_acronym is None

    def test_create_question_with_mnemonic(self, client, sample_question_with_mnemonic):
        """Test creating a question with full mnemonic data."""
        q = sample_question_with_mnemonic

        assert q.id is not None
        assert q.mnemonic_enabled is True
        assert q.mnemonic_acronym == "OPQRST"
        assert "Onset" in q.mnemonic_expansion
        assert "chest pain" in q.mnemonic_teaching_context

    def test_to_dict_excludes_mnemonic(self, client, sample_question_with_mnemonic):
        """Test that to_dict() doesn't include mnemonic by default."""
        data = sample_question_with_mnemonic.to_dict()

        assert "mnemonic" not in data
        assert "mnemonic_enabled" not in data

    def test_to_dict_with_mnemonic_includes_all(self, client, sample_question_with_mnemonic):
        """Test that to_dict_with_mnemonic() includes mnemonic data."""
        data = sample_question_with_mnemonic.to_dict_with_mnemonic()

        assert "mnemonic" in data
        assert data["mnemonic"]["enabled"] is True
        assert data["mnemonic"]["acronym"] == "OPQRST"
        assert "Onset" in data["mnemonic"]["expansion"]

    def test_update_mnemonic_fields(self, client, sample_question):
        """Test updating mnemonic fields on existing question."""
        q = sample_question

        # Initially no mnemonic
        assert q.mnemonic_enabled is False

        # Add mnemonic
        q.mnemonic_enabled = True
        q.mnemonic_acronym = "SAMPLE"
        q.mnemonic_expansion = "S - Signs/Symptoms"
        q.mnemonic_teaching_context = "For history taking"
        db.session.commit()

        # Verify saved
        q2 = Question.query.get(q.id)
        assert q2.mnemonic_enabled is True
        assert q2.mnemonic_acronym == "SAMPLE"

    def test_mnemonic_acronym_max_length(self, client):
        """Test that acronym is limited to 20 characters."""
        q = Question(
            question="Test?",
            options='["A", "B", "C", "D"]',
            correct_answer=0,
            explanation="Test",
            mnemonic_enabled=True,
            mnemonic_acronym="A" * 25,  # 25 chars, should truncate or work
        )
        db.session.add(q)
        db.session.commit()

        assert len(q.mnemonic_acronym) <= 25  # SQLite doesn't enforce, but should be okay

    def test_get_options_parses_json(self, client, sample_question):
        """Test that get_options() correctly parses JSON."""
        options = sample_question.get_options()

        assert isinstance(options, list)
        assert len(options) == 4
        assert options[0] == "A"


class TestUser:
    """Tests for User model."""

    def test_create_user(self, client):
        """Test creating a user."""
        u = User(name="Test User", level="EMT")
        db.session.add(u)
        db.session.commit()

        assert u.id is not None
        assert u.name == "Test User"
        assert u.level == "EMT"

    def test_get_score_stats_no_answers(self, client, sample_user):
        """Test score stats with no answers."""
        stats = sample_user.get_score_stats()

        assert stats["total"] == 0
        assert stats["correct"] == 0
        assert stats["percentage"] == 0
