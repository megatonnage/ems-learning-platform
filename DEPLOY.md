# EMS Learning Platform - Deployment Guide 🚑

## Quick Deploy Options

### Option 1: PythonAnywhere (Easiest - Free)
1. Go to https://www.pythonanywhere.com
2. Create free account
3. Upload your `ems-platform` folder
4. Create web app with Flask
5. Set WSGI file to point to `app.py`
6. Your app will be live at `yourusername.pythonanywhere.com`

### Option 2: Heroku (Free tier available)
1. Install Heroku CLI
2. Create `Procfile` with: `web: gunicorn app:app`
3. Create `requirements.txt` (already done)
4. `git init && git add . && git commit -m "Initial"`
5. `heroku create your-app-name`
6. `git push heroku main`

### Option 3: Railway/Render (Simple PaaS)
1. Connect GitHub repo to Railway or Render
2. Auto-deploys on push
3. Free tier available

### Option 4: Self-hosted (Your Mac)
Your app is already running! Share with classmates:
- Local: http://127.0.0.1:5000
- Network: http://192.168.0.232:5000

**For classmates on same WiFi:** Use the 192.168.0.232:5000 address

## Current Stats

✅ **140+ Questions** including:
- Pediatric fluid boluses (20+ questions)
- Pediatric medications (25+ questions)  
- Adult protocols
- Trauma/TFTC criteria
- Hospital selection
- Special circumstances

✅ **Features:**
- Category filtering
- Progress tracking
- Detailed explanations
- EMT/AEMT/Paramedic levels

## Next Steps

1. **Choose deployment option above**
2. **Share URL with classmates**
3. **Collect feedback**
4. **Add more content** (I can generate unlimited questions)

## Want More Questions?

I can add:
- ECG interpretation
- Drug calculations
- Scenario-based cases
- Image-based questions
- Audio narrated questions

Just ask!
