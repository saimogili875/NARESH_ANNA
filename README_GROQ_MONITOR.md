# Groq Token Usage Tracker & Quota Monitoring Dashboard

A production-quality Groq API Token Usage Tracker and Quota Monitoring Dashboard integrated with the **Sri NRI Junior College** Management System and the **Swecha AI Assistant**.

---

## 1. Architecture Overview

- **Backend**: Python 3.13 / 3.14, Django 5.2, Official Groq Python SDK (`groq>=1.7.0`).
- **Database**: PostgreSQL (Supabase / AWS AP-South-1) in production, SQLite fallback in development.
- **Frontend**: Bootstrap 5, Chart.js 4.4, Lovable-inspired UI aesthetic with audio sound feedback (`chatbot_sound.mp3`).
- **Primary AI Models**:
  - `qwen/qwen3.8-27b` (Sub-second inference, multilingual Telugu/English support).
  - `openai/gpt-oss-120b` (Deep analytical reasoning fallback).
  - `whisper-large-v3-turbo` (Speech-to-Text transcription).

---

## 2. Core Features

1. **Accurate Token Counting**:
   - Records actual usage reported by the Groq API (`prompt_tokens`, `completion_tokens`, `total_tokens`).
   - Distinguishes between actual verified API usage and user-configured estimates.
   - Logs response latency in milliseconds and HTTP status.
   - Captures rate-limit response headers (`x-ratelimit-remaining-*`).
2. **Atomic Daily Aggregations**:
   - Updates `DailyUsageSummary` per date and model atomically to avoid double-counting.
3. **8 Summary Metrics**:
   - Total Input Tokens
   - Total Output Tokens
   - Total Tokens Consumed
   - Total API Requests
   - Successful Requests (HTTP 200)
   - Failed Requests / Rate Limits (HTTP 429)
   - Estimated Remaining Daily Tokens
   - Daily Usage Percentage
4. **5 Chart.js Visualizations**:
   - Daily Token Consumption (Prompt vs Completion line chart)
   - Model Comparison (Bar chart)
   - Request Activity Over Time (Bar chart)
   - Usage Distribution (Input vs Output doughnut chart)
   - Daily Quota Progress (Visual gauge)
5. **API Request History**:
   - Search by model name and error message.
   - Filter by date and status.
   - Pagination and **CSV Export**.
6. **Swecha AI Chatbot**:
   - Multilingual Telugu & English assistant.
   - Real-time college context retrieval (students, attendance, fee collections).
   - Audio feedback on question send and agent reply via `static/chatbot_sound.mp3`.

---

## 3. Environment Variables Configuration

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Set the required environment variables:
```env
SECRET_KEY=your-django-secret-key
DEBUG=True
DATABASE_URL=postgresql://user:password@host:port/database
ALLOWED_HOSTS=localhost,127.0.0.1

# Groq API Configuration
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=qwen/qwen3.8-27b
```

---

## 4. Installation & Database Setup

1. **Activate Virtual Environment**:
   ```bash
   source .venv/bin/activate
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run Migrations**:
   ```bash
   python manage.py migrate
   ```

4. **Run the Development Server**:
   ```bash
   python manage.py runserver 8001
   ```

---

## 5. Running Automated Tests

Run the test suite using SQLite:
```bash
DATABASE_URL="" python manage.py test chatbot
```

All unit tests mock Groq API calls to ensure zero real quota consumption during testing.

---

## 6. Security Considerations

- API keys are stored only in environment variables and are never transmitted to frontend code.
- CSRF protection is enforced on all web forms.
- Sensitive credentials and prompt payloads are not logged to the database.
- Database backups and secrets are ignored via `.gitignore`.
