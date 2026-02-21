# Project Testing Framework

Lightweight, phase-based testing system for all projects.

## Philosophy

- **Test at the right time** — Not everything needs tests, but critical paths do
- **Fail fast** — Catch breaking changes before they reach production
- **Low friction** — Tests should be easy to write and run

## Test Structure

```
tests/
├── unit/                    # Unit tests (fast, isolated)
│   ├── test_models.py       # Database models
│   ├── test_api.py          # API endpoints
│   └── test_utils.py        # Helper functions
├── integration/             # Integration tests (slower, more realistic)
│   ├── test_flows.py        # User flows
│   └── test_import.py       # Bulk operations
└── e2e/                     # End-to-end tests (slowest, full paths)
    └── test_critical.py     # Critical user journeys
```

## Phase-Based Testing

| Phase | Focus | Test Types | When to Write |
|-------|-------|------------|---------------|
| **1** | Data/Backend | Unit (models, APIs) | During development |
| **2** | Frontend | Component/Integration | After UI stabilizes |
| **3** | Integration | Flow tests | Before feature complete |
| **4** | Full System | E2E | Before production |

## Running Tests

```bash
# Run all tests
python -m pytest tests/

# Run specific category
python -m pytest tests/unit/
python -m pytest tests/integration/

# Run with coverage
python -m pytest tests/ --cov=.

# Run specific test
python -m pytest tests/unit/test_models.py::TestQuestion::test_mnemonic_fields
```

## Test Naming Convention

- Files: `test_<module>.py`
- Classes: `Test<Feature>`
- Functions: `test_<what>_<condition>_<expected>`
  - `test_hint_reveal_returns_acronym`
  - `test_mnemonic_disabled_returns_404`

## Assertions to Use

```python
# Prefer these patterns
assert response.status_code == 200
assert question.mnemonic_enabled is True
assert 'acronym' in response.json()['hint']

# Avoid
assert response.json()  # too vague
assert len(data) > 0    # not specific enough
```

## Fixtures

Create `tests/conftest.py` for shared setup:

```python
import pytest
from app import app, db, Question

@pytest.fixture
def client():
    """Test client with test database"""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.drop_all()

@pytest.fixture
def sample_question(client):
    """Create a question with mnemonic for testing"""
    q = Question(
        question="Test question?",
        options='["A", "B", "C", "D"]',
        correct_answer=0,
        explanation="Test explanation",
        mnemonic_enabled=True,
        mnemonic_acronym="TEST",
        mnemonic_expansion="T - Test\nE - Example",
        mnemonic_teaching_context="This is a test"
    )
    db.session.add(q)
    db.session.commit()
    return q
```

## What to Test

### Always Test
- Database migrations (forward and rollback)
- API contracts (inputs/outputs don't change unexpectedly)
- Critical user paths (quiz flow, admin operations)
- Import/export functionality

### Sometimes Test
- UI rendering (if complex)
- Third-party integrations (mocked)
- Performance (if critical)

### Skip Testing
- Simple getters/setters
- Static content
- Prototype/experimental features

## Coverage Goals

| Category | Target | Why |
|----------|--------|-----|
| Models | 90%+ | Data integrity is critical |
| APIs | 80%+ | Contract stability |
| Views | 60%+ | UI changes frequently |
| Utils | 70%+ | Reusable code |

## Adding Tests to CI/CD

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-cov
      - run: pytest tests/ --cov=. --cov-report=xml
      - uses: codecov/codecov-action@v1
```

## New Project Checklist

When starting a new project:

- [ ] Create `tests/` directory
- [ ] Add `pytest` to requirements
- [ ] Create `conftest.py` with fixtures
- [ ] Write first test for core model
- [ ] Add test command to README
- [ ] Set up CI if applicable

## EMS Platform Specific

See `tests/` directory for examples:
- `test_models.py` — Question model with mnemonic fields
- `test_api.py` — Hint and teaching moment endpoints
- `test_import.py` — Bulk import with optional mnemonic fields
