#!/usr/bin/env python3
"""
Generate protocol links for existing questions by semantic matching.
Maps question categories/subcategories to SNHD protocol sections.
"""

import os
import sys
import re
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db, Question

# Protocol section mapping
# Maps category keywords to protocol anchors
PROTOCOL_SECTIONS = {
    # Adult protocols
    "cardiac arrest": "cardiac-arrest-non-traumatic",
    "cpr": "cardiac-arrest-non-traumatic",
    "chest pain": "chest-pain-non-traumatic-and-suspected-acute-coronary-syndrome",
    "acs": "chest-pain-non-traumatic-and-suspected-acute-coronary-syndrome",
    "mi": "chest-pain-non-traumatic-and-suspected-acute-coronary-syndrome",
    "stemi": "stemi-suspected",
    "stroke": "stroke-cva",
    "cva": "stroke-cva",
    "seizure": "seizure",
    "respiratory": "respiratory-distress",
    "breathing": "respiratory-distress",
    "asthma": "respiratory-distress",
    "copd": "respiratory-distress",
    "shock": "shock",
    "allergic": "allergic-reaction",
    "anaphylaxis": "allergic-reaction",
    "behavioral": "behavioral-emergencies",
    "psych": "behavioral-emergencies",
    "mental": "behavioral-emergencies",
    "diabetic": "altered-mental-status-syncope",
    "hypoglycemia": "altered-mental-status-syncope",
    "ams": "altered-mental-status-syncope",
    "syncope": "altered-mental-status-syncope",
    "overdose": "overdose-poisoning",
    "poisoning": "overdose-poisoning",
    "pain": "pain-management",
    "burn": "burns",
    "trauma": "general-adult-trauma-assessment",
    "bleeding": "hemorrhage-control",
    "hemorrhage": "hemorrhage-control",
    "ob": "ob-obstetric-emergency",
    "obstetric": "ob-obstetric-emergency",
    "labor": "ob-uncomplicated-childbirth-labor",
    "delivery": "ob-uncomplicated-childbirth-labor",
    "preeclampsia": "ob-preeclampsia-eclampsia",
    "eclampsia": "ob-preeclampsia-eclampsia",
    "sepsis": "sepsis",
    "bradycardia": "bradycardia",
    "tachycardia": "tachycardia-stable",
    "hyperkalemia": "hyperkalemia-suspected",
    "heat": "heat-related-illness",
    "cold": "cold-related-illness",
    "hypothermia": "cold-related-illness",
    "smoke": "smoke-inhalation",
    "inhalation": "smoke-inhalation",
    "abdominal": "abdominal-pain-flank-pain-nausea-vomiting",
    "nausea": "abdominal-pain-flank-pain-nausea-vomiting",
    "vomiting": "abdominal-pain-flank-pain-nausea-vomiting",
    "chf": "pulmonary-edema-chf",
    "pulmonary edema": "pulmonary-edema-chf",
    "epistaxis": "epistaxis",
    "nosebleed": "epistaxis",
    # Pediatric protocols
    "pediatric arrest": "pediatric-cardiac-arrest-non-traumatic",
    "peds arrest": "pediatric-cardiac-arrest-non-traumatic",
    "pediatric respiratory": "pediatric-respiratory-distress",
    "peds respiratory": "pediatric-respiratory-distress",
    "pediatric shock": "pediatric-shock",
    "peds shock": "pediatric-shock",
    "pediatric seizure": "pediatric-seizure",
    "peds seizure": "pediatric-seizure",
    "neonatal": "neonatal-resuscitation",
    "newborn": "neonatal-resuscitation",
    # Procedures
    "intubation": "endotracheal-intubation",
    "airway": "endotracheal-intubation",
    "cricothyroidotomy": "needle-cricothyroidotomy",
    "surgical airway": "needle-cricothyroidotomy",
    "chest decompression": "needle-thoracostomy",
    "needle decompression": "needle-thoracostomy",
    "thoracostomy": "needle-thoracostomy",
    "pneumothorax": "needle-thoracostomy",
    "io": "vascular-access",
    "iv": "vascular-access",
    "vascular access": "vascular-access",
    "defibrillation": "electrical-therapy-defibrillation",
    "cardioversion": "electrical-therapy-synchronized-cardioversion",
    "pacing": "electrical-therapy-transcutaneous-pacing",
    "tcp": "electrical-therapy-transcutaneous-pacing",
}


def slugify(text):
    """Convert text to URL-friendly slug"""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')


def find_protocol_link(question):
    """Find best matching protocol link for a question"""
    # Combine question text for matching
    text = f"{question.category} {question.subcategory or ''} {question.question} {question.explanation or ''}".lower()

    # Try keyword matching
    for keyword, anchor in PROTOCOL_SECTIONS.items():
        if keyword in text:
            return f"snhd-protocols.md#{anchor}"

    # Fallback: try to match category directly
    category_slug = slugify(question.category)
    return f"snhd-protocols.md#{category_slug}"


def generate_links(dry_run=True):
    """Generate protocol links for all questions"""
    with app.app_context():
        questions = Question.query.all()

        print(f"Found {len(questions)} questions")
        print()

        updates = []

        for q in questions:
            if q.protocol_link:
                print(f"[SKIP] Q{q.id}: Already has link - {q.protocol_link}")
                continue

            link = find_protocol_link(q)

            print(f"[{'DRY-RUN' if dry_run else 'UPDATE'}] Q{q.id}: {q.category}")
            print(f"  Question: {q.question[:80]}...")
            print(f"  Link: {link}")
            print()

            if not dry_run:
                q.protocol_link = link
                updates.append(q)

        if not dry_run and updates:
            db.session.commit()
            print(f"✓ Updated {len(updates)} questions")
        elif dry_run:
            print(f"\nDry run complete. {len([q for q in questions if not q.protocol_link])} questions need links.")
            print("Run with --apply to update database")


def show_stats():
    """Show current link coverage statistics"""
    with app.app_context():
        total = Question.query.count()
        with_links = Question.query.filter(Question.protocol_link.isnot(None)).count()
        without = total - with_links

        print("Protocol Link Coverage")
        print("=" * 40)
        print(f"Total questions: {total}")
        print(f"With links: {with_links} ({with_links/total*100:.1f}%)")
        print(f"Without links: {without} ({without/total*100:.1f}%)")
        print()

        # Show by category
        from sqlalchemy import func

        categories = db.session.query(
            Question.category,
            func.count(Question.id).label('total'),
            func.sum((Question.protocol_link.isnot(None)).cast(db.Integer)).label('with_link')
        ).group_by(Question.category).all()

        print("By Category:")
        for cat, cat_total, cat_with in categories:
            pct = (cat_with or 0) / cat_total * 100
            print(f"  {cat}: {cat_with or 0}/{cat_total} ({pct:.0f}%)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate protocol links for EMS questions")
    parser.add_argument("--apply", action="store_true", help="Actually update database (default: dry run)")
    parser.add_argument("--stats", action="store_true", help="Show current statistics")

    args = parser.parse_args()

    if args.stats:
        show_stats()
    else:
        generate_links(dry_run=not args.apply)
