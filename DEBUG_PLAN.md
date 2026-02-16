# EMS Learning Platform — Debug Plan

## 1. Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Client    │────▶│  Flask App   │────▶│  SQLite (data/  │
│  (Browser)  │     │  app.py      │     │   protocols.db)  │
└─────────────┘     └──────────────┘     └─────────────────┘
       │                     │
       │                     │ Session: user_id, admin_logged_in
       │                     │
       ▼                     ▼
  templates/           Routes: /, /register, /dashboard,
  index.html           /quiz, /submit_answer, /results,
  dashboard.html       /admin/*
  quiz.html
  results.html
```

### Stack
- **Backend:** Flask 3.0, Flask-SQLAlchemy, SQLite
- **Frontend:** Vanilla JS, server-rendered Jinja2 templates
- **Deploy targets:** Local (port 5001), PythonAnywhere, Vercel (ephemeral `/tmp` DB)

---

## 2. Critical Paths & Failure Points

### Path A: User Registration → Dashboard
| Step | Route | Failure Points |
|------|-------|----------------|
| 1 | `POST /register` | Missing `level`, DB write failure, session not set |
| 2 | `GET /dashboard` | `user_id` not in session → redirect `/`; `User.query.get(id)` returns `None` if user deleted |

### Path B: Quiz Flow
| Step | Route | Failure Points |
|------|-------|----------------|
| 1 | `GET /quiz` | Stale session (user deleted) → clear session, redirect; `question_id`/`correct_answer` in template |
| 2 | `POST /submit_answer` | No `user_id` in session (500); missing `question_id`/`correct` in JSON; invalid `question_id`; `Question.query.get(id)` returns `None` → `question.explanation` AttributeError |
| 3 | Quiz JS | `totalQuestions === 0` → divide-by-zero in progress; `dataset.questionId` is string, `question_id` sent as string to API |

### Path C: Results & Stats
| Step | Route | Failure Points |
|------|-------|----------------|
| 1 | `GET /results` | `User.query.get(session['user_id'])` returns `None` → `user.get_score_stats()` AttributeError |
| 2 | `GET /api/stats` | Same `User` lookup; JSON response |

### Path D: Admin
| Step | Route | Failure Points |
|------|-------|----------------|
| 1 | `POST /admin/login` | `check_password_hash` with wrong password |
| 2 | CRUD | `request.json` missing keys; `Question.query.get_or_404`; duplicate routes (`/admin`, `/admin/question/add` vs `/admin/question/new`) |

### Path E: Data & DB
| Concern | Failure Points |
|---------|----------------|
| `Question.get_options()` | `json.loads(self.options)` fails if options is malformed or `None` |
| DB path | Vercel: `/tmp/protocols.db` (ephemeral); Local: `data/protocols.db` |
| `correct_answer` | Must be int 0–3; stored as int, compared with JS `parseInt` |

---

## 3. Hypotheses Framework

When a bug is reported, generate 3–5 hypotheses such as:

1. **Session / Auth:** Session expired, `user_id` missing, or user record deleted after server/DB reset.
2. **Request payload:** Missing or wrong-type `question_id`, `correct`, or `level` in JSON/form.
3. **DB / Model:** `User` or `Question` not found; `options` JSON invalid; FK/constraint violation.
4. **Quiz filtering:** Category/subcategory returns 0 questions; level filter excludes all questions.
5. **JS / Template:** `totalQuestions === 0`, wrong `data-question-id`/`data-correct`; wrong variable passed to template.

---

## 4. Instrumentation Strategy

### Logging Configuration (this session)
- **Log path:** `/Users/anhta/Github/ems-learning-platform/ems-learning-platform/.cursor/debug.log`
- **Server endpoint:** `http://127.0.0.1:7242/ingest/25812e1e-bc00-4c76-abc4-4124bbacc27a`
- **Format:** NDJSON (one JSON object per line)
- **Session ID:** (not provided) — omit `sessionId` and `X-Debug-Session-Id`

### Python log helper (append NDJSON line)
```python
# At top of app.py
DEBUG_LOG_PATH = os.path.join(os.path.dirname(__file__), '.cursor', 'debug.log')

def _debug_log(location, message, data=None, hypothesis_id=None):
    try:
        payload = {"location": location, "message": message, "timestamp": __import__("time").time() * 1000}
        if data is not None: payload["data"] = data
        if hypothesis_id: payload["hypothesisId"] = hypothesis_id
        with open(DEBUG_LOG_PATH, "a") as f:
            f.write(__import__("json").dumps(payload) + "\n")
    except Exception:
        pass
```

### Placement matrix
| Hypothesis | Location | What to log |
|------------|----------|-------------|
| A (Session) | `dashboard`, `quiz`, `results`, `submit_answer` | `session.keys()`, `user_id`, `user is None` |
| B (Request) | `register`, `submit_answer`, `add_question` | `request.json` / `request.form` (sanitize) |
| C (DB/Model) | `submit_answer`, `quiz`, `Question.get_options` | `question_id`, `question is None`, options parse result |
| D (Filter) | `quiz` | `len(questions)`, `category`, `subcategory`, `user.level` |
| E (JS) | quiz.html `<script>` | `totalQuestions`, `qid`, `correctIndex` via fetch to ingest endpoint |

---

## 5. Instrumentation Regions

Wrap debug logs in collapsible regions:

```python
# #region agent log
_debug_log("app.py:submit_answer", "submit_answer entry", {"user_id": session.get("user_id"), "data_keys": list(data.keys()) if data else []}, "A")
# #endregion
```

---

## 6. Reproduction Steps Template

```markdown
<reproduction_steps>
1. Start the app: `source venv/bin/activate && python app.py`
2. Open http://localhost:5001 in browser
3. [Describe user actions: register, take quiz, etc.]
4. Observe the bug: [what happens vs expected]
</reproduction_steps>
```

---

## 7. Debug Workflow

1. **User reports bug** → capture exact steps and error (browser console, server traceback).
2. **Generate hypotheses** → 3–5 specific hypotheses with subsystem/location.
3. **Add instrumentation** → 2–6 logs, each mapped to at least one hypothesis; use `hypothesisId`.
4. **Clear log file** → Delete `.cursor/debug.log` before each run.
5. **Reproduce** → User runs with instrumentation; use reproduction steps block.
6. **Analyze logs** → Read NDJSON, mark each hypothesis CONFIRMED/REJECTED/INCONCLUSIVE.
7. **Fix** → Apply only fixes supported by evidence; keep instrumentation.
8. **Verify** → User reproduces again; compare before/after logs; confirm success.
9. **Cleanup** → Remove instrumentation after verified success or explicit user approval.

---

## 8. Quick Reference: Key Files

| File | Purpose |
|------|---------|
| `app.py` | Flask routes, models, `init_sample_questions()` |
| `templates/quiz.html` | Quiz UI, option click handler, `/submit_answer` fetch |
| `templates/index.html` | Registration form (level only; name defaults to "Student") |
| `data/protocols.db` | SQLite DB (local); `/tmp/protocols.db` on Vercel |
| `.cursor/debug.log` | NDJSON debug logs (this session) |
