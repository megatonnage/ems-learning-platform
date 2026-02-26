import json
import os
import random
from datetime import datetime
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "ems-learning-secret-key"

# Database configuration
# Priority: 1) DATABASE_URL (PostgreSQL for production/Vercel)
#          2) Local SQLite for development
if os.environ.get("DATABASE_URL"):
    # Production: Use PostgreSQL (Supabase, Neon, etc.)
    # Fix for SQLAlchemy compatibility with Postgres URL
    database_url = os.environ.get("DATABASE_URL")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    # Development: Use SQLite
    if os.environ.get("VERCEL"):
        db_path = os.path.join("/tmp", "protocols.db")
    else:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "protocols.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# Security Headers - CSP to allow inline scripts for admin panel
@app.after_request
def add_security_headers(response):
    # Allow inline scripts and styles for the admin panel functionality
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


# Admin Configuration
# Set admin password via environment variable: export EMS_ADMIN_PASSWORD=your_secure_password
# Required in production - app will not start without this set
ADMIN_PASSWORD = os.environ.get("EMS_ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    raise ValueError(
        "EMS_ADMIN_PASSWORD environment variable must be set. "
        "For local development: export EMS_ADMIN_PASSWORD=your_secure_password "
        "For production: Set in Vercel Dashboard → Settings → Environment Variables"
    )
# Use pbkdf2:sha256 for compatibility (scrypt not available on all Python builds)
ADMIN_PASSWORD_HASH = generate_password_hash(ADMIN_PASSWORD, method="pbkdf2:sha256")


def admin_required(f):
    """Decorator to require admin authentication"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)

    return decorated_function


# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    level = db.Column(db.String(20))  # EMT, AEMT, PARAMEDIC
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_score_stats(self):
        answers = Answer.query.filter_by(user_id=self.id).all()
        if not answers:
            return {"total": 0, "correct": 0, "percentage": 0}
        correct = sum(1 for a in answers if a.correct)
        return {
            "total": len(answers),
            "correct": correct,
            "percentage": round((correct / len(answers)) * 100, 1),
        }


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(20))
    category = db.Column(db.String(100))  # Main category (e.g., 'Medications', 'Boluses')
    subcategory = db.Column(db.String(100))  # Subcategory (e.g., 'Adult', 'Pediatric')
    question = db.Column(db.Text)
    options = db.Column(db.Text)  # JSON
    correct_answer = db.Column(db.Integer)
    explanation = db.Column(db.Text)
    source = db.Column(db.String(200))

    # Mnemonic hint fields
    mnemonic_enabled = db.Column(db.Boolean, default=False)
    mnemonic_acronym = db.Column(db.String(20))  # e.g., "OPQRST"
    mnemonic_expansion = db.Column(db.Text)  # Full expansion
    mnemonic_teaching_context = db.Column(db.Text)  # Why this applies

    def get_options(self):
        return json.loads(self.options)

    def to_dict(self):
        return {
            "id": self.id,
            "level": self.level,
            "category": self.category,
            "subcategory": self.subcategory,
            "question": self.question,
            "options": self.options,
            "correct_answer": self.correct_answer,
            "explanation": self.explanation,
            "source": self.source,
        }

    def to_dict_with_mnemonic(self):
        """Include mnemonic data for admin/editing purposes"""
        data = self.to_dict()
        data["mnemonic"] = {
            "enabled": self.mnemonic_enabled,
            "acronym": self.mnemonic_acronym,
            "expansion": self.mnemonic_expansion,
            "teaching_context": self.mnemonic_teaching_context,
        }
        return data


class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"))
    correct = db.Column(db.Boolean)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    time_spent = db.Column(db.Integer)


# Routes
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["POST"])
def register():
    name = request.form.get("name", "Student")
    level = request.form["level"]
    user = User(name=name, level=level)
    db.session.add(user)
    db.session.commit()
    session["user_id"] = user.id
    return jsonify({"success": True, "user_id": user.id})


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/")
    user = User.query.get(session["user_id"])
    stats = user.get_score_stats()
    return render_template("dashboard.html", user=user, stats=stats)


@app.route("/quiz")
def quiz():
    if "user_id" not in session:
        return redirect("/")
    user = User.query.get(session["user_id"])

    # Handle stale sessions (e.g. server restart/redeploy cleared the DB)
    if not user:
        session.clear()
        return redirect("/")

    # Get filter parameters
    category = request.args.get("category", "all")
    subcategory = request.args.get("subcategory", "all")
    limit = request.args.get("limit", "all")  # 'all' or '10'

    # Build base query - show questions for user's level and below
    if user.level == "PARAMEDIC":
        base_query = Question.query
    elif user.level == "AEMT":
        base_query = Question.query.filter(Question.level.in_(["EMT", "AEMT"]))
    else:  # EMT
        base_query = Question.query.filter_by(level="EMT")

    questions = []

    if category == "all":
        # No category filter - but check for subcategory filter
        if subcategory != "all":
            # Filter by subcategory only
            questions = base_query.filter_by(subcategory=subcategory).all()
        else:
            # No filters - get all questions for user's level
            questions = base_query.all()
    else:
        # Filter by category - also include pediatric questions with matching subcategory
        # For example, "Fluid Boluses" should include "Pediatric" category with "Fluid Boluses" subcategory

        # First get questions in the main category
        main_query = base_query.filter_by(category=category)
        if subcategory != "all":
            main_query = main_query.filter_by(subcategory=subcategory)
        questions = main_query.all()

        # Then get pediatric questions with matching subcategory
        # Map category names to subcategory names
        subcategory_map = {"Fluid Boluses": "Fluid Boluses", "Medications": "Medications"}

        if category in subcategory_map:
            pediatric_query = base_query.filter_by(
                category="Pediatric", subcategory=subcategory_map[category]
            )
            pediatric_questions = pediatric_query.all()
            # Add pediatric questions to main list
            questions.extend(pediatric_questions)

        # If still no questions, try all levels
        if not questions:
            all_levels_query = Question.query.filter_by(category=category)
            if subcategory != "all":
                all_levels_query = all_levels_query.filter_by(subcategory=subcategory)
            questions = all_levels_query.all()

    # Remove duplicates (in case of overlap)
    seen_ids = set()
    unique_questions = []
    for q in questions:
        if q.id not in seen_ids:
            seen_ids.add(q.id)
            unique_questions.append(q)
    questions = unique_questions

    # Get available categories for Quick Topic Selection
    categories = db.session.query(Question.category).distinct().all()
    categories = [c[0] for c in categories if c[0]]

    # Get available subcategories for More Topics dropdown
    subcategories = db.session.query(Question.subcategory).distinct().all()
    subcategories = [s[0] for s in subcategories if s[0]]

    # Get total count before limiting
    total_available = len(questions)

    # Shuffle questions
    random.shuffle(questions)

    # Limit to 10 only if no category filter and limit != 'all'
    if limit != "all" and category == "all":
        questions = questions[:10]

    return render_template(
        "quiz.html",
        questions=questions,
        user=user,
        categories=categories,
        subcategories=subcategories,
        selected_category=category,
        selected_subcategory=subcategory,
        total_available=total_available,
    )


@app.route("/submit_answer", methods=["POST"])
def submit_answer():
    data = request.json
    answer = Answer(
        user_id=session["user_id"],
        question_id=data["question_id"],
        correct=data["correct"],
        time_spent=data.get("time_spent", 0),
    )
    db.session.add(answer)
    db.session.commit()

    # Get explanation
    question = Question.query.get(data["question_id"])
    return jsonify(
        {
            "correct": data["correct"],
            "explanation": question.explanation,
            "correct_answer": question.correct_answer,
        }
    )


@app.route("/results")
def results():
    if "user_id" not in session:
        return redirect("/")
    user = User.query.get(session["user_id"])
    stats = user.get_score_stats()

    # Get all answers with question details
    all_answers = (
        db.session.query(Answer, Question)
        .join(Question)
        .filter(Answer.user_id == user.id)
        .order_by(Answer.timestamp.desc())
        .all()
    )

    # Pagination
    page = request.args.get("page", 1, type=int)
    per_page = 20
    total = len(all_answers)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    # Ensure page is valid
    page = max(1, min(page, total_pages))

    # Slice results for current page
    start = (page - 1) * per_page
    end = start + per_page
    recent = all_answers[start:end]

    return render_template(
        "results.html",
        user=user,
        stats=stats,
        recent=recent,
        page=page,
        total_pages=total_pages,
        total=total,
        per_page=per_page,
    )


@app.route("/api/stats")
def api_stats():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"})
    user = User.query.get(session["user_id"])
    return jsonify(user.get_score_stats())


@app.route("/api/update_level", methods=["POST"])
def api_update_level():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    level = data.get("level")
    if level not in ("EMT", "AEMT", "PARAMEDIC"):
        return jsonify({"error": "Invalid level"}), 400
    user = User.query.get(session["user_id"])
    if not user:
        return jsonify({"error": "User not found"}), 404
    user.level = level
    db.session.commit()
    return jsonify({"success": True, "level": level})


# Admin Routes


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Admin login page"""
    if request.method == "POST":
        password = request.form.get("password", "")
        if check_password_hash(ADMIN_PASSWORD_HASH, password):
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        else:
            return render_template("admin_login.html", error="Invalid password")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    """Admin logout"""
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin():
    questions = Question.query.all()
    categories = db.session.query(Question.category).distinct().all()
    categories = [c[0] for c in categories if c[0]]
    return render_template("admin.html", questions=questions, categories=categories)


@app.route("/admin/question/add", methods=["POST"])
@admin_required
def add_question():
    data = request.json
    q = Question(
        level=data["level"],
        category=data["category"],
        subcategory=data["subcategory"],
        question=data["question"],
        options=data["options"],  # Already JSON string from frontend
        correct_answer=data["correct_answer"],
        explanation=data["explanation"],
        source=data["source"],
    )
    db.session.add(q)
    db.session.commit()
    return jsonify({"success": True, "id": q.id})


@app.route("/admin/question/edit/<int:id>", methods=["POST"])
@admin_required
def edit_question(id):
    q = Question.query.get_or_404(id)
    data = request.json

    q.level = data["level"]
    q.category = data["category"]
    q.subcategory = data["subcategory"]
    q.question = data["question"]
    q.options = data["options"]
    q.correct_answer = data["correct_answer"]
    q.explanation = data["explanation"]
    q.source = data["source"]

    db.session.commit()
    return jsonify({"success": True})


@app.route("/admin/question/delete/<int:id>", methods=["POST"])
@admin_required
def delete_question(id):
    q = Question.query.get_or_404(id)
    db.session.delete(q)
    db.session.commit()
    return jsonify({"success": True})


# Initialize with sample questions
def init_sample_questions():
    """Add comprehensive SNHD protocol questions"""
    sample_questions = [
        # === FLUID BOLUSES - ADULT ===
        {
            "level": "AEMT",
            "category": "Fluid Boluses",
            "subcategory": "Adult",
            "question": "What is the standard adult fluid bolus amount for a patient in shock?",
            "options": ["250 mL", "500 mL", "1000 mL", "2000 mL"],
            "correct_answer": 2,
            "explanation": "Standard adult fluid bolus is 1000 mL (1 liter) of isotonic crystalloid solution.",
            "source": "SNHD Protocols - Fluid Therapy",
        },
        {
            "level": "AEMT",
            "category": "Fluid Boluses",
            "subcategory": "Adult",
            "question": "For an adult trauma patient with suspected hemorrhagic shock, how much fluid should be administered before reassessment?",
            "options": ["250 mL", "500 mL", "1000 mL", "2000 mL"],
            "correct_answer": 2,
            "explanation": "Administer 1000 mL bolus and reassess. Target systolic BP of 90 mmHg (permissive hypotension).",
            "source": "SNHD Protocols - Shock",
        },
        {
            "level": "AEMT",
            "category": "Fluid Boluses",
            "subcategory": "Adult",
            "question": "In traumatic brain injury with signs of herniation, what is the target systolic BP for fluid resuscitation?",
            "options": ["80-90 mmHg", "90-100 mmHg", "100-110 mmHg", "At least 110-120 mmHg"],
            "correct_answer": 3,
            "explanation": "In TBI, maintain SBP ≥110-120 mmHg to ensure adequate cerebral perfusion pressure.",
            "source": "SNHD Protocols - Head Trauma",
        },
        # === FLUID BOLUSES - PEDIATRIC ===
        {
            "level": "AEMT",
            "category": "Fluid Boluses",
            "subcategory": "Pediatric",
            "question": "What is the pediatric fluid bolus amount per kg for shock?",
            "options": ["10 mL/kg", "20 mL/kg", "30 mL/kg", "40 mL/kg"],
            "correct_answer": 1,
            "explanation": "Pediatric fluid bolus is 20 mL/kg of isotonic crystalloid solution.",
            "source": "SNHD Protocols - Pediatric Shock",
        },
        {
            "level": "AEMT",
            "category": "Fluid Boluses",
            "subcategory": "Pediatric",
            "question": "Maximum single fluid bolus for a pediatric patient should not exceed:",
            "options": ["500 mL", "1000 mL", "1500 mL", "2000 mL"],
            "correct_answer": 1,
            "explanation": "Maximum single bolus is 1000 mL (1 liter), even if calculated amount is higher.",
            "source": "SNHD Protocols - Pediatric Fluid Therapy",
        },
        {
            "level": "AEMT",
            "category": "Fluid Boluses",
            "subcategory": "Pediatric",
            "question": "For a 15 kg child in shock, what is the appropriate fluid bolus?",
            "options": ["150 mL", "300 mL", "500 mL", "1000 mL"],
            "correct_answer": 1,
            "explanation": "15 kg × 20 mL/kg = 300 mL. Pediatric bolus is calculated as 20 mL/kg.",
            "source": "SNHD Protocols - Pediatric Calculations",
        },
        # === MEDICATIONS - DOSAGES & ROUTES ===
        {
            "level": "AEMT",
            "category": "Medications",
            "subcategory": "Dosages",
            "question": "What is the pediatric dose of epinephrine for anaphylaxis?",
            "options": ["0.01 mg/kg IM (max 0.3 mg)", "0.3 mg IM", "0.5 mg IM", "1 mg IM"],
            "correct_answer": 0,
            "explanation": "Pediatric epinephrine is 0.01 mg/kg IM, maximum 0.3 mg (1:1000 concentration).",
            "source": "SNHD Protocols - Pediatric Allergic Reaction",
        },
        {
            "level": "PARAMEDIC",
            "category": "Medications",
            "subcategory": "Dosages",
            "question": "What is the dose of naloxone for opioid overdose in adults?",
            "options": ["0.4 mg IV/IM", "2 mg IV/IM", "4 mg IV/IM", "10 mg IV/IM"],
            "correct_answer": 1,
            "explanation": "Initial adult dose is 2 mg IV/IM, may repeat every 2-3 minutes.",
            "source": "SNHD Protocols - Overdose/Poisoning",
        },
        {
            "level": "PARAMEDIC",
            "category": "Medications",
            "subcategory": "Routes",
            "question": "Which medication can be administered via the intranasal route?",
            "options": ["Epinephrine 1:1000", "Naloxone", "Atropine", "Adenosine"],
            "correct_answer": 1,
            "explanation": "Naloxone can be given intranasally (2 mg in each nostril, total 4 mg).",
            "source": "SNHD Protocols - Alternative Routes",
        },
        {
            "level": "PARAMEDIC",
            "category": "Medications",
            "subcategory": "Contraindications",
            "question": "Morphine is contraindicated in patients with:",
            "options": ["Chest pain", "Hypotension (SBP <90)", "Anxiety", "Nausea"],
            "correct_answer": 1,
            "explanation": "Morphine is contraindicated in hypotension (SBP <90) as it causes vasodilation and further BP drop.",
            "source": "SNHD Protocols - Pain Management",
        },
        # === WAITING ROOM CRITERIA ===
        {
            "level": "EMT",
            "category": "Transport Criteria",
            "subcategory": "Waiting Room",
            "question": "Which vital signs would allow a patient to be triaged to the waiting room?",
            "options": [
                "HR 120, RR 24, SBP 90",
                "HR 90, RR 18, SBP 130",
                "HR 140, RR 30, SBP 80",
                "GCS 13, HR 110, SBP 100",
            ],
            "correct_answer": 1,
            "explanation": "Stable vitals: HR 90, RR 18, SBP 130 are within normal limits and appropriate for waiting room.",
            "source": "SNHD Protocols - Transport Decisions",
        },
        {
            "level": "EMT",
            "category": "Transport Criteria",
            "subcategory": "Waiting Room",
            "question": "A patient with minor lacerations, controlled bleeding, and vitals HR 85, BP 128/82, RR 16, SpO2 98% on room air should be transported:",
            "options": [
                "Code 3 (emergency)",
                "Code 2 (urgent)",
                "BLS non-emergency",
                "Patient can self-transport",
            ],
            "correct_answer": 2,
            "explanation": "Stable patient with minor injuries - appropriate for BLS non-emergency transport.",
            "source": "SNHD Protocols - Priority Classification",
        },
        # === INTOXICATION / ALTERED MENTAL STATUS ===
        {
            "level": "EMT",
            "category": "Transport Criteria",
            "subcategory": "Intoxication",
            "question": "An intoxicated patient with GCS 14, stable airway, and no traumatic injuries should be transported:",
            "options": [
                "Left on scene with police",
                "Code 3 to nearest ED",
                "BLS to appropriate facility",
                "Only if they consent",
            ],
            "correct_answer": 2,
            "explanation": "Intoxicated but stable patients (GCS >13, protecting airway) can be transported BLS to appropriate facility.",
            "source": "SNHD Protocols - Intoxication",
        },
        {
            "level": "EMT",
            "category": "Transport Criteria",
            "subcategory": "AMS",
            "question": "Which finding requires immediate transport of an intoxicated patient?",
            "options": [
                "Strong odor of alcohol",
                "GCS <13",
                "Combative behavior",
                "Slurred speech",
            ],
            "correct_answer": 1,
            "explanation": "GCS <13 indicates significant impairment requiring emergency transport and close monitoring.",
            "source": "SNHD Protocols - Altered Mental Status",
        },
        {
            "level": "AEMT",
            "category": "Transport Criteria",
            "subcategory": "AMS",
            "question": "For a diabetic patient with altered mental status and blood glucose of 40 mg/dL, what is the first intervention?",
            "options": [
                "Immediate transport",
                "Oral glucose if awake",
                "IV D10 if IV established",
                "Glucagon IM",
            ],
            "correct_answer": 2,
            "explanation": "If IV is established, give IV D10. If no IV, give oral glucose if awake/swallowing, or glucagon IM.",
            "source": "SNHD Protocols - Hypoglycemia",
        },
        # === TRAUMA SCORES & TFTC ===
        {
            "level": "EMT",
            "category": "Trauma",
            "subcategory": "Scoring",
            "question": 'What does "TFTC" stand for in trauma designation?',
            "options": [
                "Too Far To Care",
                "Trauma Field Transport Criteria",
                "Transport For Trauma Care",
                "Trauma Facility Transport Category",
            ],
            "correct_answer": 1,
            "explanation": "TFTC = Trauma Field Transport Criteria - used to determine appropriate trauma center destination.",
            "source": "SNHD Protocols - Trauma Triage",
        },
        {
            "level": "EMT",
            "category": "Trauma",
            "subcategory": "Scoring",
            "question": "A patient with GCS 13, SBP 85, and RR 28 meets which trauma triage criteria?",
            "options": [
                "No trauma center needed",
                "TFTC - Transport to trauma center",
                "Go to nearest ED",
                "Wait for ALS",
            ],
            "correct_answer": 1,
            "explanation": "Abnormal vital signs (GCS <14, SBP <90, RR <10 or >29) meet TFTC for trauma center transport.",
            "source": "SNHD Protocols - Trauma Triage",
        },
        {
            "level": "EMT",
            "category": "Trauma",
            "subcategory": "Scoring",
            "question": "Which mechanism of injury automatically meets trauma center criteria?",
            "options": [
                "Fall from standing",
                "Fall >20 feet",
                "Motorcycle crash <20 mph",
                "Minor assault",
            ],
            "correct_answer": 1,
            "explanation": "Falls >20 feet (adults) or >10 feet (children <15 years) meet trauma center criteria.",
            "source": "SNHD Protocols - Mechanism of Injury",
        },
        {
            "level": "PARAMEDIC",
            "category": "Trauma",
            "subcategory": "Scoring",
            "question": "What is the Revised Trauma Score (RTS) threshold that indicates severe trauma?",
            "options": ["<5", "<7", "<11", "<15"],
            "correct_answer": 2,
            "explanation": "RTS <11 indicates severe trauma requiring trauma center care.",
            "source": "SNHD Protocols - Trauma Scoring",
        },
        # === HOSPITAL CATCHMENTS ===
        {
            "level": "EMT",
            "category": "Transport",
            "subcategory": "Hospital Selection",
            "question": "For a STEMI patient, transport should be to:",
            "options": [
                "Nearest ED",
                "PCI-capable facility",
                "Trauma center",
                "Any hospital with cardiac unit",
            ],
            "correct_answer": 1,
            "explanation": "STEMI patients should go to a PCI-capable facility (catheterization lab) for emergent intervention.",
            "source": "SNHD Protocols - Cardiac Emergencies",
        },
        {
            "level": "EMT",
            "category": "Transport",
            "subcategory": "Hospital Selection",
            "question": "A patient with a severe traumatic brain injury should be transported to:",
            "options": [
                "Nearest ED",
                "Trauma center with neurosurgery",
                "Psychiatric facility",
                "Urgent care",
            ],
            "correct_answer": 1,
            "explanation": "Severe TBI requires a trauma center with neurosurgical capabilities.",
            "source": "SNHD Protocols - TBI Transport",
        },
        {
            "level": "EMT",
            "category": "Transport",
            "subcategory": "Hospital Selection",
            "question": "For a patient in cardiac arrest, what is the transport priority?",
            "options": [
                "Scene time <10 min, transport to nearest",
                "Work on scene 20+ min",
                "Transport to cardiac center only",
                "Wait for ROSC before moving",
            ],
            "correct_answer": 0,
            "explanation": "For cardiac arrest, minimize scene time (<10 min) and transport to nearest appropriate facility.",
            "source": "SNHD Protocols - Cardiac Arrest",
        },
        # === SPECIAL EXCEPTIONS & CIRCUMSTANCES ===
        {
            "level": "EMT",
            "category": "Special Circumstances",
            "subcategory": "Pregnancy",
            "question": "For a pregnant patient >20 weeks with trauma, positioning should be:",
            "options": ["Supine", "Left lateral tilt", "Trendelenburg", "Right lateral decubitus"],
            "correct_answer": 1,
            "explanation": "Left lateral tilt or manual uterine displacement to prevent supine hypotensive syndrome.",
            "source": "SNHD Protocols - Obstetric Trauma",
        },
        {
            "level": "PARAMEDIC",
            "category": "Special Circumstances",
            "subcategory": "Burns",
            "question": "For a patient with >20% TBSA burns, fluid resuscitation in first 8 hours should be:",
            "options": [
                "Half of total calculated",
                "Full amount",
                "Quarter of total",
                "None until at hospital",
            ],
            "correct_answer": 0,
            "explanation": "Half of total calculated fluid (Parkland formula) is given in first 8 hours, half in next 16 hours.",
            "source": "SNHD Protocols - Burn Management",
        },
        {
            "level": "EMT",
            "category": "Special Circumstances",
            "subcategory": "Environmental",
            "question": "In heat stroke, core temperature is typically:",
            "options": [">98.6°F", ">100°F", ">104°F", ">106°F"],
            "correct_answer": 2,
            "explanation": "Heat stroke is defined as core temp >104°F (40°C) with altered mental status.",
            "source": "SNHD Protocols - Heat Emergencies",
        },
        {
            "level": "EMT",
            "category": "Airway",
            "subcategory": "Special Cases",
            "question": "In a patient with suspected spinal injury, the airway maneuver of choice is:",
            "options": ["Head tilt-chin lift", "Jaw thrust", "OPA insertion", "NTA insertion"],
            "correct_answer": 1,
            "explanation": "Jaw thrust maneuver opens airway without extending the neck, protecting potential spinal injury.",
            "source": "SNHD Protocols - Spinal Injury",
        },
        {
            "level": "PARAMEDIC",
            "category": "Cardiac",
            "subcategory": "Exceptions",
            "question": "In cardiac arrest with suspected opioid overdose, when should naloxone be administered?",
            "options": [
                "Before CPR",
                "After ROSC",
                "During CPR if IV access available",
                "Not indicated",
            ],
            "correct_answer": 2,
            "explanation": "Naloxone may be given during CPR if opioid overdose suspected, but do NOT delay CPR/Defibrillation.",
            "source": "SNHD Protocols - Opioid Overdose",
        },
        # === ADDITIONAL FLUID BOLUS QUESTIONS ===
        {
            "level": "AEMT",
            "category": "Fluid Boluses",
            "subcategory": "Adult",
            "question": "What type of fluid is preferred for adult bolus therapy?",
            "options": ["D5W", "Normal Saline (0.9% NaCl)", "D10", "Sterile Water"],
            "correct_answer": 1,
            "explanation": "Isotonic crystalloids like Normal Saline or Lactated Ringer's are preferred for fluid resuscitation.",
            "source": "SNHD Protocols - Fluid Therapy",
        },
        {
            "level": "AEMT",
            "category": "Fluid Boluses",
            "subcategory": "Pediatric",
            "question": "How many fluid boluses can be given to a pediatric patient before reassessment?",
            "options": ["1", "2", "3", "Unlimited"],
            "correct_answer": 1,
            "explanation": "Typically 2 boluses (40 mL/kg total) before reassessing and considering other interventions.",
            "source": "SNHD Protocols - Pediatric Shock",
        },
        {
            "level": "AEMT",
            "category": "Fluid Boluses",
            "subcategory": "Adult",
            "question": "In sepsis with hypotension, what is the initial fluid bolus?",
            "options": ["250 mL", "500 mL", "1000 mL", "2000 mL"],
            "correct_answer": 2,
            "explanation": "30 mL/kg (typically 1000-2000 mL for adults) is the standard for septic shock.",
            "source": "SNHD Protocols - Sepsis",
        },
        {
            "level": "AEMT",
            "category": "Fluid Boluses",
            "subcategory": "Adult",
            "question": "Fluid boluses are contraindicated in which condition?",
            "options": ["Hypovolemia", "Shock", "Acute pulmonary edema", "Trauma"],
            "correct_answer": 2,
            "explanation": "Fluid boluses are contraindicated in pulmonary edema/CHF as they worsen fluid overload.",
            "source": "SNHD Protocols - Contraindications",
        },
        {
            "level": "AEMT",
            "category": "Fluid Boluses",
            "subcategory": "Pediatric",
            "question": "For a dehydrated but hemodynamically stable child, fluid administration should be:",
            "options": [
                "Rapid bolus",
                "Slow maintenance",
                "Nothing by mouth",
                "Hypertonic solution",
            ],
            "correct_answer": 1,
            "explanation": "Stable dehydrated children receive slow maintenance fluids, not rapid boluses.",
            "source": "SNHD Protocols - Pediatric Dehydration",
        },
        {
            "level": "AEMT",
            "category": "Fluid Boluses",
            "subcategory": "Adult",
            "question": "In hemorrhagic shock, permissive hypotension targets what SBP range?",
            "options": ["60-70 mmHg", "80-90 mmHg", "100-110 mmHg", "120+ mmHg"],
            "correct_answer": 1,
            "explanation": "Permissive hypotension targets SBP 80-90 mmHg to limit bleeding while maintaining perfusion.",
            "source": "SNHD Protocols - Hemorrhagic Shock",
        },
        {
            "level": "EMT",
            "category": "Fluid Boluses",
            "subcategory": "Special Cases",
            "question": "For suspected tension pneumothorax, what is the priority before fluids?",
            "options": ["Large bore IV", "Needle decompression", "Fluid bolus", "CPAP"],
            "correct_answer": 1,
            "explanation": "Needle decompression is lifesaving in tension pneumothorax and takes priority.",
            "source": "SNHD Protocols - Chest Trauma",
        },
        # === MORE MEDICATION QUESTIONS ===
        {
            "level": "AEMT",
            "category": "Medications",
            "subcategory": "Dosages",
            "question": "Albuterol dosing for asthma exacerbation is:",
            "options": [
                "2.5 mg via nebulizer",
                "5 mg via nebulizer",
                "10 mg via nebulizer",
                "0.5 mg via nebulizer",
            ],
            "correct_answer": 0,
            "explanation": "Standard dose is 2.5 mg in 3 mL normal saline via nebulizer, may repeat.",
            "source": "SNHD Protocols - Respiratory",
        },
        {
            "level": "PARAMEDIC",
            "category": "Medications",
            "subcategory": "Routes",
            "question": "Glucagon for hypoglycemia can be given:",
            "options": ["IV only", "IM only", "IM or SC", "PO only"],
            "correct_answer": 2,
            "explanation": "Glucagon can be given IM or SC (1 mg adults, 0.5 mg children <25 kg).",
            "source": "SNHD Protocols - Hypoglycemia",
        },
        {
            "level": "PARAMEDIC",
            "category": "Medications",
            "subcategory": "Contraindications",
            "question": "Nitroglycerin is contraindicated if SBP is below:",
            "options": ["100 mmHg", "90 mmHg", "110 mmHg", "120 mmHg"],
            "correct_answer": 1,
            "explanation": "Nitroglycerin is contraindicated if SBP <90 or >30 mmHg drop from baseline.",
            "source": "SNHD Protocols - ACS",
        },
        {
            "level": "PARAMEDIC",
            "category": "Medications",
            "subcategory": "Dosages",
            "question": "Adenosine dose for SVT in adults is:",
            "options": [
                "3 mg rapid IV push",
                "6 mg rapid IV push",
                "12 mg rapid IV push",
                "0.5 mg/kg IV",
            ],
            "correct_answer": 1,
            "explanation": "Start with 6 mg rapid IV push, then 12 mg if needed, then 12 mg again.",
            "source": "SNHD Protocols - Dysrhythmias",
        },
        {
            "level": "PARAMEDIC",
            "category": "Medications",
            "subcategory": "Pediatric",
            "question": "Pediatric adenosine dose is:",
            "options": ["0.1 mg/kg (max 6 mg)", "0.5 mg/kg", "1 mg/kg", "6 mg fixed"],
            "correct_answer": 0,
            "explanation": "Pediatric adenosine: 0.1 mg/kg rapid IV (max 6 mg), then 0.2 mg/kg (max 12 mg).",
            "source": "SNHD Protocols - Pediatric Dysrhythmias",
        },
        {
            "level": "PARAMEDIC",
            "category": "Medications",
            "subcategory": "Dosages",
            "question": "Amiodarone dose for cardiac arrest is:",
            "options": ["150 mg IV push", "300 mg IV push", "1 mg/kg", "450 mg IV push"],
            "correct_answer": 1,
            "explanation": "Cardiac arrest: 300 mg IV/IO push, may give additional 150 mg.",
            "source": "SNHD Protocols - Cardiac Arrest",
        },
        {
            "level": "AEMT",
            "category": "Medications",
            "subcategory": "Routes",
            "question": "Oral glucose can be given if the patient is:",
            "options": ["Unconscious", "Alert with intact gag reflex", "Seizing", "Vomiting"],
            "correct_answer": 1,
            "explanation": "Oral glucose is for alert patients with intact gag reflex who can swallow.",
            "source": "SNHD Protocols - Hypoglycemia",
        },
        {
            "level": "PARAMEDIC",
            "category": "Medications",
            "subcategory": "Dosages",
            "question": "Fentanyl dosing for pain management in adults:",
            "options": ["25-50 mcg IV/IM/IN", "100-200 mcg IV", "5-10 mcg IV", "1 mg IV"],
            "correct_answer": 0,
            "explanation": "Fentanyl 25-50 mcg IV/IM/IN, may repeat in 10 minutes.",
            "source": "SNHD Protocols - Pain Management",
        },
        {
            "level": "PARAMEDIC",
            "category": "Medications",
            "subcategory": "Contraindications",
            "question": "Fentanyl is contraindicated with:",
            "options": [
                "Tachycardia",
                "Hypotension or respiratory depression",
                "Hypertension",
                "Anxiety",
            ],
            "correct_answer": 1,
            "explanation": "Fentanyl contraindicated with hypotension (SBP <90), respiratory depression, or altered LOC.",
            "source": "SNHD Protocols - Pain Management",
        },
        # === MORE TRANSPORT/WAITING ROOM ===
        {
            "level": "EMT",
            "category": "Transport Criteria",
            "subcategory": "Waiting Room",
            "question": "Which patient is appropriate for waiting room triage?",
            "options": [
                "Chest pain with diaphoresis",
                "Sore throat, afebrile, vitals stable",
                "Respiratory distress",
                "Altered mental status",
            ],
            "correct_answer": 1,
            "explanation": "Stable minor complaints (sore throat, minor injuries) are appropriate for waiting room.",
            "source": "SNHD Protocols - Triage",
        },
        {
            "level": "EMT",
            "category": "Transport Criteria",
            "subcategory": "Intoxication",
            "question": "A patient with EtOH odor, HR 100, BP 140/90, GCS 15, no trauma should be transported:",
            "options": [
                "Code 3",
                "BLS to appropriate facility",
                "Left with police",
                "Refused transport",
            ],
            "correct_answer": 1,
            "explanation": "Stable intoxicated patients can be transported BLS to appropriate facility.",
            "source": "SNHD Protocols - Intoxication",
        },
        {
            "level": "EMT",
            "category": "Transport Criteria",
            "subcategory": "AMS",
            "question": "A patient found down, unresponsive, no trauma should be:",
            "options": ["Left on scene", "Transported Code 3", "Transported BLS", "Taken home"],
            "correct_answer": 1,
            "explanation": "Unresponsive patients require emergency transport and evaluation.",
            "source": "SNHD Protocols - Unresponsive",
        },
        {
            "level": "EMT",
            "category": "Transport Criteria",
            "subcategory": "Special Cases",
            "question": "A patient threatening suicide requires:",
            "options": [
                "Police only",
                "BLS transport",
                "Emergency transport with mental health evaluation",
                "Left with family",
            ],
            "correct_answer": 2,
            "explanation": "Suicidal patients require emergency transport for mental health evaluation.",
            "source": "SNHD Protocols - Behavioral",
        },
        # === MORE TRAUMA QUESTIONS ===
        {
            "level": "EMT",
            "category": "Trauma",
            "subcategory": "Scoring",
            "question": "The Glasgow Coma Scale assesses:",
            "options": [
                "Only motor response",
                "Eye, verbal, and motor response",
                "Level of pain",
                "Blood pressure",
            ],
            "correct_answer": 1,
            "explanation": "GCS assesses eye opening, verbal response, and motor response (3-15 scale).",
            "source": "SNHD Protocols - GCS",
        },
        {
            "level": "EMT",
            "category": "Trauma",
            "subcategory": "TFTC",
            "question": "TFTC includes which vital sign abnormalities?",
            "options": ["HR >100", "SBP <90, RR <10 or >29, GCS <14", "Temp >99°F", "SpO2 <95%"],
            "correct_answer": 1,
            "explanation": "TFTC includes SBP <90, RR <10 or >29, or GCS <14.",
            "source": "SNHD Protocols - Trauma Triage",
        },
        {
            "level": "EMT",
            "category": "Trauma",
            "subcategory": "Mechanism",
            "question": "Auto vs pedestrian meets trauma center criteria if impact was at:",
            "options": ["Any speed", ">5 mph", ">20 mph", ">40 mph"],
            "correct_answer": 0,
            "explanation": "All auto vs pedestrian incidents meet trauma center criteria regardless of speed.",
            "source": "SNHD Protocols - Mechanism",
        },
        {
            "level": "EMT",
            "category": "Trauma",
            "subcategory": "Scoring",
            "question": "A trauma patient with GCS 10, SBP 88, HR 120 meets:",
            "options": [
                "No trauma criteria",
                "TFTC - trauma center required",
                "BLS transport OK",
                "Wait for ALS",
            ],
            "correct_answer": 1,
            "explanation": "GCS 10 (<14) and SBP 88 (<90) both meet TFTC criteria.",
            "source": "SNHD Protocols - Trauma Scoring",
        },
        {
            "level": "EMT",
            "category": "Trauma",
            "subcategory": "Special Cases",
            "question": "Ejection from vehicle meets trauma center criteria:",
            "options": [
                "Only if >20 mph",
                "Only if rollover",
                "Yes - automatic criteria",
                "Only if unrestrained",
            ],
            "correct_answer": 2,
            "explanation": "Ejection from vehicle is automatic trauma center criteria regardless of other factors.",
            "source": "SNHD Protocols - Mechanism",
        },
        {
            "level": "EMT",
            "category": "Trauma",
            "subcategory": "Pediatric",
            "question": "Pediatric trauma activation age threshold is typically under:",
            "options": ["5 years", "10 years", "15 years", "18 years"],
            "correct_answer": 2,
            "explanation": "Many systems use <15 years for pediatric trauma criteria (falls >10 feet).",
            "source": "SNHD Protocols - Pediatric Trauma",
        },
        # === CARDIAC QUESTIONS ===
        {
            "level": "EMT",
            "category": "Cardiac",
            "subcategory": "Arrest",
            "question": "Adult CPR compression rate is:",
            "options": [
                "60-80 per minute",
                "100-120 per minute",
                "140-160 per minute",
                "As fast as possible",
            ],
            "correct_answer": 1,
            "explanation": "AHA recommends 100-120 compressions per minute for adults.",
            "source": "SNHD Protocols - CPR",
        },
        {
            "level": "EMT",
            "category": "Cardiac",
            "subcategory": "Arrest",
            "question": "CPR compression depth for adults is:",
            "options": ["At least 1 inch", "At least 2 inches (5 cm)", "3-4 inches", "1.5 inches"],
            "correct_answer": 1,
            "explanation": "Compress at least 2 inches (5 cm) but not more than 2.4 inches.",
            "source": "SNHD Protocols - CPR",
        },
        {
            "level": "PARAMEDIC",
            "category": "Cardiac",
            "subcategory": "Dysrhythmias",
            "question": "Unstable tachycardia with a pulse is treated with:",
            "options": ["CPR", "Synchronized cardioversion", "Defibrillation", "Observation"],
            "correct_answer": 1,
            "explanation": "Unstable tachycardia (hypotension, altered LOC, chest pain) requires synchronized cardioversion.",
            "source": "SNHD Protocols - Tachycardia",
        },
        {
            "level": "PARAMEDIC",
            "category": "Cardiac",
            "subcategory": "ACS",
            "question": "STEMI is defined by ST elevation of:",
            "options": [
                ">0.5 mm",
                ">1 mm in limb leads, >2 mm in precordial leads",
                ">3 mm anywhere",
                "Any ST elevation",
            ],
            "correct_answer": 1,
            "explanation": "STEMI: >1 mm ST elevation in limb leads or >2 mm in precordial leads (V1-V6).",
            "source": "SNHD Protocols - STEMI",
        },
        {
            "level": "EMT",
            "category": "Cardiac",
            "subcategory": "ACS",
            "question": "Aspirin for chest pain should be given:",
            "options": [
                "Only if 12-lead shows MI",
                "To all patients with suspected ACS",
                "Only if hypertensive",
                "Never by EMTs",
            ],
            "correct_answer": 1,
            "explanation": "Aspirin 324 mg chewable is given to all suspected ACS patients without allergy.",
            "source": "SNHD Protocols - Chest Pain",
        },
        {
            "level": "PARAMEDIC",
            "category": "Cardiac",
            "subcategory": "ACS",
            "question": "Nitroglycerin should NOT be given if:",
            "options": [
                "HR >100",
                "SBP <90 or used PDE5 inhibitor",
                "Patient is anxious",
                "Pain is severe",
            ],
            "correct_answer": 1,
            "explanation": "Nitroglycerin contraindicated if SBP <90, HR <50 or >100, or PDE5 inhibitor use.",
            "source": "SNHD Protocols - ACS",
        },
        # === RESPIRATORY QUESTIONS ===
        {
            "level": "EMT",
            "category": "Respiratory",
            "subcategory": "Assessment",
            "question": "Signs of respiratory distress include:",
            "options": [
                "Normal breathing",
                "Accessory muscle use, tripod positioning",
                "Bradypnea",
                "Sleepiness",
            ],
            "correct_answer": 1,
            "explanation": "Accessory muscle use, tripod position, retractions indicate respiratory distress.",
            "source": "SNHD Protocols - Respiratory",
        },
        {
            "level": "EMT",
            "category": "Respiratory",
            "subcategory": "Asthma",
            "question": "Status asthmaticus is defined as:",
            "options": [
                "Mild wheezing",
                "Asthma not responding to initial treatment",
                "No wheezing",
                "Normal SpO2",
            ],
            "correct_answer": 1,
            "explanation": "Status asthmaticus is severe asthma not responding to initial bronchodilator therapy.",
            "source": "SNHD Protocols - Asthma",
        },
        {
            "level": "EMT",
            "category": "Respiratory",
            "subcategory": "COPD",
            "question": "COPD patients often have baseline:",
            "options": ["High SpO2", "Low SpO2 (88-92% acceptable)", "Normal CO2", "Alkalosis"],
            "correct_answer": 1,
            "explanation": "COPD patients may have baseline SpO2 88-92% due to chronic CO2 retention.",
            "source": "SNHD Protocols - COPD",
        },
        {
            "level": "PARAMEDIC",
            "category": "Respiratory",
            "subcategory": "Failure",
            "question": "Signs of impending respiratory failure include:",
            "options": [
                "Improved SpO2 with O2",
                "Altered mental status, fatigue, bradypnea",
                "Increased wheezing",
                "Tachycardia only",
            ],
            "correct_answer": 1,
            "explanation": "Altered mental status, fatigue, bradypnea indicate respiratory failure requiring airway support.",
            "source": "SNHD Protocols - Respiratory Failure",
        },
        # === PEDIATRIC QUESTIONS ===
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Assessment",
            "question": "Pediatric vital signs differ from adults. Normal pediatric HR is:",
            "options": [
                "60-100 for all ages",
                "Faster than adults, varies by age",
                "Slower than adults",
                "Always >150",
            ],
            "correct_answer": 1,
            "explanation": "Pediatric heart rates are faster and vary by age (infants 100-160, toddlers 90-150, etc.).",
            "source": "SNHD Protocols - Pediatric Vitals",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Airway",
            "question": "Pediatric airway positioning for infants requires:",
            "options": [
                "Head hyperextension",
                "Neutral position (towel under shoulders)",
                "Chin to chest",
                "Lateral position",
            ],
            "correct_answer": 1,
            "explanation": "Infants need neutral position with towel under shoulders due to large occiput.",
            "source": "SNHD Protocols - Pediatric Airway",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fever",
            "question": "Febrile seizure is most common in ages:",
            "options": ["0-3 months", "6 months - 5 years", "5-10 years", "All ages equally"],
            "correct_answer": 1,
            "explanation": "Febrile seizures most common in children 6 months to 5 years old.",
            "source": "SNHD Protocols - Pediatric Seizures",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Pediatric epinephrine for anaphylaxis is dosed at:",
            "options": [
                "0.01 mg/kg IM (max 0.3 mg)",
                "0.3 mg IM fixed dose",
                "0.5 mg IM",
                "1 mg IM",
            ],
            "correct_answer": 0,
            "explanation": "Pediatric epinephrine: 0.01 mg/kg IM (max 0.3 mg) using 1:1000 concentration.",
            "source": "SNHD Protocols - Pediatric Anaphylaxis",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Trauma",
            "question": "Pediatric trauma patients are at higher risk for:",
            "options": [
                "Hypertension",
                "Hypovolemic shock (large body surface area)",
                "Bradycardia",
                "Hyperthermia",
            ],
            "correct_answer": 1,
            "explanation": "Children have larger body surface area to volume ratio and decompensate quickly.",
            "source": "SNHD Protocols - Pediatric Trauma",
        },
        # === OBSTETRIC QUESTIONS ===
        {
            "level": "EMT",
            "category": "Obstetric",
            "subcategory": "Delivery",
            "question": "Signs of imminent delivery include:",
            "options": [
                "Contractions 10 minutes apart",
                "Crowning, urge to push, contractions <2 min apart",
                "No contractions",
                "Mild cramping",
            ],
            "correct_answer": 1,
            "explanation": "Crowning, urge to push, and frequent contractions indicate imminent delivery.",
            "source": "SNHD Protocols - Childbirth",
        },
        {
            "level": "EMT",
            "category": "Obstetric",
            "subcategory": "Complications",
            "question": "Shoulder dystocia is managed by:",
            "options": [
                "Immediate transport",
                "McRoberts maneuver (knees to chest)",
                "Fundal pressure",
                "Pulling harder on baby",
            ],
            "correct_answer": 1,
            "explanation": "McRoberts maneuver (hyperflex maternal thighs) is first-line for shoulder dystocia.",
            "source": "SNHD Protocols - Shoulder Dystocia",
        },
        {
            "level": "EMT",
            "category": "Obstetric",
            "subcategory": "Postpartum",
            "question": "Postpartum hemorrhage is defined as blood loss >:",
            "options": ["100 mL", "500 mL (vaginal) or 1000 mL (C-section)", "250 mL", "2000 mL"],
            "correct_answer": 1,
            "explanation": "PPH: >500 mL after vaginal delivery or >1000 mL after C-section.",
            "source": "SNHD Protocols - Postpartum Hemorrhage",
        },
        {
            "level": "EMT",
            "category": "Obstetric",
            "subcategory": "Emergencies",
            "question": "Eclampsia is characterized by:",
            "options": [
                "High blood pressure only",
                "Seizures in pregnancy/postpartum",
                "Low blood pressure",
                "Normal delivery",
            ],
            "correct_answer": 1,
            "explanation": "Eclampsia is new-onset seizures in pregnancy or postpartum, usually with hypertension.",
            "source": "SNHD Protocols - Eclampsia",
        },
        # === ENVIRONMENTAL QUESTIONS ===
        {
            "level": "EMT",
            "category": "Environmental",
            "subcategory": "Hyperthermia",
            "question": "Heat exhaustion vs heat stroke - key difference is:",
            "options": [
                "Temperature only",
                "Altered mental status in heat stroke",
                "Sweating",
                "Heart rate",
            ],
            "correct_answer": 1,
            "explanation": "Heat stroke has altered mental status + temp >104°F; heat exhaustion has normal mentation.",
            "source": "SNHD Protocols - Heat Emergencies",
        },
        {
            "level": "EMT",
            "category": "Environmental",
            "subcategory": "Hypothermia",
            "question": "Severe hypothermia is core temp below:",
            "options": ["95°F (35°C)", "90°F (32°C)", "86°F (30°C)", "98.6°F"],
            "correct_answer": 1,
            "explanation": "Severe hypothermia is core temp <90°F (32°C) - may present as pulseless.",
            "source": "SNHD Protocols - Hypothermia",
        },
        {
            "level": "EMT",
            "category": "Environmental",
            "subcategory": "Drowning",
            "question": "Priority in drowning is:",
            "options": [
                "Immediate CPR regardless",
                "Airway and breathing assessment",
                "Spinal immobilization",
                "Transport only",
            ],
            "correct_answer": 1,
            "explanation": "Assess ABCs first - not all drowning victims need immediate CPR if breathing.",
            "source": "SNHD Protocols - Drowning",
        },
        {
            "level": "EMT",
            "category": "Environmental",
            "subcategory": "Altitude",
            "question": "High altitude illness symptoms include:",
            "options": ["Only headache", "HAPE and HACE", "Increased appetite", "Hypothermia only"],
            "correct_answer": 1,
            "explanation": "High altitude illness includes HAPE (pulmonary edema) and HACE (cerebral edema).",
            "source": "SNHD Protocols - Altitude",
        },
        # === BEHAVIORAL/PSYCH QUESTIONS ===
        {
            "level": "EMT",
            "category": "Behavioral",
            "subcategory": "Assessment",
            "question": "First priority in behavioral emergency is:",
            "options": [
                "Immediate sedation",
                "Scene safety",
                "Psychiatric diagnosis",
                "Physical restraint",
            ],
            "correct_answer": 1,
            "explanation": "Scene safety for crew and patient is always the first priority.",
            "source": "SNHD Protocols - Behavioral",
        },
        {
            "level": "EMT",
            "category": "Behavioral",
            "subcategory": "Restraint",
            "question": "Restraint should be:",
            "options": [
                "Prone position",
                "Minimum necessary, supine or lateral",
                "Tied tightly",
                "Ignored",
            ],
            "correct_answer": 1,
            "explanation": "Use minimum necessary restraint, avoid prone position, monitor closely.",
            "source": "SNHD Protocols - Restraint",
        },
        {
            "level": "EMT",
            "category": "Behavioral",
            "subcategory": "Suicide",
            "question": "Patient with suicide attempt requires:",
            "options": [
                "Police only",
                "Emergency transport to ED for evaluation",
                "Family to watch",
                "Promise not to do it again",
            ],
            "correct_answer": 1,
            "explanation": "All suicide attempts/ideation require emergency transport for professional evaluation.",
            "source": "SNHD Protocols - Suicide",
        },
        # === COMPREHENSIVE PEDIATRIC BOLUSES ===
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "For a 20 kg child in hypovolemic shock, what is the correct fluid bolus?",
            "options": ["200 mL", "400 mL", "600 mL", "1000 mL"],
            "correct_answer": 1,
            "explanation": "20 kg × 20 mL/kg = 400 mL. Pediatric bolus is always 20 mL/kg.",
            "source": "SNHD Protocols - Pediatric Fluids",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "Maximum number of fluid boluses recommended before reassessment in pediatrics:",
            "options": [
                "1 bolus",
                "2 boluses (40 mL/kg total)",
                "3 boluses",
                "Unlimited until BP normalizes",
            ],
            "correct_answer": 1,
            "explanation": "Maximum 2 boluses (40 mL/kg total) before reassessment. Consider other interventions if still unstable.",
            "source": "SNHD Protocols - Pediatric Shock",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "A 35 kg pediatric patient should receive a maximum single bolus of:",
            "options": ["700 mL (35 kg × 20)", "1000 mL", "500 mL", "1500 mL"],
            "correct_answer": 1,
            "explanation": "Calculated amount is 700 mL, but maximum single bolus is capped at 1000 mL.",
            "source": "SNHD Protocols - Pediatric Fluid Limits",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "Fluid bolus is contraindicated in pediatric patients with:",
            "options": [
                "Fever",
                "Respiratory distress with rales/crackles",
                "Normal vitals",
                "Minor trauma",
            ],
            "correct_answer": 1,
            "explanation": "Fluid bolus contraindicated in suspected CHF, pulmonary edema, or respiratory distress with fluid overload signs.",
            "source": "SNHD Protocols - Pediatric Contraindications",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "For pediatric DKA (Diabetic Ketoacidosis), fluid resuscitation should be:",
            "options": [
                "Rapid bolus to correct shock quickly",
                "Cautious - risk of cerebral edema",
                "Not given until glucose normalized",
                "Hypertonic saline",
            ],
            "correct_answer": 1,
            "explanation": "DKA requires cautious fluid resuscitation due to risk of cerebral edema. Follow specific DKA protocols.",
            "source": "SNHD Protocols - Pediatric DKA",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "A neonate (under 28 days) in shock receives fluid bolus of:",
            "options": ["20 mL/kg", "10 mL/kg", "30 mL/kg", "40 mL/kg"],
            "correct_answer": 1,
            "explanation": "Neonates receive 10 mL/kg boluses due to risk of fluid overload and heart strain.",
            "source": "SNHD Protocols - Neonatal Resuscitation",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "Signs of fluid overload in pediatric patients include:",
            "options": [
                "Tachycardia only",
                "Hepatomegaly, JVD, rales, decreased responsiveness",
                "Fever",
                "Increased urine output",
            ],
            "correct_answer": 1,
            "explanation": "Hepatomegaly (enlarged liver), JVD, pulmonary rales, and altered mental status indicate fluid overload.",
            "source": "SNHD Protocols - Pediatric Complications",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "For a 6-year-old (22 kg) with suspected sepsis and normal perfusion, initial fluid is:",
            "options": [
                "No fluids",
                "20 mL/kg bolus over 20 minutes",
                "Maintenance only",
                "D5W bolus",
            ],
            "correct_answer": 1,
            "explanation": "Pediatric sepsis: 20 mL/kg isotonic crystalloid bolus, reassess perfusion after each bolus.",
            "source": "SNHD Protocols - Pediatric Sepsis",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "In pediatric trauma with suspected hemorrhage but no signs of shock:",
            "options": [
                "No fluids",
                "Aggressive fluid resuscitation",
                "Limited fluids, permissive hypotension",
                "Blood transfusion",
            ],
            "correct_answer": 2,
            "explanation": "In pediatric trauma without shock, use limited fluids with permissive hypotension to avoid dilutional coagulopathy.",
            "source": "SNHD Protocols - Pediatric Trauma",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "Burn fluid resuscitation for a 15 kg child with 20% TBSA burns (Parkland formula):",
            "options": [
                "150 mL/hr",
                "300 mL/hr for first 8 hours",
                "600 mL total",
                "No fluids in field",
            ],
            "correct_answer": 1,
            "explanation": "Parkland: 4 mL × kg × %TBSA = 1200 mL. Half in first 8 hours = 600 mL total, 75 mL/hr. First 8 hours from time of burn.",
            "source": "SNHD Protocols - Pediatric Burns",
        },
        # === COMPREHENSIVE PEDIATRIC MEDICATIONS ===
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Pediatric albuterol dosing via nebulizer is:",
            "options": [
                "0.15 mg/kg (min 2.5 mg, max 5 mg)",
                "2.5 mg fixed dose",
                "5 mg fixed dose",
                "0.5 mg/kg",
            ],
            "correct_answer": 0,
            "explanation": "Pediatric albuterol: 0.15 mg/kg, minimum 2.5 mg, maximum 5 mg per treatment.",
            "source": "SNHD Protocols - Pediatric Asthma",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 3-year-old (14 kg) with anaphylaxis receives epinephrine at:",
            "options": ["0.14 mg IM (0.01 mg/kg)", "0.3 mg IM", "0.5 mg IM", "1 mg IM"],
            "correct_answer": 0,
            "explanation": "Pediatric epinephrine: 0.01 mg/kg IM using 1:1000 concentration. 14 kg × 0.01 = 0.14 mg.",
            "source": "SNHD Protocols - Pediatric Anaphylaxis",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Maximum pediatric dose of epinephrine for anaphylaxis is:",
            "options": ["0.15 mg", "0.3 mg", "0.5 mg", "1 mg"],
            "correct_answer": 1,
            "explanation": "Maximum pediatric epinephrine dose is 0.3 mg IM (1:1000), even if calculated dose is higher.",
            "source": "SNHD Protocols - Pediatric Med Limits",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Pediatric midazolam (Versed) for seizures is dosed at:",
            "options": [
                "0.1 mg/kg IM/IN (max 5 mg)",
                "0.5 mg/kg IM",
                "5 mg fixed dose",
                "0.05 mg/kg IV only",
            ],
            "correct_answer": 0,
            "explanation": "Pediatric midazolam: 0.1 mg/kg IM/IN, maximum 5 mg. Can repeat once in 5-10 minutes.",
            "source": "SNHD Protocols - Pediatric Seizures",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Pediatric naloxone for opioid overdose can be given:",
            "options": ["Only IV", "IV/IM/IN", "Only IN", "Contraindicated"],
            "correct_answer": 1,
            "explanation": "Pediatric naloxone: 2 mg IN (1 mg each nostril) or 0.1 mg/kg IV/IM (max 2 mg).",
            "source": "SNHD Protocols - Pediatric Overdose",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Pediatric oral glucose gel can be given if:",
            "options": [
                "Patient is unconscious",
                "Patient is alert with gag reflex",
                "Patient is seizing",
                "Patient is vomiting",
            ],
            "correct_answer": 1,
            "explanation": "Oral glucose only for alert pediatric patients with intact gag reflex who can swallow.",
            "source": "SNHD Protocols - Pediatric Hypoglycemia",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Pediatric fentanyl for pain management is contraindicated with:",
            "options": [
                "Fever",
                "Respiratory depression or altered mental status",
                "Crying",
                "Normal vitals",
            ],
            "correct_answer": 1,
            "explanation": "Fentanyl contraindicated in pediatrics with respiratory depression, altered LOC, or hemodynamic instability.",
            "source": "SNHD Protocols - Pediatric Pain",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Pediatric diphenhydramine (Benadryl) dose for allergic reaction:",
            "options": [
                "0.5 mg/kg IV/IM (max 25 mg)",
                "25 mg fixed dose",
                "50 mg fixed dose",
                "1 mg/kg (max 100 mg)",
            ],
            "correct_answer": 0,
            "explanation": "Pediatric diphenhydramine: 1 mg/kg PO or 0.5 mg/kg IV/IM, maximum 25 mg.",
            "source": "SNHD Protocols - Pediatric Allergies",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 5-year-old (18 kg) with severe pain can receive fentanyl at:",
            "options": [
                "0.5 mcg/kg IN (max 50 mcg)",
                "1 mcg/kg IN (max 100 mcg)",
                "25 mcg fixed dose",
                "50 mcg fixed dose",
            ],
            "correct_answer": 1,
            "explanation": "Pediatric fentanyl: 1 mcg/kg IN, maximum 100 mcg (50 mcg per nostril).",
            "source": "SNHD Protocols - Pediatric Pain Management",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Pediatric adenosine for SVT requires:",
            "options": [
                "Defibrillation first",
                "Rapid IV push followed by saline flush",
                "Slow IV drip",
                "IM injection",
            ],
            "correct_answer": 1,
            "explanation": "Adenosine must be given as rapid IV push followed immediately by 5-10 mL saline flush.",
            "source": "SNHD Protocols - Pediatric Dysrhythmias",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Pediatric amiodarone dosing for ventricular fibrillation:",
            "options": [
                "1 mg/kg IV/IO (max 100 mg)",
                "5 mg/kg IV/IO (max 300 mg)",
                "150 mg fixed dose",
                "300 mg fixed dose",
            ],
            "correct_answer": 1,
            "explanation": "Pediatric amiodarone: 5 mg/kg IV/IO, maximum 300 mg for cardiac arrest.",
            "source": "SNHD Protocols - Pediatric Cardiac Arrest",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Pediatric ondansetron (Zofran) for vomiting is contraindicated in:",
            "options": [
                "Fever",
                "Known prolonged QT syndrome",
                "Dehydration",
                "All pediatric patients",
            ],
            "correct_answer": 1,
            "explanation": "Ondansetron is contraindicated in prolonged QT syndrome due to risk of torsades.",
            "source": "SNHD Protocols - Pediatric Contraindications",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Pediatric dextrose (D10) for hypoglycemia is given at:",
            "options": [
                "0.5 g/kg (5 mL/kg) slow IV",
                "1 g/kg (10 mL/kg) rapid IV",
                "2 g/kg IV push",
                "D25 preferred",
            ],
            "correct_answer": 0,
            "explanation": "Pediatric D10: 5 mL/kg (0.5 g/kg) slow IV. D10 is preferred over D25/D50 in pediatrics.",
            "source": "SNHD Protocols - Pediatric Hypoglycemia",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Pediatric acetaminophen (Tylenol) rectal dose for fever:",
            "options": ["5 mg/kg", "10 mg/kg", "15 mg/kg", "20 mg/kg"],
            "correct_answer": 2,
            "explanation": "Pediatric acetaminophen: 15 mg/kg PO or PR, maximum 75 mg/kg/day (not to exceed adult max).",
            "source": "SNHD Protocols - Pediatric Fever",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Pediatric succinylcholine for RSI is dosed at:",
            "options": ["0.5 mg/kg", "1 mg/kg", "2 mg/kg", "3 mg/kg"],
            "correct_answer": 2,
            "explanation": "Pediatric succinylcholine: 2 mg/kg IV (higher dose than adults due to larger volume of distribution).",
            "source": "SNHD Protocols - Pediatric RSI",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Pediatric rocuronium for RSI is dosed at:",
            "options": ["0.3 mg/kg", "0.6 mg/kg", "1.2 mg/kg", "1.6 mg/kg"],
            "correct_answer": 2,
            "explanation": "Pediatric rocuronium for RSI: 1.2 mg/kg IV (higher dose than adults).",
            "source": "SNHD Protocols - Pediatric Airway",
        },
        # === PEDIATRIC SPECIAL CIRCUMSTANCES ===
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Special Cases",
            "question": "In pediatric bradycardia with poor perfusion, first intervention is:",
            "options": [
                "Atropine",
                "Epinephrine",
                "Oxygenation and ventilation support",
                "Defibrillation",
            ],
            "correct_answer": 2,
            "explanation": "Pediatric bradycardia is usually due to hypoxia - oxygenate and ventilate first.",
            "source": "SNHD Protocols - Pediatric Bradycardia",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Special Cases",
            "question": "Pediatric dose calculation using Broselow tape is based on:",
            "options": ["Age", "Weight only", "Length/height", "Head circumference"],
            "correct_answer": 2,
            "explanation": "Broselow tape uses patient length to estimate weight and provide medication dosing.",
            "source": "SNHD Protocols - Pediatric Equipment",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Special Cases",
            "question": "During pediatric respiratory arrest with a pulse, ventilate at:",
            "options": [
                "30 breaths/minute",
                "20-30 breaths/minute",
                "12-20 breaths/minute",
                "As fast as possible",
            ],
            "correct_answer": 1,
            "explanation": "Pediatric with pulse: ventilate 20-30 breaths/minute (every 2-3 seconds).",
            "source": "SNHD Protocols - Pediatric Ventilation",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Special Cases",
            "question": "Pediatric septic shock may present with:",
            "options": [
                "Hypertension",
                "Normal or low BP with signs of poor perfusion (compensated shock)",
                "Bradycardia",
                "Increased urine output",
            ],
            "correct_answer": 1,
            "explanation": "Pediatric patients compensate well - may have normal BP but poor perfusion (tachycardia, delayed cap refill, altered mentation).",
            "source": "SNHD Protocols - Pediatric Shock Recognition",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Special Cases",
            "question": "For infants, proper BVM technique requires:",
            "options": [
                "One hand for seal, one for squeeze",
                "Two hands for seal, one for squeeze",
                "One person only",
                "High pressure ventilation",
            ],
            "correct_answer": 1,
            "explanation": "Infant BVM: Two hands for mask seal (E-C technique), one person squeezes bag. Prevents air leaks.",
            "source": "SNHD Protocols - Pediatric BVM",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Special Cases",
            "question": "Pediatric IO (intraosseous) access is preferred in children under:",
            "options": ["2 years", "6 years", "12 years", "Any age if no IV access"],
            "correct_answer": 1,
            "explanation": "IO is preferred in children under 6 years when IV access difficult or delayed. Can be used in any age.",
            "source": "SNHD Protocols - Pediatric Access",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Special Cases",
            "question": "During pediatric fever with altered mental status, suspect:",
            "options": [
                "Simple viral illness",
                "Febrile seizure, meningitis, or sepsis",
                "Heat exhaustion",
                "Hypoglycemia only",
            ],
            "correct_answer": 1,
            "explanation": "Fever + altered mental status in pediatrics is serious - consider febrile seizure, meningitis, or sepsis.",
            "source": "SNHD Protocols - Pediatric Fever Workup",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Special Cases",
            "question": "Pediatric post-intubation sedation and analgesia should include:",
            "options": [
                "No medications needed",
                "Analgesia (pain control) AND sedation",
                "Sedation only",
                "Paralytic only",
            ],
            "correct_answer": 1,
            "explanation": "Intubated pediatric patients require both analgesia (fentanyl) AND sedation (midazolam/ketamine).",
            "source": "SNHD Protocols - Pediatric Post-Intubation",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Special Cases",
            "question": "For suspected non-accidental trauma in pediatrics, you should:",
            "options": [
                "Confront the parents immediately",
                "Document findings objectively and report suspicions",
                "Ignore it as not your concern",
                "Transport without documentation",
            ],
            "correct_answer": 1,
            "explanation": "Document objective findings, mechanism inconsistencies, and report suspicions to receiving facility.",
            "source": "SNHD Protocols - Pediatric Abuse",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Special Cases",
            "question": "Pediatric traumatic arrest with asystole has:",
            "options": [
                "Good prognosis with aggressive resuscitation",
                "Poor prognosis - consider terminating if no reversible cause",
                "Always due to hypothermia",
                "Better outcomes than adults",
            ],
            "correct_answer": 1,
            "explanation": "Pediatric traumatic arrest in asystole has very poor prognosis. Consider termination if no reversible cause found.",
            "source": "SNHD Protocols - Pediatric Traumatic Arrest",
        },
        # === ULTRA-DETAILED PEDIATRIC BOLUS CALCULATIONS ===
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "A 4-year-old weighing 16 kg needs a fluid bolus. Calculate: 16 kg × 20 mL/kg = ?",
            "options": ["240 mL", "320 mL", "400 mL", "480 mL"],
            "correct_answer": 1,
            "explanation": "16 kg × 20 mL/kg = 320 mL. This is under the 1000 mL cap, so give full 320 mL.",
            "source": "SNHD Protocols - Pediatric Fluid Calculation",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "An 8-year-old weighing 25 kg needs a fluid bolus. Calculate amount and apply cap: 25 kg × 20 mL/kg = ?",
            "options": ["400 mL", "500 mL", "750 mL", "1000 mL (capped)"],
            "correct_answer": 1,
            "explanation": "25 kg × 20 mL/kg = 500 mL. Under 1000 mL cap, so give 500 mL.",
            "source": "SNHD Protocols - Pediatric Fluid Calculation",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "A 12-year-old weighing 55 kg needs a fluid bolus. Calculate: 55 kg × 20 mL/kg = ? Apply cap.",
            "options": ["800 mL", "1000 mL (capped)", "1100 mL", "1200 mL"],
            "correct_answer": 1,
            "explanation": "55 kg × 20 mL/kg = 1100 mL, BUT maximum single bolus is 1000 mL. Give 1000 mL.",
            "source": "SNHD Protocols - Pediatric Fluid Cap",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "A 2-year-old weighing 12 kg is in hypovolemic shock. First bolus is 12 kg × 20 mL/kg = ?",
            "options": ["200 mL", "240 mL", "300 mL", "400 mL"],
            "correct_answer": 1,
            "explanation": "12 kg × 20 mL/kg = 240 mL first bolus. Reassess after administration.",
            "source": "SNHD Protocols - Pediatric Shock",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "After first bolus, the 12 kg child remains hypotensive. Second bolus calculation: 12 kg × 20 mL/kg = ? Total given?",
            "options": [
                "120 mL, total 360 mL",
                "240 mL, total 480 mL (40 mL/kg)",
                "500 mL, total 740 mL",
                "1000 mL total",
            ],
            "correct_answer": 1,
            "explanation": "Second bolus is another 240 mL. Total is 480 mL or 40 mL/kg. Maximum recommended before reassessment.",
            "source": "SNHD Protocols - Pediatric Bolus Limits",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "A 5-year-old weighs 18 kg. Calculate fluid bolus: 18 kg × 20 mL/kg = ?",
            "options": ["300 mL", "360 mL", "400 mL", "500 mL"],
            "correct_answer": 1,
            "explanation": "18 kg × 20 mL/kg = 360 mL bolus.",
            "source": "SNHD Protocols - Pediatric Calculation",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "A 7-month-old infant weighs 8 kg. Calculate bolus: 8 kg × 20 mL/kg = ?",
            "options": ["120 mL", "160 mL", "200 mL", "240 mL"],
            "correct_answer": 1,
            "explanation": "8 kg × 20 mL/kg = 160 mL bolus for this infant.",
            "source": "SNHD Protocols - Pediatric Infant Fluids",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "A 10-year-old weighs 32 kg. Calculate: 32 kg × 20 mL/kg = ?",
            "options": ["540 mL", "640 mL", "740 mL", "840 mL"],
            "correct_answer": 1,
            "explanation": "32 kg × 20 mL/kg = 640 mL bolus.",
            "source": "SNHD Protocols - Pediatric Calculation",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "A 14 kg child has received 2 boluses and remains unstable. You have given 14 kg × 20 mL/kg × 2 = ?",
            "options": ["420 mL", "560 mL", "640 mL", "760 mL"],
            "correct_answer": 1,
            "explanation": "14 kg × 20 mL/kg = 280 mL per bolus. Two boluses = 560 mL total (40 mL/kg). Consider other interventions.",
            "source": "SNHD Protocols - Pediatric Maximum Boluses",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "A 50 kg adolescent in DKA with pH 7.1 and altered mental status. Fluid calculation: 50 kg × 20 mL/kg = ? Special consideration?",
            "options": [
                "1000 mL - give rapidly",
                "1000 mL - give cautiously due to cerebral edema risk",
                "2000 mL - DKA needs more",
                "No fluids until glucose normalized",
            ],
            "correct_answer": 1,
            "explanation": "DKA patients get 20 mL/kg (1000 mL) BUT must be given cautiously over 1-2 hours due to cerebral edema risk.",
            "source": "SNHD Protocols - DKA Fluids",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "A 3-day-old neonate weighs 3.5 kg and is in shock. Neonatal bolus: 3.5 kg × 10 mL/kg = ?",
            "options": ["25 mL", "35 mL", "50 mL", "70 mL"],
            "correct_answer": 1,
            "explanation": "Neonates (<28 days) receive 10 mL/kg boluses. 3.5 kg × 10 = 35 mL.",
            "source": "SNHD Protocols - Neonatal Bolus",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "A 9 kg infant in shock. First bolus: 9 kg × 20 mL/kg = ? Second bolus if needed?",
            "options": [
                "180 mL, then 180 mL more",
                "200 mL, then 200 mL more",
                "150 mL, then reassess",
                "No bolus - infants get IV only",
            ],
            "correct_answer": 0,
            "explanation": "9 kg × 20 = 180 mL first bolus. If still unstable, second 180 mL bolus for total 360 mL (40 mL/kg).",
            "source": "SNHD Protocols - Pediatric Infants",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "A 22 kg child has 30% TBSA burns. Using Parkland formula (4 mL × kg × %TBSA): 4 × 22 × 30 = ? First 8 hours?",
            "options": [
                "1320 mL total, 660 mL in first 8 hours",
                "2640 mL total, 1320 mL in first 8 hours",
                "3000 mL total",
                "500 mL in first 8 hours",
            ],
            "correct_answer": 1,
            "explanation": "Parkland: 4 × 22 × 30 = 2640 mL total. Half in first 8 hours = 1320 mL.",
            "source": "SNHD Protocols - Burn Calculation",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "A 6-year-old weighs 21 kg and has severe vomiting with signs of shock. Bolus calculation: 21 kg × 20 mL/kg = ?",
            "options": ["320 mL", "420 mL", "520 mL", "620 mL"],
            "correct_answer": 1,
            "explanation": "21 kg × 20 mL/kg = 420 mL first bolus for hypovolemic shock.",
            "source": "SNHD Protocols - Dehydration",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "A 28 kg child needs fluids but has rales and JVD. What do you do?",
            "options": [
                "Give full 560 mL bolus",
                "Give half bolus (280 mL)",
                "No bolus - suspected CHF/fluid overload",
                "Give 1000 mL regardless",
            ],
            "correct_answer": 2,
            "explanation": "Rales and JVD indicate fluid overload/CHF. Fluid bolus is CONTRAINDICATED.",
            "source": "SNHD Protocols - Pediatric Contraindications",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "A 15-month-old weighs 10 kg and is lethargic with delayed cap refill. Bolus: 10 kg × 20 mL/kg = ?",
            "options": ["150 mL", "200 mL", "250 mL", "300 mL"],
            "correct_answer": 1,
            "explanation": "10 kg × 20 mL/kg = 200 mL first bolus for shock.",
            "source": "SNHD Protocols - Toddler Fluids",
        },
        # === ULTRA-DETAILED PEDIATRIC MEDICATION CALCULATIONS ===
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 9-year-old weighs 27 kg and has anaphylaxis. Epinephrine: 27 kg × 0.01 mg/kg = ? mg IM (max 0.3 mg)",
            "options": ["0.2 mg", "0.27 mg", "0.3 mg (capped)", "0.5 mg"],
            "correct_answer": 1,
            "explanation": "27 kg × 0.01 = 0.27 mg IM. Under 0.3 mg max, so give 0.27 mg of 1:1000.",
            "source": "SNHD Protocols - Epinephrine Calculation",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 5-year-old weighs 19 kg with anaphylaxis. Epinephrine: 19 kg × 0.01 mg/kg = ? Check against max.",
            "options": ["0.15 mg", "0.19 mg", "0.25 mg", "0.3 mg (capped)"],
            "correct_answer": 1,
            "explanation": "19 kg × 0.01 = 0.19 mg IM. Under 0.3 mg max, so give full calculated dose.",
            "source": "SNHD Protocols - Pediatric Anaphylaxis",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 35 kg child has anaphylaxis. Epinephrine: 35 kg × 0.01 = 0.35 mg. Apply max. Dose?",
            "options": ["0.3 mg (capped)", "0.35 mg", "0.4 mg", "0.5 mg"],
            "correct_answer": 0,
            "explanation": "Calculated 0.35 mg, but MAXIMUM pediatric epinephrine is 0.3 mg IM. Give 0.3 mg.",
            "source": "SNHD Protocols - Pediatric Med Max",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 12 kg child has status epilepticus. Midazolam: 12 kg × 0.1 mg/kg = ? mg IM/IN (max 5 mg)",
            "options": ["0.8 mg", "1.0 mg", "1.2 mg", "5 mg"],
            "correct_answer": 2,
            "explanation": "12 kg × 0.1 = 1.2 mg IM/IN. Under 5 mg max, so give 1.2 mg.",
            "source": "SNHD Protocols - Midazolam Calc",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "An 8-year-old weighs 23 kg with asthma. Albuterol: 23 kg × 0.15 mg/kg = ? mg (min 2.5 mg, max 5 mg)",
            "options": ["2.5 mg (minimum)", "3.45 mg", "5 mg (maximum)", "7 mg"],
            "correct_answer": 1,
            "explanation": "23 kg × 0.15 = 3.45 mg. Between 2.5-5 mg range, so give 3.45 mg (or round to 3.5 mg).",
            "source": "SNHD Protocols - Albuterol Calc",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 4-year-old weighs 16 kg with severe asthma. Albuterol: 16 kg × 0.15 = 2.4 mg. Check min/max.",
            "options": ["2.4 mg", "2.5 mg (minimum)", "3 mg", "5 mg"],
            "correct_answer": 1,
            "explanation": "Calculated 2.4 mg, but MINIMUM is 2.5 mg. Give at least 2.5 mg.",
            "source": "SNHD Protocols - Albuterol Min",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 40 kg child with severe pain. Fentanyl: 40 kg × 1 mcg/kg = ? mcg IN (max 100 mcg)",
            "options": ["30 mcg", "40 mcg", "50 mcg", "100 mcg"],
            "correct_answer": 1,
            "explanation": "40 kg × 1 mcg/kg = 40 mcg IN. Under 100 mcg max. Give 40 mcg (20 mcg per nostril).",
            "source": "SNHD Protocols - Fentanyl Calc",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 55 kg adolescent needs fentanyl. 55 kg × 1 mcg/kg = 55 mcg. Max is 100 mcg. Dose?",
            "options": ["50 mcg", "55 mcg", "100 mcg", "150 mcg"],
            "correct_answer": 2,
            "explanation": "55 mcg calculated, but can give up to 100 mcg max. Consider giving 100 mcg for severe pain.",
            "source": "SNHD Protocols - Fentanyl Max",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 7 kg infant is hypoglycemic. D10: 7 kg × 5 mL/kg = ? mL slow IV",
            "options": ["25 mL", "30 mL", "35 mL", "50 mL"],
            "correct_answer": 2,
            "explanation": "7 kg × 5 mL/kg = 35 mL D10 slow IV push for hypoglycemia.",
            "source": "SNHD Protocols - D10 Calculation",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 30 kg child needs RSI. Rocuronium: 30 kg × 1.2 mg/kg = ? mg IV",
            "options": ["24 mg", "30 mg", "36 mg", "40 mg"],
            "correct_answer": 2,
            "explanation": "30 kg × 1.2 mg/kg = 36 mg IV rocuronium for paralysis.",
            "source": "SNHD Protocols - Rocuronium Calc",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 20 kg child needs succinylcholine for RSI. 20 kg × 2 mg/kg = ? mg IV",
            "options": ["30 mg", "35 mg", "40 mg", "50 mg"],
            "correct_answer": 2,
            "explanation": "20 kg × 2 mg/kg = 40 mg IV succinylcholine.",
            "source": "SNHD Protocols - Succinylcholine Calc",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 14 kg toddler with VF. Amiodarone: 14 kg × 5 mg/kg = ? mg IV/IO (max 300 mg)",
            "options": ["50 mg", "60 mg", "70 mg", "300 mg"],
            "correct_answer": 2,
            "explanation": "14 kg × 5 mg/kg = 70 mg IV/IO. Well under 300 mg max.",
            "source": "SNHD Protocols - Amiodarone Calc",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 65 kg adolescent in cardiac arrest needs amiodarone. 65 kg × 5 mg/kg = 325 mg. Apply max.",
            "options": ["300 mg (capped)", "325 mg", "350 mg", "400 mg"],
            "correct_answer": 0,
            "explanation": "Calculated 325 mg, but MAXIMUM is 300 mg. Give 300 mg IV/IO.",
            "source": "SNHD Protocols - Amiodarone Max",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 17 kg child has fever. Acetaminophen: 17 kg × 15 mg/kg = ? mg PO/PR",
            "options": ["200 mg", "255 mg", "300 mg", "350 mg"],
            "correct_answer": 1,
            "explanation": "17 kg × 15 mg/kg = 255 mg PO or PR (round to 240 mg or 260 mg per local protocol).",
            "source": "SNHD Protocols - Acetaminophen Calc",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 6 kg infant is hypoglycemic. Dextrose gel: 6 kg × 0.5 g/kg = ? g (if awake)",
            "options": ["2 g", "3 g", "4 g", "5 g"],
            "correct_answer": 1,
            "explanation": "6 kg × 0.5 g/kg = 3 g oral glucose gel if awake with gag reflex.",
            "source": "SNHD Protocols - Oral Glucose",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 42 kg child needs ketamine for RSI. 42 kg × 2 mg/kg = ? mg IV",
            "options": ["60 mg", "74 mg", "84 mg", "100 mg"],
            "correct_answer": 2,
            "explanation": "42 kg × 2 mg/kg = 84 mg IV ketamine for induction.",
            "source": "SNHD Protocols - Ketamine Calc",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 25 kg child needs midazolam for seizure. 25 kg × 0.1 mg/kg = ? mg IM/IN (max 5 mg)",
            "options": ["2 mg", "2.5 mg", "3 mg", "5 mg"],
            "correct_answer": 1,
            "explanation": "25 kg × 0.1 = 2.5 mg IM/IN. Under 5 mg max. Can repeat in 5-10 minutes.",
            "source": "SNHD Protocols - Midazolam Calc",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 10 kg child has allergic reaction. Diphenhydramine: 10 kg × 0.5 mg/kg = ? mg (max 25 mg)",
            "options": ["3 mg", "5 mg", "10 mg", "25 mg"],
            "correct_answer": 1,
            "explanation": "10 kg × 0.5 mg/kg = 5 mg IV/IM. Under 25 mg max.",
            "source": "SNHD Protocols - Diphenhydramine Calc",
        },
        # === PEDIATRIC CONTRAINDICATIONS & EXCEPTIONS ===
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 3-year-old is wheezing but has a known sulfa allergy. Can you give albuterol?",
            "options": [
                "No - contraindicated",
                "Yes - albuterol is not a sulfa drug",
                "Only if severe",
                "Give epinephrine instead",
            ],
            "correct_answer": 1,
            "explanation": "Albuterol does NOT contain sulfa. Safe to give despite sulfa allergy.",
            "source": "SNHD Protocols - Allergy Clarification",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A child needs pain control but has respiratory rate of 8. Which medication is CONTRAINDICATED?",
            "options": ["Acetaminophen", "Fentanyl", "Ketorolac", "Ibuprofen"],
            "correct_answer": 1,
            "explanation": "Fentanyl is contraindicated with respiratory depression (RR <10). Use non-opioid alternatives.",
            "source": "SNHD Protocols - Opioid Contraindications",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 2-year-old has SVT. Adenosine should be given:",
            "options": [
                "Rapid IV push with immediate flush",
                "Slow IV drip",
                "IM injection",
                "Subcutaneously",
            ],
            "correct_answer": 0,
            "explanation": "Adenosine must be rapid IV push followed immediately by 5-10 mL saline flush (half-life <10 seconds).",
            "source": "SNHD Protocols - Adenosine Administration",
        },
        # === COMPREHENSIVE PEDIATRIC MEDICATION DATABASE ===
        # Pain Management
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 20 kg child has moderate pain from a fracture. Ibuprofen dosing: 20 kg × 10 mg/kg = ?",
            "options": ["100 mg", "200 mg", "300 mg", "400 mg"],
            "correct_answer": 1,
            "explanation": "20 kg × 10 mg/kg = 200 mg PO ibuprofen (max 400 mg/dose, 1200 mg/day).",
            "source": "SNHD Protocols - Ibuprofen Dosing",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 15 kg toddler needs pain relief. Acetaminophen rectal: 15 kg × 15 mg/kg = ?",
            "options": ["150 mg", "200 mg", "225 mg", "300 mg"],
            "correct_answer": 2,
            "explanation": "15 kg × 15 mg/kg = 225 mg PR acetaminophen (round to 240 mg per local protocol).",
            "source": "SNHD Protocols - Acetaminophen PR",
        },
        # Anti-emetics
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "An 18 kg child with vomiting. Ondansetron: 18 kg × 0.15 mg/kg = ? mg (max 4 mg)",
            "options": ["2 mg", "2.4 mg", "2.7 mg", "4 mg"],
            "correct_answer": 2,
            "explanation": "18 kg × 0.15 = 2.7 mg PO/ODT. Under 4 mg max. Can round to 2.5 or 3 mg.",
            "source": "SNHD Protocols - Ondansetron Dosing",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 25 kg child needs ondansetron. 25 kg × 0.15 = 3.75 mg. IV dosing is different:",
            "options": ["0.1 mg/kg IV (max 2 mg)", "0.15 mg/kg IV", "0.5 mg/kg IV", "1 mg/kg IV"],
            "correct_answer": 0,
            "explanation": "Ondansetron IV: 0.1 mg/kg (max 2 mg IV). PO/ODT is 0.15 mg/kg (max 4 mg).",
            "source": "SNHD Protocols - Ondansetron IV vs PO",
        },
        # Bronchodilators
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 12 kg infant with wheezing. Albuterol: 12 kg × 0.15 mg/kg = ? (min 2.5 mg)",
            "options": ["1.5 mg", "1.8 mg", "2.5 mg (minimum)", "3 mg"],
            "correct_answer": 2,
            "explanation": "12 kg × 0.15 = 1.8 mg, but MINIMUM is 2.5 mg. Give 2.5 mg via nebulizer.",
            "source": "SNHD Protocols - Albuterol Minimum",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Albuterol can be repeated every how often in severe pediatric asthma?",
            "options": ["Every 15 minutes", "Every 20-30 minutes", "Every hour", "Once only"],
            "correct_answer": 1,
            "explanation": "Albuterol can be repeated every 20-30 minutes in severe asthma with reassessment.",
            "source": "SNHD Protocols - Albuterol Frequency",
        },
        # Steroids
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 20 kg child with moderate asthma exacerbation. Prednisolone: 20 kg × 1 mg/kg = ?",
            "options": ["10 mg", "20 mg", "30 mg", "40 mg"],
            "correct_answer": 1,
            "explanation": "20 kg × 1 mg/kg = 20 mg PO prednisolone (typical range 1-2 mg/kg).",
            "source": "SNHD Protocols - Prednisolone Dosing",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Dexamethasone for pediatric asthma/croup alternative dosing:",
            "options": [
                "0.3 mg/kg PO/IM (max 10 mg)",
                "0.6 mg/kg PO/IM (max 10 mg)",
                "1 mg/kg",
                "2 mg/kg",
            ],
            "correct_answer": 1,
            "explanation": "Dexamethasone: 0.6 mg/kg PO/IM (max 10 mg) - longer acting than prednisolone.",
            "source": "SNHD Protocols - Dexamethasone",
        },
        # Narcotic Reversal
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 10 kg infant with opioid-induced respiratory depression. Naloxone: 10 kg × 0.1 mg/kg = ?",
            "options": ["0.5 mg", "1 mg", "1.5 mg", "2 mg"],
            "correct_answer": 1,
            "explanation": "10 kg × 0.1 mg/kg = 1 mg IV/IM/IN (max 2 mg). Titrate to effect, not full reversal.",
            "source": "SNHD Protocols - Naloxone Pediatric",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Naloxone for a 4-year-old (16 kg) with suspected overdose. Intranasal dosing?",
            "options": [
                "1 mg in one nostril",
                "2 mg total (1 mg each nostril)",
                "4 mg in one nostril",
                "0.5 mg total",
            ],
            "correct_answer": 1,
            "explanation": "Pediatric IN naloxone: 2 mg total, divided as 1 mg in each nostril (max per nostril).",
            "source": "SNHD Protocols - Naloxone IN",
        },
        # Cardiac/Epinephrine variations
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 3 kg newborn in cardiac arrest needs epinephrine. Dose: 3 kg × 0.01 mg/kg = ? mg IV/IO",
            "options": ["0.01 mg", "0.03 mg", "0.1 mg", "0.3 mg"],
            "correct_answer": 1,
            "explanation": "3 kg × 0.01 mg/kg = 0.03 mg (0.3 mL of 1:10,000) IV/IO every 3-5 minutes.",
            "source": "SNHD Protocols - Neonatal Epinephrine",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Pediatric epinephrine for cardiac arrest vs anaphylaxis dosing differs. Arrest is:",
            "options": [
                "0.01 mg/kg IV/IO (1:10,000)",
                "0.1 mg/kg IV/IO",
                "0.01 mg/kg IM",
                "0.3 mg fixed",
            ],
            "correct_answer": 0,
            "explanation": "Cardiac arrest: 0.01 mg/kg (0.1 mL/kg) of 1:10,000 IV/IO. Anaphylaxis: 0.01 mg/kg IM (1:1,000).",
            "source": "SNHD Protocols - Epinephrine Routes",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Atropine for pediatric symptomatic bradycardia (minimum dose to prevent paradoxical bradycardia):",
            "options": [
                "0.01 mg/kg (min 0.1 mg, max 0.5 mg)",
                "0.02 mg/kg IV",
                "0.1 mg fixed",
                "0.5 mg fixed",
            ],
            "correct_answer": 0,
            "explanation": "Atropine: 0.02 mg/kg IV/IO (minimum 0.1 mg, maximum 0.5 mg child, 1 mg adolescent).",
            "source": "SNHD Protocols - Atropine Pediatric",
        },
        # RSI Medications detailed
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 24 kg child needs RSI. Etomidate induction dose: 24 kg × 0.3 mg/kg = ? mg IV",
            "options": ["5 mg", "7.2 mg", "10 mg", "15 mg"],
            "correct_answer": 1,
            "explanation": "24 kg × 0.3 mg/kg = 7.2 mg IV etomidate for induction (typical range 0.2-0.3 mg/kg).",
            "source": "SNHD Protocols - Etomidate Pediatric",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Ketamine for pediatric sedation (not RSI): 30 kg × 1 mg/kg = ? mg IV/IM",
            "options": ["10 mg", "20 mg", "30 mg", "60 mg"],
            "correct_answer": 2,
            "explanation": "30 kg × 1 mg/kg = 30 mg IV/IM for procedural sedation (RSI dose is 2 mg/kg).",
            "source": "SNHD Protocols - Ketamine Sedation",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Propofol for pediatric RSI: 25 kg × 2 mg/kg = ? mg IV",
            "options": ["25 mg", "50 mg", "75 mg", "100 mg"],
            "correct_answer": 1,
            "explanation": "25 kg × 2 mg/kg = 50 mg IV propofol (use cautiously, can cause hypotension).",
            "source": "SNHD Protocols - Propofol Pediatric",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 20 kg child post-intubation needs ongoing paralysis. Vecuronium: 20 kg × 0.1 mg/kg = ?",
            "options": ["1 mg", "2 mg", "3 mg", "4 mg"],
            "correct_answer": 1,
            "explanation": "20 kg × 0.1 mg/kg = 2 mg IV vecuronium for maintenance paralysis.",
            "source": "SNHD Protocols - Vecuronium",
        },
        # Sedation/Analgesia combos
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Post-intubation sedation for 40 kg child: Fentanyl 1 mcg/kg + Midazolam 0.1 mg/kg = ?",
            "options": [
                "20 mcg fentanyl + 2 mg midazolam",
                "40 mcg fentanyl + 4 mg midazolam",
                "60 mcg fentanyl + 6 mg midazolam",
                "100 mcg fentanyl + 10 mg midazolam",
            ],
            "correct_answer": 1,
            "explanation": "40 kg: 40 mcg fentanyl + 4 mg midazolam. Both analgesia AND sedation required.",
            "source": "SNHD Protocols - Post-Intubation Care",
        },
        # Glucose management
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 5 kg infant with BG 45 mg/dL and altered mental status. D10: 5 kg × 5 mL/kg = ?",
            "options": ["15 mL", "25 mL", "35 mL", "50 mL"],
            "correct_answer": 1,
            "explanation": "5 kg × 5 mL/kg = 25 mL D10 slow IV push for hypoglycemia.",
            "source": "SNHD Protocols - Infant Hypoglycemia",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Glucagon for a 12 kg child unable to take PO with BG 50: 12 kg × 0.03 mg/kg = ? mg IM",
            "options": ["0.2 mg", "0.36 mg", "0.5 mg", "1 mg"],
            "correct_answer": 1,
            "explanation": "12 kg × 0.03 mg/kg = 0.36 mg IM/SC glucagon (if no IV access, can use 0.5 mg min).",
            "source": "SNHD Protocols - Glucagon Pediatric",
        },
        # Antibiotics (rare but important)
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 30 kg child with suspected meningitis. Ceftriaxone: 30 kg × 50 mg/kg = ? mg IM/IV",
            "options": ["500 mg", "1000 mg", "1500 mg", "2000 mg"],
            "correct_answer": 2,
            "explanation": "30 kg × 50 mg/kg = 1500 mg IM/IV ceftriaxone (max 2 g) for suspected meningitis.",
            "source": "SNHD Protocols - Meningitis Antibiotics",
        },
        # Magnesium
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 25 kg child with refractory asthma. Magnesium: 25 kg × 25-50 mg/kg = ? mg IV (max 2 g)",
            "options": ["250-500 mg", "625-1250 mg", "1000-1500 mg", "2000 mg"],
            "correct_answer": 1,
            "explanation": "25 kg × 25-50 mg/kg = 625-1250 mg IV magnesium sulfate over 20 minutes.",
            "source": "SNHD Protocols - Magnesium Asthma",
        },
        # Calcium
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 20 kg child with hyperkalemia. Calcium gluconate: 20 kg × 0.5-1 mL/kg = ? mL",
            "options": ["5-10 mL", "10-20 mL", "20-30 mL", "30-40 mL"],
            "correct_answer": 1,
            "explanation": "20 kg × 0.5-1 mL/kg = 10-20 mL calcium gluconate slow IV for hyperkalemia/cardiac stabilization.",
            "source": "SNHD Protocols - Hyperkalemia",
        },
        # Sodium bicarbonate
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 15 kg child with severe metabolic acidosis. Sodium bicarb: 15 kg × 1-2 mEq/kg = ? mEq",
            "options": ["5-10 mEq", "15-30 mEq", "30-45 mEq", "45-60 mEq"],
            "correct_answer": 1,
            "explanation": "15 kg × 1-2 mEq/kg = 15-30 mEq sodium bicarbonate slow IV for severe acidosis.",
            "source": "SNHD Protocols - Bicarbonate",
        },
        # Diphenhydramine detailed
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A 22 kg child with allergic reaction. Diphenhydramine PO: 22 kg × 1 mg/kg = ? mg (max 50 mg)",
            "options": ["15 mg", "22 mg", "25 mg", "50 mg"],
            "correct_answer": 1,
            "explanation": "22 kg × 1 mg/kg = 22 mg PO diphenhydramine (IV/IM is 0.5 mg/kg, max 25 mg).",
            "source": "SNHD Protocols - Diphenhydramine PO",
        },
        # Special scenarios
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "A child with organophosphate poisoning needs atropine. Initial dose and escalation?",
            "options": [
                "0.01 mg/kg once",
                "0.02 mg/kg, double every 5 min until secretions dry",
                "0.1 mg/kg single dose",
                "1 mg fixed regardless of weight",
            ],
            "correct_answer": 1,
            "explanation": "Organophosphate: 0.02 mg/kg atropine, double every 5 min until drying of secretions (toxic dose may be very high).",
            "source": "SNHD Protocols - Organophosphate",
        },
        # Weight-based shortcuts
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Broselow tape color zones estimate weights. Yellow zone is approximately:",
            "options": ["3-5 kg", "10-11 kg", "15-18 kg", "24-29 kg"],
            "correct_answer": 1,
            "explanation": "Broselow tape: Yellow = 10-11 kg (approximately 1 year old).",
            "source": "SNHD Protocols - Broselow Reference",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Using Broselow tape, Purple zone (smallest) equipment sizes and approximate weight:",
            "options": [
                "Premature <3 kg",
                "Term newborn 3-5 kg",
                "3-6 months 5-7 kg",
                "6-12 months 8-10 kg",
            ],
            "correct_answer": 1,
            "explanation": "Broselow Purple = term newborn approximately 3-5 kg.",
            "source": "SNHD Protocols - Broselow Purple",
        },
        # === CLARK COUNTY SNHD SPECIFIC QUESTIONS FROM NOTEBOOKLM ===
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "What is the standard weight-based volume for an initial NS or LR bolus in pediatric patients according to the Clark County protocols?",
            "options": ["30 ml/kg", "20 ml/kg", "10 ml/kg", "50 ml/kg"],
            "correct_answer": 1,
            "explanation": "20 ml/kg is the fundamental weight-based fluid increment for pediatric patients across most shock and assessment protocols.",
            "source": "SNHD Protocols - Pediatric Fluids",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "What is the maximum total volume of NS or LR that should be administered to a pediatric patient in shock before seeking medical direction?",
            "options": ["100 ml/kg", "40 ml/kg", "20 ml/kg", "60 ml/kg"],
            "correct_answer": 1,
            "explanation": "Maximum 40 ml/kg (2 boluses) before seeking medical direction or considering other interventions.",
            "source": "SNHD Protocols - Pediatric Shock Limits",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "If a pediatric patient with abdominal pain is suspected of being in Diabetic Ketoacidosis (DKA), what is the maximum amount of fluid bolus allowed?",
            "options": ["20 ml/kg", "10 ml/kg", "60 ml/kg", "40 ml/kg"],
            "correct_answer": 1,
            "explanation": "DKA patients get maximum 10 ml/kg bolus due to risk of cerebral edema.",
            "source": "SNHD Protocols - Pediatric DKA",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "According to the Pediatric Burn protocol, what is the appropriate fluid bolus for a 4-year-old child showing signs of hypoperfusion?",
            "options": ["250 ml", "125 ml", "500 ml", "20 ml/kg"],
            "correct_answer": 3,
            "explanation": "Pediatric burn protocol uses 20 ml/kg for hypoperfusion, not fixed volumes.",
            "source": "SNHD Protocols - Pediatric Burn",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "In the Pediatric Burn protocol, what is the fixed bolus volume for a 10-year-old child?",
            "options": ["1000 ml", "125 ml", "500 ml", "250 ml"],
            "correct_answer": 2,
            "explanation": "Pediatric burn protocol specifies 500 ml fixed bolus for certain age groups with hypoperfusion.",
            "source": "SNHD Protocols - Pediatric Burn Fixed",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "For a 15-year-old patient being treated under the Pediatric Burn protocol, what fluid bolus should be administered?",
            "options": ["20 ml/kg", "500 ml", "1000 ml", "250 ml"],
            "correct_answer": 1,
            "explanation": "500 ml bolus for pediatric burn patients in specific age/weight categories.",
            "source": "SNHD Protocols - Pediatric Burn",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Assessment",
            "question": "What is the calculated minimum acceptable systolic blood pressure for a 5-year-old child?",
            "options": ["90 mmHg", "70 mmHg", "100 mmHg", "80 mmHg"],
            "correct_answer": 3,
            "explanation": "Using formula (Age × 2) + 70: (5 × 2) + 70 = 80 mmHg minimum SBP.",
            "source": "SNHD Protocols - Pediatric BP Calculation",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "When treating a pediatric patient for non-traumatic shock, which clinical finding indicates that you should stop repeating fluid boluses?",
            "options": [
                "A systolic blood pressure of 70 mmHg in a 1-year-old",
                "The patient remains tachycardic",
                "Presence of rales on lung exam",
                "The patient develops a fever",
            ],
            "correct_answer": 2,
            "explanation": "Rales on lung exam indicates fluid overload - stop fluids and contact medical direction.",
            "source": "SNHD Protocols - Fluid Contraindications",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Assessment",
            "question": "What is the minimum systolic blood pressure target for a 2-year-old child undergoing fluid resuscitation?",
            "options": ["72 mmHg", "74 mmHg", "80 mmHg", "90 mmHg"],
            "correct_answer": 1,
            "explanation": "Using formula (Age × 2) + 70: (2 × 2) + 70 = 74 mmHg minimum SBP.",
            "source": "SNHD Protocols - Pediatric BP Target",
        },
        {
            "level": "EMT",
            "category": "Fluid Boluses",
            "subcategory": "General",
            "question": "Which fluid types are approved for bolus administration in both adult and pediatric patients according to these protocols?",
            "options": ["NS with 20 mEq/L Potassium", "D5W or NS", "NS or LR", "0.45% NS only"],
            "correct_answer": 2,
            "explanation": "Normal Saline (NS) or Lactated Ringers (LR) are approved for boluses in all patients.",
            "source": "SNHD Protocols - Approved Fluids",
        },
        {
            "level": "EMT",
            "category": "Environmental",
            "subcategory": "Heat/Cold",
            "question": "For adult patients suffering from heat-related or cold-related illness with poor perfusion, what is the initial bolus volume?",
            "options": ["2000 ml", "500 ml", "1000 ml", "250 ml"],
            "correct_answer": 1,
            "explanation": "500 ml bolus for environmental illness with poor perfusion in adults.",
            "source": "SNHD Protocols - Environmental Illness",
        },
        {
            "level": "EMT",
            "category": "Environmental",
            "subcategory": "Heat",
            "question": "What is the maximum cumulative fluid limit for an adult patient being treated for Heat-Related illness?",
            "options": ["3000 ml", "60 ml/kg", "1000 ml", "2000 ml"],
            "correct_answer": 3,
            "explanation": "Maximum 2000 ml cumulative for heat-related illness in adults.",
            "source": "SNHD Protocols - Heat Illness Limits",
        },
        {
            "level": "EMT",
            "category": "Assessment",
            "subcategory": "General",
            "question": "According to the general assessment Pearls, what action must be performed after each fluid bolus is administered?",
            "options": [
                "Administer an antiemetic",
                "Perform retroperitoneal palpation",
                "Check a blood glucose level",
                "Repeat vital signs",
            ],
            "correct_answer": 3,
            "explanation": "Repeat vital signs after every fluid bolus to assess response and avoid fluid overload.",
            "source": "SNHD Protocols - Assessment Pearls",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Cardiac",
            "question": "In the case of pediatric bradycardia with poor perfusion, what fluid intervention is indicated if hypovolemia is suspected?",
            "options": [
                "No fluid bolus is indicated for bradycardia",
                "10 ml/kg bolus",
                "D10 at 5 ml/kg",
                "20 ml/kg bolus",
            ],
            "correct_answer": 3,
            "explanation": "Pediatric bradycardia with poor perfusion gets 20 ml/kg bolus if hypovolemia suspected after oxygenation/ventilation.",
            "source": "SNHD Protocols - Pediatric Bradycardia",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Which protocol specifies that Morphine is not recommended for children?",
            "options": [
                "Neonatal Resuscitation",
                "Pediatric Allergic Reaction",
                "Pediatric Burns",
                "Pediatric Abdominal Pain",
            ],
            "correct_answer": 2,
            "explanation": "Pediatric Burn protocol specifies morphine is not recommended for children.",
            "source": "SNHD Protocols - Pediatric Burns",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Environmental",
            "question": "For a pediatric smoke inhalation patient with hypotension, what is the appropriate initial fluid management?",
            "options": [
                "NS or LR bolus at 125 ml",
                "NS or LR bolus at 20 ml/kg",
                "NS bolus at 500 ml",
                "Hydroxocobalamin only",
            ],
            "correct_answer": 1,
            "explanation": "Pediatric smoke inhalation with hypotension gets 20 ml/kg NS or LR bolus.",
            "source": "SNHD Protocols - Smoke Inhalation",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "What is the maximum cumulative dose for fluid boluses in the Pediatric Allergic Reaction protocol for a patient in shock?",
            "options": ["2000 ml", "60 ml/kg", "30 ml/kg", "20 ml/kg"],
            "correct_answer": 3,
            "explanation": "Pediatric Allergic Reaction protocol limits fluids to maximum 20 ml/kg for shock.",
            "source": "SNHD Protocols - Pediatric Allergic Reaction",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "For patients with known adrenal insufficiency, what is the primary recommended intervention alongside fluid boluses?",
            "options": [
                "Oral glucose regardless of BG level",
                "Administer high-dose Epinephrine",
                "Wait for medical direction",
                "Administer the patient's own Solu-Cortef",
            ],
            "correct_answer": 3,
            "explanation": "Patients with adrenal insufficiency should receive their own Solu-Cortef (hydrocortisone) if available.",
            "source": "SNHD Protocols - Adrenal Insufficiency",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Assessment",
            "question": "The estimated minimum systolic blood pressure calculation formula ((Age in Years×2)+70) applies up to what age?",
            "options": ["5 years", "18 years", "10 years", "13 years"],
            "correct_answer": 1,
            "explanation": "Formula (Age × 2) + 70 applies up to age 18. Adult minimum (90 mmHg) applies after age 18.",
            "source": "SNHD Protocols - BP Formula Age",
        },
        {
            "level": "EMT",
            "category": "Neonatal",
            "subcategory": "CPR",
            "question": "In Neonatal Resuscitation, what is the required compression-to-ventilation ratio for CPR?",
            "options": ["10:1", "15:2", "3:1", "30:2"],
            "correct_answer": 2,
            "explanation": "Neonatal CPR uses 3:1 compression-to-ventilation ratio (3 compressions, 1 breath).",
            "source": "SNHD Protocols - Neonatal CPR",
        },
        {
            "level": "EMT",
            "category": "Neonatal",
            "subcategory": "Medications",
            "question": "What dose of D10 is specified for a newborn with hypoglycemia (BG<40 mg/dl)?",
            "options": ["5 ml/kg", "10 ml/kg", "2 ml/kg", "20 ml/kg"],
            "correct_answer": 0,
            "explanation": "Neonatal hypoglycemia: D10 at 5 ml/kg IV/IO.",
            "source": "SNHD Protocols - Neonatal Hypoglycemia",
        },
        {
            "level": "EMT",
            "category": "Neonatal",
            "subcategory": "Assessment",
            "question": "What threshold defines hypoglycemia in a newborn according to the protocols?",
            "options": ["<60 mg/dl", "<20 mg/dl", "<80 mg/dl", "<40 mg/dl"],
            "correct_answer": 3,
            "explanation": "Newborn hypoglycemia is defined as blood glucose <40 mg/dl.",
            "source": "SNHD Protocols - Neonatal Glucose",
        },
        {
            "level": "PARAMEDIC",
            "category": "Neonatal",
            "subcategory": "Medications",
            "question": "Which concentration of Sodium Bicarbonate should be used for neonatal patients according to the protocols?",
            "options": ["0.45%", "5%", "8.4%", "4.2%"],
            "correct_answer": 3,
            "explanation": "Neonates should receive 4.2% sodium bicarbonate (diluted from 8.4%).",
            "source": "SNHD Protocols - Neonatal Bicarbonate",
        },
        {
            "level": "PARAMEDIC",
            "category": "Burns",
            "subcategory": "Protocols",
            "question": "What is the primary reason to contact Medical Direction at the Burn Center according to the tiered burn protocols?",
            "options": [
                "For further drip rates or additional boluses",
                "To confirm the patient's age",
                "To report blood glucose levels",
                "To request an initial fluid bolus",
            ],
            "correct_answer": 0,
            "explanation": "Contact Burn Center Medical Direction for further drip rates or additional boluses beyond initial protocol.",
            "source": "SNHD Protocols - Burn Center Contact",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "In the Pediatric Allergic Reaction protocol, what is the maximum single dose of Diphenhydramine?",
            "options": ["1 mg", "50 mg", "25 mg", "100 mg"],
            "correct_answer": 1,
            "explanation": "Maximum single dose of diphenhydramine in pediatric allergic reaction is 50 mg.",
            "source": "SNHD Protocols - Pediatric Diphenhydramine",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "What is the maximum single dose of D10 when treating a pediatric patient for hypoglycemia?",
            "options": ["60 ml", "25 g", "50 g", "5 g"],
            "correct_answer": 1,
            "explanation": "Maximum single dose of D10 for pediatric hypoglycemia is 25 grams.",
            "source": "SNHD Protocols - D10 Maximum",
        },
        # === ADDITIONAL PEDIATRIC MEDICATION QUESTIONS ===
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "What is the appropriate dose of Glucagon for a pediatric patient with no IV access who weighs less than 20 kg?",
            "options": ["0.5 mg IM", "0.1 mg/kg IM", "0.01 mg/kg IM", "1 mg IM"],
            "correct_answer": 0,
            "explanation": "Glucagon for pediatrics <20 kg without IV access: 0.5 mg IM.",
            "source": "SNHD Protocols - Glucagon Pediatric",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "According to the Pediatric Allergic Reaction protocol, what is the maximum single dose of Epinephrine 1:1000 that can be administered IM?",
            "options": ["0.5 mg", "1.5 mg", "0.3 mg", "0.1 mg"],
            "correct_answer": 2,
            "explanation": "Maximum single dose of Epinephrine 1:1000 IM for pediatric allergic reaction is 0.3 mg.",
            "source": "SNHD Protocols - Pediatric Epi Max",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "In a pediatric patient with suspected hypoglycemia, what is the correct volume and concentration for a D10 IV/IO bolus?",
            "options": ["2 ml/kg of D10", "5 ml/kg of D10", "25 ml/kg of D10", "10 ml/kg of D10"],
            "correct_answer": 1,
            "explanation": "Pediatric hypoglycemia: D10 at 5 ml/kg IV/IO bolus.",
            "source": "SNHD Protocols - Pediatric D10",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "What is the weight-based dose for Diphenhydramine (Benadryl) across pediatric protocols for allergic reactions and dystonic reactions?",
            "options": ["0.5 mg/kg", "5 mg/kg", "1 mg/kg", "2 mg/kg"],
            "correct_answer": 2,
            "explanation": "Pediatric diphenhydramine: 1 mg/kg PO or 0.5 mg/kg IV/IM for allergic/dystonic reactions.",
            "source": "SNHD Protocols - Diphenhydramine Dosing",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Which of the following is the maximum single dose for IV Morphine in pediatric pain management?",
            "options": ["2 mg", "5 mg", "15 mg", "10 mg"],
            "correct_answer": 0,
            "explanation": "Maximum single dose of IV Morphine for pediatric pain management is 2 mg.",
            "source": "SNHD Protocols - Pediatric Morphine",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "What is the recommended dose for Push Dose Epinephrine in the treatment of pediatric shock?",
            "options": ["1 mcg/kg", "0.01 mg/kg", "0.1 mcg/kg", "0.1 mg/kg"],
            "correct_answer": 0,
            "explanation": "Push dose epinephrine for pediatric shock: 1 mcg/kg IV/IO.",
            "source": "SNHD Protocols - Push Dose Epi",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "For a pediatric patient in SVT, what is the initial rapid IV/IO push dose of Adenosine?",
            "options": ["0.2 mg/kg", "0.1 mg/kg", "6 mg fixed dose", "0.3 mg/kg"],
            "correct_answer": 1,
            "explanation": "Pediatric SVT: Initial adenosine 0.1 mg/kg rapid IV/IO push (max 6 mg first dose).",
            "source": "SNHD Protocols - Pediatric Adenosine",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "When administering Naloxone (Narcan) titration to a pediatric patient with respiratory depression, what is the per-kilogram dose?",
            "options": ["2 mg fixed dose", "0.5 mg/kg", "0.01 mg/kg", "0.1 mg/kg"],
            "correct_answer": 3,
            "explanation": "Pediatric naloxone titration: 0.1 mg/kg IV/IM/IN (titrate to respiratory effort, not full consciousness).",
            "source": "SNHD Protocols - Naloxone Titration",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "What is the maximum single dose of Fentanyl for a pediatric patient without a physician order?",
            "options": ["50 mcg", "10 mcg", "200 mcg", "100 mcg"],
            "correct_answer": 0,
            "explanation": "Maximum single dose of fentanyl for pediatric patients without physician order is 50 mcg.",
            "source": "SNHD Protocols - Fentanyl Max",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Under the Pediatric Seizure protocol, what is the dose for Midazolam when treating an active seizure?",
            "options": ["0.2 mg/kg", "0.05 mg/kg", "2.5 mg fixed dose", "0.1 mg/kg"],
            "correct_answer": 3,
            "explanation": "Pediatric seizure: Midazolam 0.1 mg/kg IM/IN/IV (max 5 mg).",
            "source": "SNHD Protocols - Midazolam Seizure",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "What is the specific age requirement for administering Metoclopramide (Reglan) to a pediatric patient for nausea or pain?",
            "options": [
                "8 years of age or older",
                "12 years of age or older",
                "10 years of age or older",
                "2 years of age or older",
            ],
            "correct_answer": 0,
            "explanation": "Metoclopramide (Reglan) is only for pediatric patients 8 years or older.",
            "source": "SNHD Protocols - Reglan Age",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "What is the correct dose for IV Acetaminophen (Tylenol) in pediatric patients?",
            "options": ["1 g fixed dose", "15 mg/kg", "10 mg/kg", "0.15 mg/kg"],
            "correct_answer": 1,
            "explanation": "IV Acetaminophen for pediatrics: 15 mg/kg (max adult dose).",
            "source": "SNHD Protocols - IV Tylenol",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "In pediatric bradycardia, what are the minimum and maximum single doses for Atropine?",
            "options": [
                "Min: 0.5 mg; Max: 3 mg",
                "Min: 0.1 mg; Max: 0.5 mg",
                "Min: 0.1 mg; Max: 1 mg",
                "Min: 0.02 mg; Max: 1 mg",
            ],
            "correct_answer": 2,
            "explanation": "Pediatric atropine: Minimum 0.1 mg (to prevent paradoxical bradycardia), Maximum 0.5 mg child / 1 mg adolescent.",
            "source": "SNHD Protocols - Atropine Min/Max",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "What is the pediatric dose for Ondansetron (Zofran)?",
            "options": ["4 mg fixed dose", "0.1 mg/kg", "1 mg/kg", "0.15 mg/kg"],
            "correct_answer": 3,
            "explanation": "Pediatric ondansetron: 0.15 mg/kg PO/ODT (max 4 mg) or 0.1 mg/kg IV (max 2 mg).",
            "source": "SNHD Protocols - Ondansetron Dose",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "According to the Tachycardia protocol, how is Amiodarone administered to a pediatric patient with a pulse?",
            "options": [
                "150 mg over 10 minutes",
                "5 mg/kg rapid IV push",
                "5 mg/kg in 50 ml NS over 20 minutes",
                "0.2 mg/kg over 20 minutes",
            ],
            "correct_answer": 2,
            "explanation": "Amiodarone with pulse: 5 mg/kg in 50 ml NS over 20 minutes (slow infusion).",
            "source": "SNHD Protocols - Amiodarone With Pulse",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "What is the maximum dose of Midazolam allowed for the management of a pediatric febrile seizure?",
            "options": ["10 mg", "2.5 mg", "5 mg", "1 mg"],
            "correct_answer": 2,
            "explanation": "Maximum midazolam for pediatric febrile seizure is 5 mg.",
            "source": "SNHD Protocols - Midazolam Max Seizure",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "When performing pediatric intubation, what is the induction dose for Etomidate?",
            "options": ["0.03 mg/kg", "0.3 mg/kg", "1 mg/kg", "0.15 mg/kg"],
            "correct_answer": 1,
            "explanation": "Pediatric etomidate for RSI induction: 0.3 mg/kg IV.",
            "source": "SNHD Protocols - Etomidate RSI",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Which concentration and dose of Epinephrine is administered via the Endotracheal Tube (ETT) during pediatric bradycardia?",
            "options": [
                "1:1000, 0.1 mg/kg",
                "1:10,000, 0.01 mg/kg",
                "1:1000, 0.01 mg/kg",
                "1:10,000, 0.1 mg/kg",
            ],
            "correct_answer": 0,
            "explanation": "ETT epinephrine: 1:1000 concentration at 0.1 mg/kg (higher concentration for ETT route).",
            "source": "SNHD Protocols - ETT Epinephrine",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "What is the maximum single dose of Naloxone (Narcan) when administered via the Intranasal (IN) route to a pediatric patient?",
            "options": ["0.5 mg", "4 mg", "0.1 mg", "10 mg"],
            "correct_answer": 1,
            "explanation": "Maximum single IN naloxone dose for pediatrics is 4 mg (2 mg per nostril).",
            "source": "SNHD Protocols - Naloxone IN Max",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Under the Pediatric Tachycardia protocol, what is the dose for Magnesium Sulfate in cases of Torsades de Pointes?",
            "options": [
                "2 g fixed dose",
                "5 mg/kg over 20 minutes",
                "50 mg/kg rapid IV push",
                "25 mg/kg in 50 ml NS over 10 minutes",
            ],
            "correct_answer": 3,
            "explanation": "Magnesium for pediatric Torsades: 25-50 mg/kg (max 2 g) over 10-20 minutes.",
            "source": "SNHD Protocols - Magnesium Torsades",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "For pediatric induction during airway management, what is the IV/IO dose for Ketamine?",
            "options": ["4 mg/kg", "0.3 mg/kg", "2 mg/kg", "1 mg/kg"],
            "correct_answer": 2,
            "explanation": "Pediatric ketamine for RSI induction: 2 mg/kg IV/IO.",
            "source": "SNHD Protocols - Ketamine RSI",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "What is the maximum single dose of Ketamine when administered via the IM route for induction?",
            "options": ["500 mg", "200 mg", "100 mg", "400 mg"],
            "correct_answer": 0,
            "explanation": "Maximum single IM ketamine dose for pediatric induction is 500 mg.",
            "source": "SNHD Protocols - Ketamine IM Max",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "In the Pediatric Shock protocol, for a patient with known adrenal insufficiency, what medication should be administered?",
            "options": [
                "0.1 mg/kg Dexamethasone",
                "The patient's own Solu-Cortef (hydrocortisone)",
                "2 mg/kg Methylprednisolone",
                "0.01 mg/kg Epinephrine",
            ],
            "correct_answer": 1,
            "explanation": "Adrenal insufficiency: Give patient's own Solu-Cortef (hydrocortisone) if available.",
            "source": "SNHD Protocols - Adrenal Insufficiency",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "What is the initial volume for a pediatric fluid bolus in a non-trauma shock patient, provided there are no rales on lung exam?",
            "options": ["60 ml/kg", "20 ml/kg", "500 ml", "10 ml/kg"],
            "correct_answer": 1,
            "explanation": "Initial pediatric fluid bolus for non-trauma shock: 20 ml/kg (if no rales/JVD).",
            "source": "SNHD Protocols - Initial Bolus",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "What is the maximum cumulative dose of Epinephrine 1:1000 that can be given IM for a pediatric allergic reaction?",
            "options": ["0.5 mg", "1.0 mg", "1.5 mg", "3.0 mg"],
            "correct_answer": 1,
            "explanation": "Maximum cumulative IM epinephrine 1:1000 for pediatric allergic reaction is 1.0 mg.",
            "source": "SNHD Protocols - Epi Cumulative Max",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "In the Pediatric Pain Management protocol, what is the IN/IM/IV/IO dose for Fentanyl?",
            "options": ["1 mcg/kg", "0.1 mcg/kg", "1 mg/kg", "10 mcg/kg"],
            "correct_answer": 0,
            "explanation": "Pediatric fentanyl: 1 mcg/kg IN/IM/IV/IO (max 50 mcg without physician order).",
            "source": "SNHD Protocols - Fentanyl Dosing",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Under the Post-Intubation Sedation protocol for pediatrics, what is the maximum single dose of Midazolam?",
            "options": ["20 mg", "2.5 mg", "5 mg", "10 mg"],
            "correct_answer": 1,
            "explanation": "Maximum single midazolam dose for pediatric post-intubation sedation is 2.5 mg.",
            "source": "SNHD Protocols - Post-Intubation Midazolam",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "What is the correct concentration and dose of Epinephrine used for IV/IO administration in pediatric bradycardia or cardiac arrest?",
            "options": [
                "1:10,000, 0.01 mg/kg",
                "1:1000, 0.01 mg/kg",
                "1:10,000, 0.1 mg/kg",
                "1:1000, 0.1 mg/kg",
            ],
            "correct_answer": 0,
            "explanation": "IV/IO epinephrine: 1:10,000 concentration at 0.01 mg/kg (0.1 ml/kg).",
            "source": "SNHD Protocols - Epi IV/IO",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "What is the recommended dose of Ipratropium (0.02%) for a pediatric patient over 2 years old with wheezing?",
            "options": ["2.5 ml", "5 ml", "0.5 mg", "3.0 ml"],
            "correct_answer": 0,
            "explanation": "Ipratropium 0.02% for pediatrics >2 years: 2.5 ml via SVN.",
            "source": "SNHD Protocols - Ipratropium",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Which medication is noted as 'not recommended' for children in the treatment of pediatric abdominal pain?",
            "options": ["Ondansetron", "Morphine", "Fentanyl", "Acetaminophen"],
            "correct_answer": 1,
            "explanation": "Morphine is specifically noted as NOT recommended for children with abdominal pain.",
            "source": "SNHD Protocols - Abdominal Pain Meds",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Assessment",
            "question": "According to the General Pediatric Assessment pearls, what is the standard initial fluid bolus for a pediatric patient in Clark County?",
            "options": ["20 ml/kg", "50 ml/kg", "30 ml/kg", "10 ml/kg"],
            "correct_answer": 0,
            "explanation": "Standard initial pediatric fluid bolus in Clark County protocols is 20 ml/kg.",
            "source": "SNHD Protocols - Assessment Pearls",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "For a pediatric patient with suspected hypoglycemia who weighs less than 20 kg, what is the correct dosage of Glucagon (IM)?",
            "options": ["0.5 mg", "2 mg", "1 mg", "0.1 mg/kg"],
            "correct_answer": 0,
            "explanation": "Glucagon for pediatrics <20 kg: 0.5 mg IM (if no IV access).",
            "source": "SNHD Protocols - Glucagon <20kg",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "What is the maximum total volume of fluid boluses a pediatric patient can receive under general assessment pearls?",
            "options": ["20 ml/kg", "100 ml/kg", "40 ml/kg", "60 ml/kg"],
            "correct_answer": 2,
            "explanation": "Maximum total fluid boluses under general assessment pearls: 40 ml/kg.",
            "source": "SNHD Protocols - Max Fluids",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "In a pediatric patient suspected of having Diabetic Ketoacidosis (DKA), what is the maximum fluid bolus limit specified?",
            "options": [
                "Do not exceed 10 ml/kg",
                "No limit is specified for DKA",
                "Do not exceed 20 ml/kg",
                "Do not exceed 60 ml/kg",
            ],
            "correct_answer": 0,
            "explanation": "DKA maximum fluid bolus: Do not exceed 10 ml/kg due to cerebral edema risk.",
            "source": "SNHD Protocols - DKA Max",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "When managing a pediatric allergic reaction, what is the maximum single dose of Epinephrine 1:1000 given via the IM route?",
            "options": ["1.0 mg", "0.3 mg", "1.5 mg", "0.5 mg"],
            "correct_answer": 1,
            "explanation": "Maximum single IM dose of Epinephrine 1:1000 for pediatric allergic reaction is 0.3 mg.",
            "source": "SNHD Protocols - Epi IM Max",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Assessment",
            "question": "At what blood glucose level is a newborn considered hypoglycemic according to the Pediatric Altered Mental Status protocol?",
            "options": ["<70 mg/dl", "<40 mg/dl", "<20 mg/dl", "<60 mg/dl"],
            "correct_answer": 1,
            "explanation": "Newborn hypoglycemia threshold: <40 mg/dl.",
            "source": "SNHD Protocols - Newborn Hypoglycemia",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "What is the maximum single dose of D10 permitted for a pediatric patient?",
            "options": ["25 g", "50 g", "10 g", "15 g"],
            "correct_answer": 0,
            "explanation": "Maximum single dose of D10 for pediatric hypoglycemia is 25 grams.",
            "source": "SNHD Protocols - D10 Max Single",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Assessment",
            "question": "Which sign is specifically used to identify the onset of puberty in a female patient to determine if adult protocols should be used?",
            "options": [
                "First menstrual cycle",
                "Height over 5 feet",
                "Age over 12 years",
                "Any breast development",
            ],
            "correct_answer": 3,
            "explanation": "Any breast development indicates onset of puberty in females - may use adult protocols.",
            "source": "SNHD Protocols - Puberty Assessment",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "What is the maximum dose of Diphenhydramine for a pediatric patient experiencing an allergic reaction?",
            "options": ["100 mg", "25 mg", "75 mg", "50 mg"],
            "correct_answer": 3,
            "explanation": "Maximum diphenhydramine dose for pediatric allergic reaction is 50 mg.",
            "source": "SNHD Protocols - Diphenhydramine Max",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Equipment",
            "question": "What is the appropriate size BVM for a pediatric patient weighing 25 kg?",
            "options": ["Infant BVM", "Pediatric BVM", "Neonatal BVM", "Adult BVM"],
            "correct_answer": 1,
            "explanation": "Pediatric BVM is appropriate for patients approximately 10-40 kg (child size).",
            "source": "SNHD Protocols - BVM Sizing",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "When using Ondansetron ODT to a child, how should the provider handle rounding the dose?",
            "options": [
                "Round up to the nearest 1/2 pill",
                "Round down to the nearest whole pill",
                "Do not round, administer exact weight-based dose",
                "Round to the nearest 1/4 pill",
            ],
            "correct_answer": 1,
            "explanation": "Round down to nearest whole pill to avoid overdose.",
            "source": "SNHD Protocols - Ondansetron Rounding",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Equipment",
            "question": "What is the weight range for using a Pediatric BVM according to the Cardiac Arrest pearls?",
            "options": ["Under 10 kg", "10 to 40 kg", "5 to 30 kg", "5 to 20 kg"],
            "correct_answer": 1,
            "explanation": "Pediatric BVM is for patients approximately 10-40 kg.",
            "source": "SNHD Protocols - Pediatric BVM Range",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Which medication is NOT recommended for use in children for behavioral emergencies in Clark County?",
            "options": ["Naloxone", "Albuterol", "Midazolam", "Diphenhydramine"],
            "correct_answer": 2,
            "explanation": "Midazolam is NOT recommended for pediatric behavioral emergencies per Clark County protocols.",
            "source": "SNHD Protocols - Behavioral Meds",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "What is the recommended dose of Levalbuterol for a pediatric patient via SVN?",
            "options": ["0.63 mg", "2.5 mg", "1.25 mg", "5.0 mg"],
            "correct_answer": 2,
            "explanation": "Levalbuterol pediatric dose: 1.25 mg via SVN.",
            "source": "SNHD Protocols - Levalbuterol",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Which of these is a strict 'never' rule regarding Epinephrine administration for allergic reactions?",
            "options": [
                "Never use an auto-injector on a child",
                "Never give Epinephrine to a child under 5 kg",
                "Never give Epinephrine 1:1000 (IM concentration) through IV/IO route",
                "Never repeat Epinephrine more than once",
            ],
            "correct_answer": 2,
            "explanation": "NEVER give Epinephrine 1:1000 (IM concentration) via IV/IO - must use 1:10,000 for IV/IO.",
            "source": "SNHD Protocols - Epi Safety",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "For a pediatric patient in shock, what is the goal systolic blood pressure (SBP) when titrating push-dose epinephrine or fluids?",
            "options": ["60+Age", "70+2×Age", "Always 100 mm Hg", "90+2×Age"],
            "correct_answer": 1,
            "explanation": "Goal SBP for pediatric shock: 70 + (2 × Age in years).",
            "source": "SNHD Protocols - SBP Goal",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Assessment",
            "question": "When managing pediatric epistaxis, what is the first step according to the assessment flow?",
            "options": [
                "General Pediatric Assessment",
                "Administer Oxymetazoline",
                "Apply an ice pack to the bridge of the nose",
                "Direct pressure for 15 minutes",
            ],
            "correct_answer": 0,
            "explanation": "First step in pediatric epistaxis is General Pediatric Assessment.",
            "source": "SNHD Protocols - Epistaxis",
        },
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Equipment",
            "question": "What is the weight threshold for switching from an Infant BVM to a Pediatric BVM?",
            "options": ["5 kg", "3 kg", "10 kg", "15 kg"],
            "correct_answer": 0,
            "explanation": "Switch from Infant to Pediatric BVM at approximately 5 kg.",
            "source": "SNHD Protocols - BVM Switch",
        },
    ]

    for q in sample_questions:
        if not Question.query.filter_by(question=q["question"]).first():
            question = Question(
                level=q.get("level", "EMT"),
                category=q.get("category", "General"),
                subcategory=q.get("subcategory", ""),
                question=q["question"],
                options=json.dumps(q["options"]),
                correct_answer=q["correct_answer"],
                explanation=q["explanation"],
                source=q["source"],
            )
            db.session.add(question)

    db.session.commit()


# ==================== ADMIN ROUTES ====================


@app.route("/admin")
def admin_dashboard():
    """Admin dashboard to manage questions"""
    questions = Question.query.order_by(Question.category, Question.level).all()
    categories = db.session.query(Question.category).distinct().all()
    categories = [c[0] for c in categories]
    return render_template("admin.html", questions=questions, categories=categories)


@app.route("/admin/question/new", methods=["POST"])
def admin_create_question():
    """Create a new question"""
    try:
        question = Question(
            level=request.form["level"],
            category=request.form["category"],
            subcategory=request.form.get("subcategory", ""),
            question=request.form["question"],
            options=json.dumps(
                [
                    request.form["option_0"],
                    request.form["option_1"],
                    request.form["option_2"],
                    request.form["option_3"],
                ]
            ),
            correct_answer=int(request.form["correct_answer"]),
            explanation=request.form["explanation"],
            source=request.form.get("source", ""),
            # Mnemonic fields
            mnemonic_enabled=request.form.get("mnemonic_enabled") == "on",
            mnemonic_acronym=request.form.get("mnemonic_acronym", ""),
            mnemonic_expansion=request.form.get("mnemonic_expansion", ""),
            mnemonic_teaching_context=request.form.get("mnemonic_teaching_context", ""),
        )
        db.session.add(question)
        db.session.commit()
        return jsonify({"success": True, "message": "Question created successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/admin/question/<int:question_id>/edit", methods=["POST"])
def admin_update_question(question_id):
    """Update an existing question"""
    try:
        question = Question.query.get_or_404(question_id)
        question.level = request.form["level"]
        question.category = request.form["category"]
        question.subcategory = request.form.get("subcategory", "")
        question.question = request.form["question"]
        question.options = json.dumps(
            [
                request.form["option_0"],
                request.form["option_1"],
                request.form["option_2"],
                request.form["option_3"],
            ]
        )
        question.correct_answer = int(request.form["correct_answer"])
        question.explanation = request.form["explanation"]
        question.source = request.form.get("source", "")
        # Mnemonic fields
        question.mnemonic_enabled = request.form.get("mnemonic_enabled") == "on"
        question.mnemonic_acronym = request.form.get("mnemonic_acronym", "")
        question.mnemonic_expansion = request.form.get("mnemonic_expansion", "")
        question.mnemonic_teaching_context = request.form.get("mnemonic_teaching_context", "")
        db.session.commit()
        return jsonify({"success": True, "message": "Question updated successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/admin/question/<int:question_id>/delete", methods=["POST"])
def admin_delete_question(question_id):
    """Delete a question"""
    try:
        question = Question.query.get_or_404(question_id)
        db.session.delete(question)
        db.session.commit()
        return jsonify({"success": True, "message": "Question deleted successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/admin/question/<int:question_id>/json")
def admin_get_question_json(question_id):
    """Get question data as JSON for editing"""
    question = Question.query.get_or_404(question_id)
    return jsonify(
        {
            "id": question.id,
            "level": question.level,
            "category": question.category,
            "subcategory": question.subcategory,
            "question": question.question,
            "options": question.get_options(),
            "correct_answer": question.correct_answer,
            "explanation": question.explanation,
            "source": question.source,
            "mnemonic": {
                "enabled": question.mnemonic_enabled,
                "acronym": question.mnemonic_acronym,
                "expansion": question.mnemonic_expansion,
                "teaching_context": question.mnemonic_teaching_context,
            },
        }
    )


@app.route("/admin/categories")
def admin_get_categories():
    """Get all unique categories"""
    categories = db.session.query(Question.category).distinct().all()
    return jsonify([c[0] for c in categories])


@app.route("/admin/stats")
def admin_stats():
    """Get admin statistics"""
    total_questions = Question.query.count()
    by_level = {
        "EMT": Question.query.filter_by(level="EMT").count(),
        "AEMT": Question.query.filter_by(level="AEMT").count(),
        "PARAMEDIC": Question.query.filter_by(level="PARAMEDIC").count(),
    }
    by_category = {}
    for cat in db.session.query(Question.category).distinct():
        by_category[cat[0]] = Question.query.filter_by(category=cat[0]).count()

    return jsonify(
        {"total_questions": total_questions, "by_level": by_level, "by_category": by_category}
    )


# ==================== BULK IMPORT/EXPORT ROUTES ====================


@app.route("/admin/export/json")
@admin_required
def admin_export_json():
    """Export all questions to JSON"""
    import json

    from flask import Response

    questions = Question.query.all()
    export_data = []
    for q in questions:
        export_data.append(
            {
                "id": q.id,
                "level": q.level,
                "category": q.category,
                "subcategory": q.subcategory,
                "question": q.question,
                "options": q.get_options(),
                "correct_answer": q.correct_answer,
                "explanation": q.explanation,
                "source": q.source,
                "mnemonic_enabled": q.mnemonic_enabled,
                "mnemonic_acronym": q.mnemonic_acronym,
                "mnemonic_expansion": q.mnemonic_expansion,
                "mnemonic_teaching_context": q.mnemonic_teaching_context,
            }
        )

    response = Response(
        json.dumps(export_data, indent=2),
        mimetype="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="ems_questions.json"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )
    return response


@app.route("/admin/export/csv")
@admin_required
def admin_export_csv():
    """Export all questions to CSV"""
    import csv
    import io

    from flask import Response

    questions = Question.query.all()
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(
        [
            "id",
            "level",
            "category",
            "subcategory",
            "question",
            "option_0",
            "option_1",
            "option_2",
            "option_3",
            "correct_answer",
            "explanation",
            "source",
            "mnemonic_enabled",
            "mnemonic_acronym",
            "mnemonic_expansion",
            "mnemonic_teaching_context",
        ]
    )

    # Data
    for q in questions:
        options = q.get_options()
        writer.writerow(
            [
                q.id,
                q.level,
                q.category,
                q.subcategory,
                q.question,
                options[0],
                options[1],
                options[2],
                options[3],
                q.correct_answer,
                q.explanation,
                q.source,
                q.mnemonic_enabled,
                q.mnemonic_acronym,
                q.mnemonic_expansion,
                q.mnemonic_teaching_context,
            ]
        )

    output.seek(0)

    response = Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="ems_questions.csv"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
    return response


@app.route("/admin/import/json", methods=["POST"])
@admin_required
def admin_import_json():
    """Import questions from JSON"""
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "No file selected"}), 400

        data = json.load(file)
        imported = 0
        updated = 0
        errors = []

        for item in data:
            try:
                # Validate required fields
                required = ["question", "options", "correct_answer", "explanation"]
                for field in required:
                    if field not in item:
                        errors.append(
                            f"Missing field '{field}' in question: {item.get('question', 'unknown')}"
                        )
                        continue

                # Check if question exists (by ID or by question text)
                existing = None
                if "id" in item and item["id"]:
                    existing = Question.query.get(item["id"])
                if not existing:
                    existing = Question.query.filter_by(question=item["question"]).first()

                if existing:
                    # Update existing
                    existing.level = item.get("level", "EMT")
                    existing.category = item.get("category", "General")
                    existing.subcategory = item.get("subcategory", "")
                    existing.options = json.dumps(item["options"])
                    existing.correct_answer = int(item["correct_answer"])
                    existing.explanation = item["explanation"]
                    existing.source = item.get("source", "")
                    # Mnemonic fields (optional, safe to omit)
                    existing.mnemonic_enabled = item.get("mnemonic_enabled", False)
                    existing.mnemonic_acronym = item.get("mnemonic_acronym", "")
                    existing.mnemonic_expansion = item.get("mnemonic_expansion", "")
                    existing.mnemonic_teaching_context = item.get("mnemonic_teaching_context", "")
                    updated += 1
                else:
                    # Create new
                    q = Question(
                        level=item.get("level", "EMT"),
                        category=item.get("category", "General"),
                        subcategory=item.get("subcategory", ""),
                        question=item["question"],
                        options=json.dumps(item["options"]),
                        correct_answer=int(item["correct_answer"]),
                        explanation=item["explanation"],
                        source=item.get("source", ""),
                        # Mnemonic fields (optional, safe to omit)
                        mnemonic_enabled=item.get("mnemonic_enabled", False),
                        mnemonic_acronym=item.get("mnemonic_acronym", ""),
                        mnemonic_expansion=item.get("mnemonic_expansion", ""),
                        mnemonic_teaching_context=item.get("mnemonic_teaching_context", ""),
                    )
                    db.session.add(q)
                    imported += 1

            except Exception as e:
                errors.append(f"Error processing question: {str(e)}")

        db.session.commit()

        return jsonify(
            {"success": True, "imported": imported, "updated": updated, "errors": errors}
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/admin/import/csv", methods=["POST"])
@admin_required
def admin_import_csv():
    """Import questions from CSV"""
    try:
        import csv
        import io

        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "No file selected"}), 400

        stream = io.StringIO(file.stream.read().decode("UTF-8"))
        reader = csv.DictReader(stream)

        imported = 0
        updated = 0
        errors = []

        for row in reader:
            try:
                # Build options list
                options = [
                    row.get("option_0", ""),
                    row.get("option_1", ""),
                    row.get("option_2", ""),
                    row.get("option_3", ""),
                ]

                # Validate
                if not row.get("question"):
                    errors.append("Missing question text")
                    continue

                # Check if exists
                existing = None
                if row.get("id"):
                    existing = Question.query.get(int(row["id"]))
                if not existing:
                    existing = Question.query.filter_by(question=row["question"]).first()

                if existing:
                    # Update
                    existing.level = row.get("level", "EMT")
                    existing.category = row.get("category", "General")
                    existing.subcategory = row.get("subcategory", "")
                    existing.options = json.dumps(options)
                    existing.correct_answer = int(row.get("correct_answer", 0))
                    existing.explanation = row.get("explanation", "")
                    existing.source = row.get("source", "")
                    # Mnemonic fields (optional, safe to omit)
                    existing.mnemonic_enabled = row.get("mnemonic_enabled", "").lower() in [
                        "true",
                        "1",
                        "yes",
                        "on",
                    ]
                    existing.mnemonic_acronym = row.get("mnemonic_acronym", "")
                    existing.mnemonic_expansion = row.get("mnemonic_expansion", "")
                    existing.mnemonic_teaching_context = row.get("mnemonic_teaching_context", "")
                    updated += 1
                else:
                    # Create new
                    q = Question(
                        level=row.get("level", "EMT"),
                        category=row.get("category", "General"),
                        subcategory=row.get("subcategory", ""),
                        question=row["question"],
                        options=json.dumps(options),
                        correct_answer=int(row.get("correct_answer", 0)),
                        explanation=row.get("explanation", ""),
                        source=row.get("source", ""),
                        # Mnemonic fields (optional, safe to omit)
                        mnemonic_enabled=row.get("mnemonic_enabled", "").lower()
                        in ["true", "1", "yes", "on"],
                        mnemonic_acronym=row.get("mnemonic_acronym", ""),
                        mnemonic_expansion=row.get("mnemonic_expansion", ""),
                        mnemonic_teaching_context=row.get("mnemonic_teaching_context", ""),
                    )
                    db.session.add(q)
                    imported += 1

            except Exception as e:
                errors.append(f"Error processing row: {str(e)}")

        db.session.commit()

        return jsonify(
            {"success": True, "imported": imported, "updated": updated, "errors": errors}
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/init-db")
def init_db():
    """Initialize database tables (for PostgreSQL setup)"""
    try:
        with app.app_context():
            db.create_all()
            count = Question.query.count()
            return jsonify(
                {
                    "success": True,
                    "message": "Database tables created successfully",
                    "questions_count": count,
                    "note": "If questions_count is 0, you need to import questions via admin panel",
                }
            )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/cleanup-db")
@admin_required
def cleanup_db():
    """Remove all sample questions, keep only imported SNHD Protocol questions"""
    try:
        with app.app_context():
            from sqlalchemy import not_, or_

            # Count before deletion
            total_before = Question.query.count()
            answers_before = Answer.query.count()

            # Find questions to keep (exact source match)
            keep_query = Question.query.filter(
                or_(
                    Question.source == "SNHD Protocols",
                    Question.source == "SNHD Protocols - Quizlet",
                )
            )
            keep_ids = [q.id for q in keep_query.all()]

            # Find questions to delete (everything else)
            if keep_ids:
                delete_query = Question.query.filter(not_(Question.id.in_(keep_ids)))
            else:
                delete_query = Question.query

            # Get IDs of questions to delete
            delete_ids = [q.id for q in delete_query.all()]

            # Step 1: Delete all answers that reference questions we're deleting
            if delete_ids:
                Answer.query.filter(Answer.question_id.in_(delete_ids)).delete(
                    synchronize_session=False
                )
                db.session.commit()

            # Step 2: Delete the questions
            if delete_ids:
                delete_query.delete(synchronize_session=False)
                db.session.commit()

            # Count after deletion
            total_after = Question.query.count()
            answers_after = Answer.query.count()

            return jsonify(
                {
                    "success": True,
                    "message": "Database cleanup completed",
                    "deleted_questions": total_before - total_after,
                    "deleted_answers": answers_before - answers_after,
                    "remaining_questions": total_after,
                    "remaining_answers": answers_after,
                    "kept_ids": keep_ids[:10],  # Show first 10 for debugging
                    "note": "Kept only SNHD Protocols and SNHD Protocols - Quizlet questions",
                }
            )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== MNEMONIC HINT API ====================


@app.route("/api/question/<int:question_id>/hint", methods=["POST"])
def reveal_hint(question_id):
    """
    Reveal mnemonic hint for a question.
    Tracks analytics: user_id, question_id, timestamp
    """
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Not authenticated"}), 401

    question = Question.query.get_or_404(question_id)

    # Check if mnemonic is enabled for this question
    if not question.mnemonic_enabled or not question.mnemonic_acronym:
        return jsonify({"success": False, "error": "No hint available for this question"}), 404

    # TODO: Track hint usage in analytics table (Phase 5)
    # For now, just return the acronym

    return jsonify({"success": True, "hint": {"acronym": question.mnemonic_acronym}})


@app.route("/api/question/<int:question_id>/mnemonic", methods=["GET"])
def get_full_mnemonic(question_id):
    """
    Get full mnemonic expansion (for teaching moment after wrong answer).
    Returns full expansion + teaching context.
    """
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Not authenticated"}), 401

    question = Question.query.get_or_404(question_id)

    if not question.mnemonic_enabled:
        return jsonify({"success": False, "error": "No mnemonic available"}), 404

    return jsonify(
        {
            "success": True,
            "mnemonic": {
                "acronym": question.mnemonic_acronym,
                "expansion": question.mnemonic_expansion,
                "teaching_context": question.mnemonic_teaching_context,
            },
        }
    )


@app.route("/api/questions/with-mnemonics", methods=["GET"])
@admin_required
def list_questions_with_mnemonics():
    """Admin: List all questions with their mnemonic data"""
    questions = Question.query.all()
    return jsonify({"success": True, "questions": [q.to_dict_with_mnemonic() for q in questions]})


# ==================== MAIN ====================

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        if Question.query.count() == 0:
            init_sample_questions()
    app.run(debug=True, host="0.0.0.0", port=5001)

# Ensure DB is initialized on Vercel import
if os.environ.get("VERCEL"):
    with app.app_context():
        db.create_all()
        if Question.query.count() == 0:
            init_sample_questions()
