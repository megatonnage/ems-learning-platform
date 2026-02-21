# Phase 1 Implementation: Mnemonic Hint Feature

## What Was Added

### 1. Database Migration
**File:** `migrations/001_add_mnemonic_fields.sql`

Run this in Supabase SQL Editor to add:
- `mnemonic_enabled` (boolean)
- `mnemonic_acronym` (varchar 20)
- `mnemonic_expansion` (text)
- `mnemonic_teaching_context` (text)

### 2. Updated Question Model
**File:** `app.py` - Question class

Added fields + `to_dict_with_mnemonic()` method for admin API

### 3. New API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/question/<id>/hint` | POST | Student reveals hint (returns acronym) |
| `/api/question/<id>/mnemonic` | GET | Get full mnemonic (for teaching moment) |
| `/api/questions/with-mnemonics` | GET | Admin: list all questions with mnemonic data |

### 4. Updated Admin Routes

- `POST /admin/question/new` - accepts mnemonic fields
- `POST /admin/question/<id>/edit` - accepts mnemonic fields
- `GET /admin/question/<id>/json` - returns mnemonic data

## How to Deploy Phase 1

1. **Run the migration:**
   ```bash
   # In Supabase SQL Editor, run:
   migrations/001_add_mnemonic_fields.sql
   ```

2. **Deploy the code:**
   ```bash
   git add .
   git commit -m "Add mnemonic hint feature - Phase 1"
   git push origin main
   ```

3. **Test the endpoints:**
   ```bash
   # Reveal hint (student)
   curl -X POST https://your-domain.com/api/question/1/hint \
     -H "Content-Type: application/json" \
     -b "session_cookie"
   
   # Get full mnemonic
   curl https://your-domain.com/api/question/1/mnemonic \
     -b "session_cookie"
   ```

## Phase 2 Preview (Next)

Add student-facing UI:
- "💡 Reveal hint" link below answer choices
- Hint card display
- Hide hint after submission

## Phase 3 Preview (After)

Teaching moment integration:
- Show full mnemonic after wrong answers
- Show as "bonus" after correct answers

## Data Population (Temporary)

Until admin UI is built (Phase 4), populate mnemonics via SQL:

```sql
UPDATE question 
SET 
  mnemonic_enabled = true,
  mnemonic_acronym = 'OPQRST',
  mnemonic_expansion = 'O - Onset (when did it start?)
P - Provocation (what makes it better/worse?)
Q - Quality (sharp, dull, pressure?)
R - Radiation (does it move?)
S - Severity (rate 1-10)
T - Time (how long has it lasted?)',
  mnemonic_teaching_context = 'This question asks about chest pain assessment, the classic use case for OPQRST.'
WHERE id = 1;
```
