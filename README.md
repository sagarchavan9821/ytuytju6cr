# ExamHall - online examination system

FastAPI backend + plain HTML/CSS/JS frontend, served together by one app.

## Run locally (VS Code terminal)
    cd backend
    pip install -r requirements.txt
    uvicorn main:app --reload
Open http://127.0.0.1:8000

Students log in with just their name and phone number. A new phone number is registered automatically on first login.
Admin: log in with the admin phone (default 9999999999) and then enter the admin password (default admin123).
Set ADMIN_PHONE and ADMIN_PASSWORD environment variables to change them before going live.

## How it works
- Login uses name + phone number only (no email or password for students) and random session tokens. Anyone who knows a phone number can log in as that student, so this suits classroom or practice use rather than high-stakes exams.
- Starting an exam stores the start time on the server; the countdown runs in the browser but the deadline is enforced by the server.
- When the timer hits 00:00 the page auto-submits. The server grades the answers and returns the score and a correct-answer review.
- Correct answers are never sent to the browser until the exam is submitted.
- Closing the tab does not save answers; an unsubmitted exam scores 0 once its time is up.

## Deploy on Render (one service, free tier)
1. Push this folder to a GitHub repo.
2. Render > New > Web Service > pick the repo.
3. Build command: pip install -r backend/requirements.txt
4. Start command: uvicorn main:app --app-dir backend --host 0.0.0.0 --port $PORT
5. Add environment variables ADMIN_PHONE and ADMIN_PASSWORD.

Note: SQLite data is erased on each deploy on Render's free tier. For a permanent site, move to PostgreSQL (Neon or Render Postgres) or attach a persistent disk and set DB_PATH to it.
