# EMS Learning Platform 🚑

A personalized NREMT training platform built from SNHD protocols using your NotebookLM content.

## Features

✅ **User Level Personalization** - Content tailored to EMT, AEMT, or Paramedic levels  
✅ **Interactive Quizzes** - 10-question sessions with immediate feedback  
✅ **Progress Tracking** - Percentage scores, correct/incorrect breakdown  
✅ **Explanations** - Learn from mistakes with detailed explanations  
✅ **Web-Based** - Share with classmates, accessible anywhere  

## Quick Start

### 1. Install Dependencies
```bash
cd ems-platform
pip install -r requirements.txt
```

### 2. Run the App
```bash
python app.py
```

### 3. Open in Browser
Go to `http://localhost:5000`

## How to Use

1. **Register** - Enter your name and select your NREMT level (EMT/AEMT/Paramedic)
2. **Dashboard** - View your progress statistics
3. **Take Quiz** - Answer 10 questions at your level
4. **Review Results** - See detailed breakdown and explanations

## Adding More Questions

### Option 1: Manual Entry
Edit `app.py` and add questions to the `init_sample_questions()` function:

```python
{
    'level': 'EMT',  # or 'AEMT', 'PARAMEDIC'
    'category': 'Airway',
    'question': 'Your question here?',
    'options': ['Option A', 'Option B', 'Option C', 'Option D'],
    'correct_answer': 0,  # Index of correct answer (0-3)
    'explanation': 'Why this is correct',
    'source': 'SNHD Protocols - Section Name'
}
```

### Option 2: Import from NotebookLM (Coming Soon)
I'll create an import script that reads your SNHD protocols notebook and auto-generates questions.

## Database

SQLite database stored at `data/protocols.db`

Tables:
- `users` - User profiles and levels
- `questions` - Question bank with explanations
- `answers` - User answer history

## Customization

### Add Your Own Content
1. Study your SNHD protocols notebook
2. Extract key protocols and create questions
3. Add to the question bank
4. Share with your study group

### Deploy for Others
```bash
# For development
flask run --host=0.0.0.0

# For production (use a WSGI server)
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## Next Steps

Want me to:
1. Create an import script from your NotebookLM content?
2. Add more question types (scenario-based, image-based)?
3. Add voice narration using TTS?
4. Create study schedules and spaced repetition?
5. Add a multiplayer/competitive mode?

Just ask!

## Project Structure

```
ems-platform/
├── app.py              # Flask application
├── requirements.txt    # Python dependencies
├── data/
│   └── protocols.db    # SQLite database
└── templates/
    ├── index.html      # Registration page
    ├── dashboard.html  # User dashboard
    ├── quiz.html       # Quiz interface
    └── results.html    # Results page
```

---

Built with ❤️ by Bento for Anh's NREMT success 🚑
