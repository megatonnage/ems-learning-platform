"""
Unit tests for API endpoints.
"""


class TestHintAPI:
    """Tests for mnemonic hint endpoints."""

    def test_reveal_hint_requires_auth(self, client, sample_question_with_mnemonic):
        """Test that hint endpoint requires authentication."""
        q = sample_question_with_mnemonic
        response = client.post(f"/api/question/{q.id}/hint")

        assert response.status_code == 401
        assert "Not authenticated" in response.get_json()["error"]

    def test_reveal_hint_returns_acronym(self, auth_client, sample_question_with_mnemonic):
        """Test that hint endpoint returns acronym for enabled question."""
        q = sample_question_with_mnemonic
        response = auth_client.post(f"/api/question/{q.id}/hint")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["hint"]["acronym"] == "OPQRST"

    def test_reveal_hint_disabled_returns_404(self, auth_client, sample_question):
        """Test that hint returns 404 for questions without mnemonic."""
        q = sample_question
        response = auth_client.post(f"/api/question/{q.id}/hint")

        assert response.status_code == 404
        assert "No hint available" in response.get_json()["error"]

    def test_reveal_hint_nonexistent_question(self, auth_client):
        """Test hint endpoint for non-existent question."""
        response = auth_client.post("/api/question/99999/hint")

        assert response.status_code == 404


class TestMnemonicAPI:
    """Tests for full mnemonic endpoint."""

    def test_get_mnemonic_requires_auth(self, client, sample_question_with_mnemonic):
        """Test that mnemonic endpoint requires authentication."""
        q = sample_question_with_mnemonic
        response = client.get(f"/api/question/{q.id}/mnemonic")

        assert response.status_code == 401

    def test_get_mnemonic_returns_full_data(self, auth_client, sample_question_with_mnemonic):
        """Test that mnemonic endpoint returns all fields."""
        q = sample_question_with_mnemonic
        response = auth_client.get(f"/api/question/{q.id}/mnemonic")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["mnemonic"]["acronym"] == "OPQRST"
        assert "Onset" in data["mnemonic"]["expansion"]
        assert "chest pain" in data["mnemonic"]["teaching_context"]

    def test_get_mnemonic_disabled_returns_404(self, auth_client, sample_question):
        """Test that mnemonic returns 404 for disabled questions."""
        q = sample_question
        response = auth_client.get(f"/api/question/{q.id}/mnemonic")

        assert response.status_code == 404


class TestAdminAPI:
    """Tests for admin endpoints."""

    def test_list_questions_with_mnemonics_requires_admin(
        self, client, sample_question_with_mnemonic
    ):
        """Test that admin list requires admin auth."""
        response = client.get("/api/questions/with-mnemonics")

        # Should redirect to login or return 401
        assert response.status_code in [302, 401, 403]

    def test_list_questions_with_mnemonics_returns_data(
        self, admin_client, sample_question_with_mnemonic
    ):
        """Test that admin list returns mnemonic data."""
        response = admin_client.get("/api/questions/with-mnemonics")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert len(data["questions"]) > 0

        # Check first question has mnemonic data
        q = data["questions"][0]
        assert "mnemonic" in q

    def test_get_question_json_includes_mnemonic(self, admin_client, sample_question_with_mnemonic):
        """Test that admin JSON endpoint includes mnemonic."""
        q = sample_question_with_mnemonic
        response = admin_client.get(f"/admin/question/{q.id}/json")

        assert response.status_code == 200
        data = response.get_json()
        assert "mnemonic" in data
        assert data["mnemonic"]["acronym"] == "OPQRST"
