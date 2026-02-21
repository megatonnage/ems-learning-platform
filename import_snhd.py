#!/usr/bin/env python3
"""
SNHD Protocol Import Script
Extracts content from SNHD protocols and generates questions
"""

import json
import re

from app import Question, db


def parse_protocol_text(text_content):
    """Parse SNHD protocol text and extract key information"""

    # Patterns to look for
    patterns = {
        "boluses": r"(?i)(fluid bolus|bolus|iv fluids?)(?:.*?)(\d+\s*mL|\d+\s*mL/kg)",
        "medications": r"(?i)(?:dose|give|administer)(?:.*?)(\d+(?:\.\d+)?\s*(?:mg|mcg|g|units?))",
        "contraindications": r"(?i)(contraindicated?|do not give|avoid)(.*?)(?:\.|\n)",
        "indications": r"(?i)(indicated|give for|treat)(.*?)(?:with|:)",
    }

    extracted = {}
    for key, pattern in patterns.items():
        matches = re.findall(pattern, text_content, re.DOTALL)
        extracted[key] = matches

    return extracted


def generate_questions_from_protocols():
    """Generate additional questions based on SNHD protocol patterns"""

    additional_questions = [
        # PEDIATRIC FLUIDS - More specific scenarios
        {
            "level": "EMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "A 3-year-old (14 kg) with gastroenteritis and signs of moderate dehydration should receive:",
            "options": [
                "No fluids - PO only",
                "280 mL bolus (20 mL/kg)",
                "500 mL bolus",
                "1000 mL bolus",
            ],
            "correct_answer": 1,
            "explanation": "14 kg × 20 mL/kg = 280 mL. Moderate dehydration with shock signs gets bolus; mild gets PO.",
            "source": "SNHD Protocols - Pediatric Dehydration",
        },
        {
            "level": "AEMT",
            "category": "Pediatric",
            "subcategory": "Fluid Boluses",
            "question": "After 2 fluid boluses, a pediatric patient remains hypotensive. Next step is:",
            "options": [
                "Give 3rd bolus immediately",
                "Reassess and consider dopamine/epinephrine infusion",
                "Transport without further fluids",
                "Give blood products",
            ],
            "correct_answer": 1,
            "explanation": "After 40 mL/kg, if still unstable, reassess and consider vasoactive medications per protocol.",
            "source": "SNHD Protocols - Pediatric Refractory Shock",
        },
        # PEDIATRIC MEDS - Advanced scenarios
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "For pediatric status epilepticus, if benzodiazepines fail, next medication is:",
            "options": [
                "More benzodiazepines",
                "Levetiracetam (Keppra) or phenobarbital",
                "Haloperidol",
                "Diphenhydramine",
            ],
            "correct_answer": 1,
            "explanation": "Refractory status epilepticus requires second-line agents like levetiracetam or phenobarbital.",
            "source": "SNHD Protocols - Pediatric Status Epilepticus",
        },
        {
            "level": "PARAMEDIC",
            "category": "Pediatric",
            "subcategory": "Medications",
            "question": "Pediatric ketamine for RSI dosing and benefits:",
            "options": [
                "1 mg/kg - causes hypotension",
                "2 mg/kg - maintains BP, good for shock",
                "0.5 mg/kg - short acting",
                "5 mg/kg - deep sedation",
            ],
            "correct_answer": 1,
            "explanation": "Ketamine 2 mg/kg is preferred for RSI in pediatrics - maintains BP and sympathetic tone.",
            "source": "SNHD Protocols - Pediatric RSI",
        },
        # SNHD SPECIFIC - Waiting room & transport
        {
            "level": "EMT",
            "category": "Transport Criteria",
            "subcategory": "SNHD Specific",
            "question": 'Per SNHD protocols, a patient meets "forward content" criteria if:',
            "options": [
                "They request a specific hospital",
                "They need specialized care not at nearest facility",
                "They have minor complaints",
                "They refuse transport",
            ],
            "correct_answer": 1,
            "explanation": "Forward content/redirect applies when patient needs specialty care (PCI, trauma, pediatrics) not available at nearest facility.",
            "source": "SNHD Protocols - Hospital Selection",
        },
        {
            "level": "EMT",
            "category": "Transport Criteria",
            "subcategory": "SNHD Specific",
            "question": "SNHD trauma destination for pediatric patients <15 years with major trauma:",
            "options": [
                "Nearest adult trauma center",
                "Pediatric-capable trauma center if available within reasonable distance",
                "Any hospital with pediatric unit",
                "Urgent care",
            ],
            "correct_answer": 1,
            "explanation": "Pediatric trauma patients should go to pediatric-capable trauma centers when available and appropriate.",
            "source": "SNHD Protocols - Pediatric Trauma Destination",
        },
        # INTOXICATION/AMS - SNHD specific
        {
            "level": "EMT",
            "category": "Transport Criteria",
            "subcategory": "Intoxication",
            "question": "Per SNHD, an intoxicated patient may be appropriate for alternate destination (Crisis Response Center) if:",
            "options": [
                "Any intoxicated patient",
                "GCS 14-15, stable vitals, no trauma, medically cleared",
                "GCS <13",
                "Combative and violent",
            ],
            "correct_answer": 1,
            "explanation": "SNHD allows alternate destination for stable intoxicated patients (GCS 14-15, no trauma) to Crisis Response Center.",
            "source": "SNHD Protocols - Alternate Destination",
        },
        # TFTC & TRAUMA
        {
            "level": "EMT",
            "category": "Trauma",
            "subcategory": "TFTC",
            "question": "SNHD TFTC (Trauma Field Transport Criteria) includes all EXCEPT:",
            "options": ["GCS <14", "SBP <90", "HR >120", "SpO2 >95% on room air"],
            "correct_answer": 3,
            "explanation": "Normal SpO2 is NOT TFTC criteria. TFTC includes GCS<14, SBP<90, RR<10 or >29, penetrating injuries to head/torso, etc.",
            "source": "SNHD Protocols - TFTC Criteria",
        },
        {
            "level": "EMT",
            "category": "Trauma",
            "subcategory": "TFTC",
            "question": "A patient falls 25 feet from a ladder. According to SNHD trauma criteria:",
            "options": [
                "Transport to nearest ED",
                "Meets TFTC - transport to trauma center",
                "Only if they have injuries",
                "BLS transport OK",
            ],
            "correct_answer": 1,
            "explanation": "Falls >20 feet for adults automatically meet trauma center criteria per SNHD.",
            "source": "SNHD Protocols - Mechanism Criteria",
        },
        # HOSPITAL CATCHMENTS
        {
            "level": "EMT",
            "category": "Transport",
            "subcategory": "Hospital Selection",
            "question": "A patient with suspected stroke (last known well 2 hours ago) should go to:",
            "options": [
                "Nearest ED",
                "Primary Stroke Center or Comprehensive Stroke Center",
                "Urgent care",
                "Rehab facility",
            ],
            "correct_answer": 1,
            "explanation": "Stroke patients need facilities with CT capability and stroke protocols - Primary or Comprehensive Stroke Center.",
            "source": "SNHD Protocols - Stroke Destination",
        },
        {
            "level": "EMT",
            "category": "Transport",
            "subcategory": "Hospital Selection",
            "question": "For STEMI with symptom onset 30 minutes ago, transport time to PCI center is 45 minutes vs 10 minutes to non-PCI hospital. Best destination:",
            "options": [
                "Non-PCI hospital (closer)",
                "PCI-capable facility despite longer transport",
                "Either is fine",
                "Urgent care",
            ],
            "correct_answer": 1,
            "explanation": "STEMI patients benefit from direct transport to PCI-capable facilities even with longer transport times (door-to-balloon time critical).",
            "source": "SNHD Protocols - STEMI Destination",
        },
    ]

    return additional_questions


def import_to_database():
    """Import all generated questions to database"""
    questions = generate_questions_from_protocols()

    added = 0
    for q in questions:
        # Check if question already exists
        existing = Question.query.filter_by(question=q["question"]).first()
        if not existing:
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
            added += 1

    db.session.commit()
    print(f"Added {added} new questions from SNHD protocols")


if __name__ == "__main__":
    import_to_database()
