# SpeakPro — CEFR Speaking Test Platform

A full-featured Django web application for CEFR speaking test administration, supporting both center students and external candidates with AI-powered scoring.

---

## ✨ Features

| Feature | Details |
|---|---|
| **AI Scoring** | GPT-4o-mini evaluates grammar, vocabulary, pronunciation, fluency |
| **Speech-to-Text** | OpenAI Whisper transcribes recordings |
| **TTS Instructions** | Browser reads instructions aloud to students |
| **Ting Timer** | Prep countdown + answer timer with audio signal |
| **Mic Animation** | Real-time waveform visualization during recording |
| **Student Dashboard** | Streak tracker, history, average scores, performance by part |
| **Teacher Telegram** | Audio recordings + scores sent to teacher's Telegram bot |
| **Mock Test Codes** | External candidates use code + candidate ID |
| **Auto-Logout** | If outsider enters code, logged-in student is silently logged out |
| **Excel Export** | Admin can export results as formatted .xlsx |
| **Live Counter** | Shows how many users are online right now |
| **Analytics** | Admin dashboard for total students, tests, avg scores |

---

## 🚀 Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file (or set environment variables):

```env
SECRET_KEY=your-secret-key-here
DEBUG=False
OPENAI_API_KEY=sk-your-openai-key-here
TELEGRAM_BOT_TOKEN=your-bot-token-here
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
```

Update `settings.py` to load from env:
```python
import environ
env = environ.Env()
environ.Env.read_env()
SECRET_KEY = env('SECRET_KEY')
OPENAI_API_KEY = env('OPENAI_API_KEY')
TELEGRAM_BOT_TOKEN = env('TELEGRAM_BOT_TOKEN')
```

### 3. Database Setup

```bash
python manage.py makemigrations speaking_test
python manage.py migrate
python manage.py createsuperuser
```

### 4. Collect Static Files

```bash
python manage.py collectstatic
```

### 5. Run Development Server

```bash
python manage.py runserver
```

### 6. Production (Gunicorn + Nginx)

```bash
gunicorn cefr_project.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

---

## 📋 Admin Setup Guide

After setup, go to `/admin/` and:

### 1. Add Teachers
- Name + Telegram Chat ID (get ID from @userinfobot on Telegram)
- Bot must be started by the teacher or added to their group

### 2. Create Test Parts
- Part 1.1, 1.2, 2, 3
- Set instructions, prep time, answer time
- Add questions inline (question number, text, level)

### 3. Create Mock Tests (for outsiders)
- Set title + unique code (e.g. `MOCK2024`)
- Assign teacher for Telegram results
- Add candidates with IDs and full names

### 4. Get Telegram Bot Token
1. Message @BotFather on Telegram
2. `/newbot` → follow instructions
3. Copy token to settings
4. Teacher must start the bot (`/start`)
5. Get teacher's chat ID via @userinfobot

---

## 🏗 Project Structure

```
cefr_project/
├── cefr_project/          # Django project config
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── speaking_test/         # Main app
│   ├── models.py          # DB models
│   ├── views.py           # Views
│   ├── admin.py           # Admin config + Excel export
│   ├── services.py        # GPT + Telegram services
│   ├── forms.py           # Registration form
│   ├── middleware.py      # Online tracking
│   └── templates/
│       └── speaking_test/
│           ├── home.html
│           ├── dashboard.html
│           ├── test_session.html   ← Main test UI
│           ├── test_results.html
│           ├── test_select.html
│           └── outsider_entry.html
├── templates/
│   ├── base.html
│   └── registration/
│       └── login.html
├── static/
├── media/                 # Uploaded audio recordings
├── requirements.txt
└── manage.py
```

---

## 🎯 CEFR Scoring Rubric

| Part | Questions | Target Level | Max Score |
|---|---|---|---|
| 1.1 | Q1–Q3 | A1–A2 | 5 |
| 1.2 | Q4–Q6 | A2–B1 | 5 |
| 2 | Q7 | B1–B2 | 5 |
| 3 | Q8 | B2–C1 | 6 |

---

## 🔧 Key URLs

| URL | Description |
|---|---|
| `/` | Home page |
| `/register/` | Student registration |
| `/login/` | Student login |
| `/dashboard/` | Student dashboard |
| `/test/select/` | Choose test part |
| `/outsider/` | External candidate entry |
| `/admin/` | Admin panel |
| `/api/live-count/` | Online users count |

---

## 💡 Customization Tips

- **Scoring criteria**: Edit `SCORING_PROMPTS` in `services.py`
- **Timer sounds**: Modify `playTing()` in `test_session.html`
- **TTS voice**: Adjust `utterance.rate`, `pitch` in test_session.html
- **Streak logic**: Edit `StudentProfile.update_streak()` in models.py
- **Export format**: Customize `export_sessions_xlsx()` in admin.py

---

## 🔒 Security Notes

1. Set `DEBUG = False` in production
2. Use environment variables for all secrets
3. Set `ALLOWED_HOSTS` to your domain only
4. Use HTTPS (required for microphone access!)
5. Restrict `FILE_UPLOAD_MAX_MEMORY_SIZE` as needed

---

*Developed by Sherzodjonov Abdulaziz*
