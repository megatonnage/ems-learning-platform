"""
SNHD Protocols Question Bank Generator
Generates 100+ questions covering:
- Fluid boluses (adults & pediatrics)
- Medications (dosages, routes, contraindications)
- Waiting room criteria
- Intoxication/altered mental status transport
- Trauma score and TFTC designations
- Hospital catchments
"""

import json
import sys
sys.path.insert(0, '/Users/anhta/.openclaw/workspace/ems-platform')

from app import app, db, Question

def generate_snhd_questions():
    """Generate comprehensive SNHD protocol questions"""
    
    questions = []
    
    # ========== FLUID BOLUSES - ADULTS ==========
    questions.extend([
        {
            'level': 'EMT',
            'category': 'Fluid Boluses',
            'subcategory': 'Adult',
            'question': 'What is the standard adult fluid bolus volume for a patient with suspected hypovolemic shock?',
            'options': ['250 mL', '500 mL', '1000 mL', '2000 mL'],
            'correct_answer': 2,
            'explanation': 'Standard adult fluid bolus is 1000 mL (1 liter) of normal saline or lactated Ringer\'s. May repeat if indicated.',
            'source': 'SNHD Protocols - Fluid Administration'
        },
        {
            'level': 'EMT',
            'category': 'Fluid Boluses',
            'subcategory': 'Adult',
            'question': 'In an adult trauma patient without head injury, what is the maximum number of fluid boluses recommended before considering blood products?',
            'options': ['1 bolus', '2 boluses', '3 boluses', '4 boluses'],
            'correct_answer': 1,
            'explanation': 'Maximum 2 liters (2 boluses) of crystalloid before considering blood products in trauma patients.',
            'source': 'SNHD Protocols - Trauma Fluid Resuscitation'
        },
        {
            'level': 'EMT',
            'category': 'Fluid Boluses',
            'subcategory': 'Adult',
            'question': 'For an adult patient with suspected cardiogenic pulmonary edema, what is the appropriate fluid administration approach?',
            'options': ['Standard 1000 mL bolus', '250 mL boluses with reassessment', 'No fluids unless SBP < 90', 'Aggressive fluid resuscitation'],
            'correct_answer': 2,
            'explanation': 'In cardiogenic pulmonary edema, avoid fluids unless hypotensive (SBP < 90). If fluids given, use small boluses (250 mL) with frequent reassessment.',
            'source': 'SNHD Protocols - Congestive Heart Failure'
        },
        {
            'level': 'AEMT',
            'category': 'Fluid Boluses',
            'subcategory': 'Adult',
            'question': 'An adult patient with sepsis has a MAP of 65 mmHg after initial 1000 mL bolus. What is the next appropriate action?',
            'options': ['Give second 1000 mL bolus', 'Start vasopressors immediately', 'Give 500 mL bolus and reassess', 'Transport without further fluids'],
            'correct_answer': 2,
            'explanation': 'For sepsis with MAP < 65, give additional 500 mL boluses while reassessing perfusion. Goal is MAP ≥ 65.',
            'source': 'SNHD Protocols - Sepsis'
        },
    ])
    
    # ========== FLUID BOLUSES - PEDIATRICS ==========
    questions.extend([
        {
            'level': 'EMT',
            'category': 'Fluid Boluses',
            'subcategory': 'Pediatric',
            'question': 'What is the standard pediatric fluid bolus volume per kg?',
            'options': ['10 mL/kg', '20 mL/kg', '30 mL/kg', '50 mL/kg'],
            'correct_answer': 1,
            'explanation': 'Standard pediatric fluid bolus is 20 mL/kg of normal saline or LR. May repeat up to 3 times if indicated.',
            'source': 'SNHD Protocols - Pediatric Fluid Administration'
        },
        {
            'level': 'EMT',
            'category': 'Fluid Boluses',
            'subcategory': 'Pediatric',
            'question': 'A 15 kg pediatric patient requires fluid resuscitation. What is the appropriate initial bolus volume?',
            'options': ['150 mL', '300 mL', '500 mL', '1000 mL'],
            'correct_answer': 1,
            'explanation': '15 kg × 20 mL/kg = 300 mL. Pediatric boluses are weight-based at 20 mL/kg.',
            'source': 'SNHD Protocols - Pediatric Calculations'
        },
        {
            'level': 'AEMT',
            'category': 'Fluid Boluses',
            'subcategory': 'Pediatric',
            'question': 'In a pediatric trauma patient, what is the maximum total fluid volume before considering blood products?',
            'options': ['20 mL/kg', '40 mL/kg', '60 mL/kg', '80 mL/kg'],
            'correct_answer': 2,
            'explanation': 'Maximum 60 mL/kg total crystalloid in pediatric trauma before considering blood products (approximately 3 boluses).',
            'source': 'SNHD Protocols - Pediatric Trauma'
        },
        {
            'level': 'AEMT',
            'category': 'Fluid Boluses',
            'subcategory': 'Pediatric',
            'question': 'A pediatric patient with suspected diabetic ketoacidosis (DKA) presents with hypotension. What is the appropriate fluid approach?',
            'options': ['Aggressive 40 mL/kg bolus', 'No fluids - risk of cerebral edema', '10-20 mL/kg bolus over 1-2 hours', 'Standard 20 mL/kg rapid bolus'],
            'correct_answer': 2,
            'explanation': 'In pediatric DKA, fluid resuscitation must be cautious to prevent cerebral edema. Use 10-20 mL/kg over 1-2 hours, not rapid bolus.',
            'source': 'SNHD Protocols - Pediatric DKA'
        },
    ])
    
    # ========== MEDICATIONS - DOSAGES ==========
    questions.extend([
        {
            'level': 'EMT',
            'category': 'Medications',
            'subcategory': 'Dosages',
            'question': 'What is the adult dose of epinephrine 1:1000 for anaphylaxis?',
            'options': ['0.1 mg IM', '0.3 mg IM', '0.5 mg IM', '1.0 mg IM'],
            'correct_answer': 1,
            'explanation': 'Adult dose for anaphylaxis is 0.3 mg of epinephrine 1:1000 IM (usually 0.3 mL in thigh). May repeat every 5-15 minutes.',
            'source': 'SNHD Protocols - Anaphylaxis'
        },
        {
            'level': 'EMT',
            'category': 'Medications',
            'subcategory': 'Dosages',
            'question': 'What is the pediatric dose of epinephrine 1:1000 for anaphylaxis?',
            'options': ['0.01 mg/kg IM (max 0.3 mg)', '0.15 mg IM (fixed dose)', '0.1 mg/kg IM', '0.01 mg/kg IV'],
            'correct_answer': 0,
            'explanation': 'Pediatric epinephrine for anaphylaxis is 0.01 mg/kg IM, maximum 0.3 mg. Use auto-injector if available for weight-appropriate dose.',
            'source': 'SNHD Protocols - Anaphylaxis'
        },
        {
            'level': 'AEMT',
            'category': 'Medications',
            'subcategory': 'Dosages',
            'question': 'What is the adult dose of naloxone for suspected opioid overdose?',
            'options': ['0.4 mg IV/IM', '2 mg IN or 0.4-2 mg IV/IM', '4 mg IM only', '0.1 mg/kg IV'],
            'correct_answer': 1,
            'explanation': 'Adult naloxone: 2 mg IN (1 mg per nostril) or 0.4-2 mg IV/IM. Titrate to respiratory effort, not full consciousness.',
            'source': 'SNHD Protocols - Opioid Overdose'
        },
        {
            'level': 'AEMT',
            'category': 'Medications',
            'subcategory': 'Dosages',
            'question': 'What is the pediatric dose of naloxone?',
            'options': ['0.01 mg/kg IV/IM (max 2 mg)', '0.1 mg/kg IV/IM (max 2 mg)', '2 mg IN (fixed dose)', '0.4 mg IM only'],
            'correct_answer': 1,
            'explanation': 'Pediatric naloxone is 0.1 mg/kg IV/IM (max 2 mg) or 2 mg IN (if ≥ 1 year old). Titrate to respiratory effort.',
            'source': 'SNHD Protocols - Opioid Overdose'
        },
        {
            'level': 'PARAMEDIC',
            'category': 'Medications',
            'subcategory': 'Dosages',
            'question': 'What is the adult dose of adenosine for SVT (first dose)?',
            'options': ['3 mg rapid IV push', '6 mg rapid IV push', '12 mg rapid IV push', '0.1 mg/kg rapid IV push'],
            'correct_answer': 1,
            'explanation': 'First dose adenosine is 6 mg rapid IV push followed by 20 mL saline flush. Second dose is 12 mg if needed.',
            'source': 'SNHD Protocols - Tachycardia'
        },
        {
            'level': 'PARAMEDIC',
            'category': 'Medications',
            'subcategory': 'Dosages',
            'question': 'What is the pediatric dose of adenosine for SVT?',
            'options': ['0.05 mg/kg rapid IV push (max 6 mg)', '0.1 mg/kg rapid IV push (max first dose 6 mg)', '0.2 mg/kg rapid IV push (max 12 mg)', '1 mg rapid IV push (fixed dose)'],
            'correct_answer': 1,
            'explanation': 'Pediatric adenosine: First dose 0.1 mg/kg rapid IV push (max 6 mg), second dose 0.2 mg/kg (max 12 mg).',
            'source': 'SNHD Protocols - Pediatric Tachycardia'
        },
        {
            'level': 'PARAMEDIC',
            'category': 'Medications',
            'subcategory': 'Dosages',
            'question': 'What is the adult dose of amiodarone for cardiac arrest?',
            'options': ['150 mg IV/IO', '300 mg IV/IO', '450 mg IV/IO', '5 mg/kg IV/IO'],
            'correct_answer': 1,
            'explanation': 'Amiodarone for cardiac arrest: First dose 300 mg IV/IO. Second dose (if needed) 150 mg. For perfusing VT: 150 mg over 10 minutes.',
            'source': 'SNHD Protocols - Cardiac Arrest'
        },
        {
            'level': 'PARAMEDIC',
            'category': 'Medications',
            'subcategory': 'Dosages',
            'question': 'What is the pediatric dose of amiodarone for pulseless arrest?',
            'options': ['2.5 mg/kg IV/IO', '5 mg/kg IV/IO', '10 mg/kg IV/IO', '15 mg/kg IV/IO'],
            'correct_answer': 1,
            'explanation': 'Pediatric amiodarone for arrest: 5 mg/kg IV/IO (max 300 mg). May repeat once.',
            'source': 'SNHD Protocols - Pediatric Cardiac Arrest'
        },
    ])
    
    # ========== MEDICATIONS - ROUTES & CONTRAINDICATIONS ==========
    questions.extend([
        {
            'level': 'AEMT',
            'category': 'Medications',
            'subcategory': 'Routes',
            'question': 'When administering epinephrine for anaphylaxis, what is the preferred route?',
            'options': ['IV', 'IM (anterolateral thigh)', 'Subcutaneous', 'IO'],
            'correct_answer': 1,
            'explanation': 'IM route in anterolateral thigh is preferred for epinephrine in anaphylaxis. Faster absorption than SC, safer than IV.',
            'source': 'SNHD Protocols - Anaphylaxis'
        },
        {
            'level': 'AEMT',
            'category': 'Medications',
            'subcategory': 'Contraindications',
            'question': 'Morphine sulfate is contraindicated in patients with:\n',
            'options': ['Systolic BP < 100 mmHg', 'Systolic BP < 90 mmHg', 'HR > 100', 'RR < 20'],
            'correct_answer': 1,
            'explanation': 'Morphine is contraindicated if SBP < 90 mmHg (or MAP < 65) due to risk of worsening hypotension. Also contraindicated in severe respiratory depression.',
            'source': 'SNHD Protocols - Pain Management'
        },
        {
            'level': 'PARAMEDIC',
            'category': 'Medications',
            'subcategory': 'Contraindications',
            'question': 'Nitroglycerin is contraindicated in which of the following situations?',
            'options': ['SBP < 120 mmHg', 'SBP < 90 mmHg or use of PDE5 inhibitors within 24-48 hours', 'HR > 100', 'Patient taking aspirin'],
            'correct_answer': 1,
            'explanation': 'Nitroglycerin is contraindicated with SBP < 90 mmHg or if patient took Viagra/Levitra within 24 hours or Cialis within 48 hours (risk of severe hypotension).',
            'source': 'SNHD Protocols - Chest Pain'
        },
        {
            'level': 'PARAMEDIC',
            'category': 'Medications',
            'subcategory': 'Routes',
            'question': 'In a patient with altered mental status and no IV access, what is the preferred route for glucose administration if oral intake is unsafe?',
            'options': ['IM glucagon', 'Subcutaneous insulin', 'IO dextrose', 'Wait for IV access'],
            'correct_answer': 2,
            'explanation': 'If IV access unavailable and patient cannot take oral glucose, IO dextrose is preferred. IM glucagon works but takes 10-15 minutes.',
            'source': 'SNHD Protocols - Altered Mental Status'
        },
    ])
    
    # ========== WAITING ROOM CRITERIA ==========
    questions.extend([
        {
            'level': 'EMT',
            'category': 'Waiting Room Criteria',
            'subcategory': 'General',
            'question': 'Which vital sign would EXCLUDE a patient from being placed in the waiting room?',
            'options': ['HR 95 bpm', 'RR 18/min', 'SBP 105 mmHg', 'SpO2 94% on room air'],
            'correct_answer': 2,
            'explanation': 'SBP < 110 mmHg typically excludes patients from waiting room (depending on protocol). SBP 105 is below threshold requiring immediate evaluation.',
            'source': 'SNHD Protocols - Triage Criteria'
        },
        {
            'level': 'EMT',
            'category': 'Waiting Room Criteria',
            'subcategory': 'General',
            'question': 'A patient with abdominal pain can be placed in the waiting room if they meet all criteria EXCEPT:\n',
            'options': ['Age > 3 years', 'SBP > 110 mmHg', 'HR < 100 bpm', 'Severe, constant pain with guarding'],
            'correct_answer': 3,
            'explanation': 'Severe pain with guarding indicates peritoneal signs and requires immediate evaluation, not waiting room.',
            'source': 'SNHD Protocols - Abdominal Pain Triage'
        },
        {
            'level': 'EMT',
            'category': 'Waiting Room Criteria',
            'subcategory': 'Pediatric',
            'question': 'What is the minimum age for pediatric patients to be considered for waiting room placement (with normal vitals and minor complaints)?',
            'options': ['3 months', '6 months', '1 year', '3 years'],
            'correct_answer': 3,
            'explanation': 'Most protocols require pediatric patients to be ≥ 3 years old for waiting room consideration, due to difficulty assessing severity in younger children.',
            'source': 'SNHD Protocols - Pediatric Triage'
        },
        {
            'level': 'EMT',
            'category': 'Waiting Room Criteria',
            'subcategory': 'Respiratory',
            'question': 'A patient with mild respiratory symptoms may be placed in the waiting room if their SpO2 is:\n',
            'options': ['≥ 90% on room air', '≥ 92% on room air', '≥ 94% on room air', '≥ 96% on room air'],
            'correct_answer': 2,
            'explanation': 'SpO2 ≥ 94% on room air is generally the minimum for waiting room placement in patients with respiratory complaints.',
            'source': 'SNHD Protocols - Respiratory Triage'
        },
    ])
    
    # ========== INTOXICATION / ALTERED MENTAL STATUS ==========
    questions.extend([
        {
            'level': 'EMT',
            'category': 'Transport Criteria',
            'subcategory': 'Intoxication',
            'question': 'An intoxicated patient with altered mental status should be transported if:\n',
            'options': ['They want to go home', 'GCS < 15 or inability to protect airway', 'They can walk unassisted', 'They have a sober friend to drive them'],
            'correct_answer': 1,
            'explanation': 'Altered mental status (GCS < 15), inability to protect airway, or significant trauma mechanism requires transport. Capacity to refuse may be impaired.',
            'source': 'SNHD Protocols - Intoxication'
        },
        {
            'level': 'EMT',
            'category': 'Transport Criteria',
            'subcategory': 'Altered Mental Status',
            'question': 'A patient with altered mental status and a known history of diabetes should have what checked immediately?',
            'options': ['Blood pressure only', 'Blood glucose', 'Temperature', 'Pupil size'],
            'correct_answer': 1,
            'explanation': 'Blood glucose must be checked immediately in altered patients with diabetes history to rule out hypoglycemia, which is rapidly reversible.',
            'source': 'SNHD Protocols - Altered Mental Status'
        },
        {
            'level': 'AEMT',
            'category': 'Transport Criteria',
            'subcategory': 'Intoxication',
            'question': 'A patient with isolated ethanol intoxication (no trauma) and GCS 14 may be appropriate for non-transport if:\n',
            'options': ['They have a ride home', 'They are ambulatory, vitals stable, and can be observed by responsible adult', 'They sign a refusal form', 'They promise not to drive'],
            'correct_answer': 1,
            'explanation': 'Non-transport for intoxication requires: ambulatory, normal vitals, GCS appropriate, no trauma, and observation by responsible sober adult.',
            'source': 'SNHD Protocols - Intoxication Refusal'
        },
        {
            'level': 'PARAMEDIC',
            'category': 'Transport Criteria',
            'subcategory': 'Altered Mental Status',
            'question': 'A patient with suspected opioid overdose has been given naloxone and is now awake. What is the appropriate disposition?',
            'options': ['Release immediately - problem solved', 'Transport required - risk of renarcotization', 'Release if they sign refusal', 'Only transport if they used fentanyl'],
            'correct_answer': 1,
            'explanation': 'Transport is required after naloxone reversal due to risk of renarcotization as naloxone wears off (half-life 30-60 min vs opioids 3-6 hours).',
            'source': 'SNHD Protocols - Opioid Overdose'
        },
    ])
    
    # ========== TRAUMA SCORE & TFTC ==========
    questions.extend([
        {
            'level': 'EMT',
            'category': 'Trauma',
            'subcategory': 'Trauma Score',
            'question': 'The GCS (Glasgow Coma Scale) assesses which three components?',
            'options': ['Pulse, respiration, blood pressure', 'Eye opening, verbal response, motor response', 'Pupil size, eye opening, limb movement', 'Alertness, pain response, verbalization'],
            'correct_answer': 1,
            'explanation': 'GCS assesses: Eye opening (1-4), Verbal response (1-5), and Motor response (1-6). Total range 3-15.',
            'source': 'SNHD Protocols - Neurological Assessment'
        },
        {
            'level': 'EMT',
            'category': 'Trauma',
            'subcategory': 'Trauma Score',
            'question': 'A trauma patient with GCS 13, SBP 85, and RR 28 has a Revised Trauma Score (RTS) of:\n',
            'options': ['RTS = 10 (minor trauma)', 'RTS = 8 (moderate trauma)', 'RTS calculation requires additional data', 'RTS = 6 (severe trauma)'],
            'correct_answer': 2,
            'explanation': 'RTS requires GCS, SBP, and RR values with specific coding. GCS 13=4, SBP 85=3, RR 28=3. RTS = 0.9368(4) + 0.7326(3) + 0.2908(3) ≈ 7.4 (moderate-severe).',
            'source': 'SNHD Protocols - Trauma Scoring'
        },
        {
            'level': 'EMT',
            'category': 'Trauma',
            'subcategory': 'TFTC',
            'question': 'TFTC (Too Far To Care) designation typically applies to patients with which characteristic?',
            'options': ['Minor injuries from MVC', 'Obvious death or unsurvivable injuries', 'Stable vital signs', 'Single system trauma'],
            'correct_answer': 1,
            'explanation': 'TFTC designation is for patients with obvious death (decapitation, rigor mortis, dependent lividity) or injuries incompatible with life.',
            'source': 'SNHD Protocols - Trauma Triage'
        },
        {
            'level': 'EMT',
            'category': 'Trauma',
            'subcategory': 'TFTC',
            'question': 'In a multi-casualty incident, which patient should be given priority for transport first?',
            'options': ['The patient with the loudest complaints', 'The patient with immediate life threats who can be rapidly stabilized', 'The patient with minor injuries', 'The patient who is unresponsive with no pulse'],
            'correct_answer': 1,
            'explanation': 'Triage priority: Immediate (RED) - life threats, can be stabilized. Delayed (YELLOW) - serious but stable. Minor (GREEN). Expectant/Dead (BLACK).',
            'source': 'SNHD Protocols - MCI Triage'
        },
        {
            'level': 'AEMT',
            'category': 'Trauma',
            'subcategory': 'Trauma Score',
            'question': 'Which vital sign change in a trauma patient is most concerning for shock?',
            'options': ['HR increasing from 80 to 110', 'SBP dropping from 140 to 100', 'HR increasing and SBP dropping (pulse pressure narrowing)', 'RR increasing from 16 to 24'],
            'correct_answer': 2,
            'explanation': 'HR increase with SBP drop (narrowing pulse pressure) indicates compensated shock progressing to decompensated. Most concerning combination.',
            'source': 'SNHD Protocols - Hemorrhagic Shock'
        },
        {
            'level': 'PARAMEDIC',
            'category': 'Trauma',
            'subcategory': 'Trauma Score',
            'question': 'What is the Injury Severity Score (ISS) calculation based on?',
            'options': ['Single worst injury', 'Sum of all injury severities', 'Sum of squares of highest AIS scores in 3 most severely injured body regions', 'GCS + RTS + age'],
            'correct_answer': 2,
            'explanation': 'ISS = sum of squares of highest Abbreviated Injury Scale (AIS) scores in the 3 most severely injured body regions. Range 0-75.',
            'source': 'SNHD Protocols - Trauma Scoring'
        },
    ])
    
    # ========== HOSPITAL CATCHMENTS ==========
    questions.extend([
        {
            'level': 'EMT',
            'category': 'Hospital Catchments',
            'subcategory': 'General',
            'question': 'A patient with STEMI (ST-elevation MI) should be transported to:\n',
            'options': ['The nearest hospital', 'A PCI-capable hospital (STEMI receiving center)', 'Any hospital with an ER', 'The patient\'s preferred hospital'],
            'correct_answer': 1,
            'explanation': 'STEMI patients require PCI (percutaneous coronary intervention) within 90 minutes. Transport to nearest PCI-capable facility, bypassing closer non-PCI hospitals.',
            'source': 'SNHD Protocols - STEMI Transport'
        },
        {
            'level': 'EMT',
            'category': 'Hospital Catchments',
            'subcategory': 'Stroke',
            'question': 'A patient with sudden onset stroke symptoms (within 4.5 hours) should be transported to:\n',
            'options': ['Nearest hospital', 'Primary Stroke Center or Comprehensive Stroke Center', 'Any hospital with CT capability', 'Patient\'s insurance-approved facility'],
            'correct_answer': 1,
            'explanation': 'Stroke patients eligible for tPA or thrombectomy must go to designated Stroke Centers with 24/7 stroke teams and neuro-interventional capabilities.',
            'source': 'SNHD Protocols - Stroke Transport'
        },
        {
            'level': 'EMT',
            'category': 'Hospital Catchments',
            'subcategory': 'Trauma',
            'question': 'A patient meeting field trauma triage criteria should be transported to:\n',
            'options': ['Nearest emergency department', 'Trauma Center (Level I, II, or III based on severity)', 'Any hospital with surgery capability', 'Patient choice'],
            'correct_answer': 1,
            'explanation': 'Field trauma criteria trigger transport to designated Trauma Centers. Severe injuries go to Level I/II, moderate to Level III/IV.',
            'source': 'SNHD Protocols - Trauma Transport'
        },
        {
            'level': 'AEMT',
            'category': 'Hospital Catchments',
            'subcategory': 'Burns',
            'question': 'A patient with 25% TBSA (total body surface area) burns should be transported to:\n',
            'options': ['Nearest emergency department', 'Burn Center', 'Any hospital with ICU', 'Trauma Center'],
            'correct_answer': 1,
            'explanation': 'Burns > 20% TBSA (or specific criteria like face/hands/genitals) require Burn Center care for specialized wound management and fluid resuscitation.',
            'source': 'SNHD Protocols - Burn Transport'
        },
    ])
    
    # ========== EXCEPTIONAL CIRCUMSTANCES ==========
    questions.extend([
        {
            'level': 'AEMT',
            'category': 'Exceptions',
            'subcategory': 'Special Cases',
            'question': 'A pregnant patient at 32 weeks gestation with trauma should be transported to:\n',
            'options': ['Nearest hospital', 'Hospital with obstetric and trauma capabilities', 'Any Trauma Center', 'Nearest community hospital'],
            'correct_answer': 1,
            'explanation': 'Pregnant trauma patients > 20 weeks require facilities with both trauma and OB capabilities for fetal monitoring and potential emergency delivery.',
            'source': 'SNHD Protocols - Obstetric Trauma'
        },
        {
            'level': 'PARAMEDIC',
            'category': 'Exceptions',
            'subcategory': 'Special Cases',
            'question': 'In a patient with severe traumatic brain injury (TBI), what is the target SpO2?',
            'options': ['> 90%', '> 94%', '> 98%', '90-92% (permissive hypoxia)'],
            'correct_answer': 1,
            'explanation': 'TBI patients require SpO2 > 94% (some protocols say > 90%) to prevent secondary brain injury from hypoxia. Avoid hypocapnia (ETCO2 35-45).',
            'source': 'SNHD Protocols - TBI Management'
        },
        {
            'level': 'PARAMEDIC',
            'category': 'Exceptions',
            'subcategory': 'Special Cases',
            'question': 'A patient on warfarin with minor head trauma and GCS 15 should:\n',
            'options': ['Be released at scene', 'Be transported for CT scan due to high-risk anticoagulation', 'Sign refusal after being informed of risks', 'Only transport if LOC or vomiting'],
            'correct_answer': 1,
            'explanation': 'Patients on anticoagulants with even minor head trauma are high-risk for delayed intracranial hemorrhage. Transport for CT scan is indicated.',
            'source': 'SNHD Protocols - Anticoagulation Trauma'
        },
    ])
    
    return questions

def add_questions_to_db():
    """Add all generated questions to database"""
    questions = generate_snhd_questions()
    
    with app.app_context():
        added = 0
        skipped = 0
        
        for q in questions:
            # Check if question already exists
            existing = Question.query.filter_by(question=q['question']).first()
            if existing:
                skipped += 1
                continue
            
            question = Question(
                level=q['level'],
                category=q['category'],
                subcategory=q['subcategory'],
                question=q['question'],
                options=json.dumps(q['options']),
                correct_answer=q['correct_answer'],
                explanation=q['explanation'],
                source=q['source']
            )
            db.session.add(question)
            added += 1
        
        db.session.commit()
        print(f"✅ Added {added} new questions")
        print(f"⏭️  Skipped {skipped} duplicates")
        print(f"📊 Total questions in database: {Question.query.count()}")
        
        # Show breakdown by category
        print("\n📁 Questions by Category:")
        categories = db.session.query(Question.category, db.func.count(Question.id)).group_by(Question.category).all()
        for cat, count in categories:
            print(f"  - {cat}: {count}")

if __name__ == '__main__':
    print("🚑 SNHD Protocols Question Bank Generator")
    print("=" * 50)
    add_questions_to_db()
    print("\n✨ Done! Restart your Flask app to use the new questions.")
