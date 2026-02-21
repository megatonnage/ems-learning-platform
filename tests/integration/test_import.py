"""
Integration tests for bulk import functionality.
"""

import io
import json

from app import Question


class TestJsonImport:
    """Tests for JSON import with mnemonic fields."""

    def test_import_without_mnemonic(self, admin_client):
        """Test importing question without mnemonic fields."""
        data = [
            {
                "question": "Import test without mnemonic?",
                "options": ["A", "B", "C", "D"],
                "correct_answer": 0,
                "explanation": "Test explanation",
                "level": "EMT",
                "category": "Test",
            }
        ]

        response = admin_client.post(
            "/admin/import/json",
            data={"file": (io.BytesIO(json.dumps(data).encode()), "test.json")},
            content_type="multipart/form-data",
        )

        assert response.status_code == 200
        result = response.get_json()
        assert result["success"] is True
        assert result["imported"] == 1

        # Verify mnemonic is disabled by default
        q = Question.query.filter_by(question="Import test without mnemonic?").first()
        assert q is not None
        assert q.mnemonic_enabled is False

    def test_import_with_mnemonic(self, admin_client):
        """Test importing question with mnemonic fields."""
        data = [
            {
                "question": "Import test with mnemonic?",
                "options": ["A", "B", "C", "D"],
                "correct_answer": 0,
                "explanation": "Test",
                "level": "EMT",
                "category": "Test",
                "mnemonic_enabled": True,
                "mnemonic_acronym": "IMPORT",
                "mnemonic_expansion": "I - Import\nM - Mnemonic",
                "mnemonic_teaching_context": "This is an import test",
            }
        ]

        response = admin_client.post(
            "/admin/import/json",
            data={"file": (io.BytesIO(json.dumps(data).encode()), "test.json")},
            content_type="multipart/form-data",
        )

        assert response.status_code == 200
        result = response.get_json()
        assert result["imported"] == 1

        # Verify mnemonic was saved
        q = Question.query.filter_by(question="Import test with mnemonic?").first()
        assert q.mnemonic_enabled is True
        assert q.mnemonic_acronym == "IMPORT"

    def test_import_update_existing_with_mnemonic(self, admin_client, sample_question):
        """Test updating existing question with mnemonic via import."""
        # Import with same question text but add mnemonic
        data = [
            {
                "question": sample_question.question,  # Same question
                "options": ["A", "B", "C", "D"],
                "correct_answer": 0,
                "explanation": "Updated explanation",
                "mnemonic_enabled": True,
                "mnemonic_acronym": "UPDATE",
            }
        ]

        response = admin_client.post(
            "/admin/import/json",
            data={"file": (io.BytesIO(json.dumps(data).encode()), "test.json")},
            content_type="multipart/form-data",
        )

        assert response.status_code == 200
        result = response.get_json()
        assert result["updated"] == 1

        # Verify mnemonic was added
        q = Question.query.get(sample_question.id)
        assert q.mnemonic_enabled is True
        assert q.mnemonic_acronym == "UPDATE"


class TestCsvImport:
    """Tests for CSV import with mnemonic fields."""

    def test_csv_import_without_mnemonic(self, admin_client):
        """Test CSV import without mnemonic columns."""
        csv_data = """question,option_0,option_1,option_2,option_3,correct_answer,explanation,level,category
CSV test no mnemonic,A,B,C,D,0,Test,EMT,Test"""

        response = admin_client.post(
            "/admin/import/csv",
            data={"file": (io.BytesIO(csv_data.encode()), "test.csv")},
            content_type="multipart/form-data",
        )

        assert response.status_code == 200
        result = response.get_json()
        assert result["imported"] == 1

        q = Question.query.filter_by(question="CSV test no mnemonic").first()
        assert q.mnemonic_enabled is False

    def test_csv_import_with_mnemonic(self, admin_client):
        """Test CSV import with mnemonic columns."""
        csv_data = """question,option_0,option_1,option_2,option_3,correct_answer,explanation,level,category,mnemonic_enabled,mnemonic_acronym,mnemonic_expansion,mnemonic_teaching_context
CSV test with mnemonic,A,B,C,D,0,Test,EMT,Test,true,ABC,A - Alpha,B - Beta,C - Charlie,Test context"""

        response = admin_client.post(
            "/admin/import/csv",
            data={"file": (io.BytesIO(csv_data.encode()), "test.csv")},
            content_type="multipart/form-data",
        )

        assert response.status_code == 200
        result = response.get_json()
        assert result["imported"] == 1

        q = Question.query.filter_by(question="CSV test with mnemonic").first()
        assert q.mnemonic_enabled is True
        assert q.mnemonic_acronym == "ABC"

    def test_csv_import_mnemonic_case_insensitive(self, admin_client):
        """Test that mnemonic_enabled accepts various true values."""
        test_cases = [
            ("true", True),
            ("TRUE", True),
            ("True", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            ("false", False),
            ("", False),
        ]

        for value, expected in test_cases:
            csv_data = f"""question,option_0,option_1,option_2,option_3,correct_answer,explanation,level,category,mnemonic_enabled,mnemonic_acronym
Test {value},A,B,C,D,0,Test,EMT,Test,{value},TEST"""

            response = admin_client.post(
                "/admin/import/csv",
                data={"file": (io.BytesIO(csv_data.encode()), "test.csv")},
                content_type="multipart/form-data",
            )

            assert response.status_code == 200
            q = Question.query.filter_by(question=f"Test {value}").first()
            assert q is not None
            assert q.mnemonic_enabled is expected, f"Failed for value: {value}"
