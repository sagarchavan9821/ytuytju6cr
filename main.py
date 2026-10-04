import os, json, time, sqlite3, secrets, hmac
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DB = os.getenv("DB_PATH", "examhall.db")
ADMIN_PHONE = "".join(ch for ch in os.getenv("ADMIN_PHONE", "9999999999") if ch.isdigit())
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
GRACE = 5  # seconds of network delay allowed after the timer ends

app = FastAPI(title="Online Exam System")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, phone TEXT UNIQUE, role TEXT DEFAULT 'student');
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER, created REAL);
CREATE TABLE IF NOT EXISTS exams(id INTEGER PRIMARY KEY, title TEXT, minutes INTEGER);
CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY, exam_id INTEGER, text TEXT, options TEXT, answer INTEGER);
CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, user_id INTEGER, exam_id INTEGER, started REAL, finished REAL, score INTEGER, total INTEGER);
"""

SAMPLE = [
    ("Which language is used to style web pages?", ["HTML", "CSS", "Python", "SQL"], 1),
    ("What does SQL stand for?", ["Structured Query Language", "Simple Question Logic", "Sorted Query List", "System Query Layer"], 0),
    ("Which HTTP method is normally used to create data?", ["GET", "DELETE", "POST", "HEAD"], 2),
    ("Which of these is a Python web framework?", ["React", "FastAPI", "Bootstrap", "Redis"], 1),
    ("What is 15% of 200?", ["20", "25", "30", "35"], 2),
    ("Which language is used to style web pages?", ["HTML", "CSS", "Python", "SQL"], 1),
    ("What does HTML stand for?", ["High Transfer Markup Language", "HyperText Markup Language", "Hyper Tool Multi Language", "Home Text Markup Level"], 1),
    ("Which HTML tag creates a hyperlink?", ["<link>", "<a>", "<href>", "<url>"], 1),
    ("Which of these is NOT a programming language?", ["Java", "Ruby", "Go", "Linux"], 3),
    ("What does CSS stand for?", ["Computer Style Sheets", "Cascading Style Sheets", "Creative Style System", "Colorful Style Sheets"], 1),
    ("Which data structure follows First In, First Out (FIFO)?", ["Stack", "Queue", "Tree", "Graph"], 1),
    ("Which HTTP status code means 'Not Found'?", ["200", "301", "500", "404"], 3),
    ("Which keyword defines a function in Python?", ["func", "function", "def", "define"], 2),
    ("What is the output of 2 ** 3 in Python?", ["5", "6", "8", "9"], 2),
    ("Which SQL command is used to retrieve data from a table?", ["GET", "FETCH", "EXTRACT", "SELECT"], 3),
    ("Which of these is a relational database?", ["Redis", "MongoDB", "PostgreSQL", "Elasticsearch"], 2),
    ("What does API stand for?", ["Application Programming Interface", "Applied Program Integration", "Automated Page Index", "Application Process Input"], 0),
    ("Which Git command saves your changes to the local repository?", ["git push", "git commit", "git clone", "git pull"], 1),
    ("What is the decimal number 5 in binary?", ["100", "110", "111", "101"], 3),
    ("Which language runs natively in a web browser?", ["Python", "C++", "JavaScript", "Go"], 2),
]

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def q(sql, args=(), one=False):
    c = db()
    try:
        rows = c.execute(sql, args).fetchall()
        c.commit()
    finally:
        c.close()
    return (rows[0] if rows else None) if one else rows

def ins(sql, args=()):
    c = db()
    try:
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid
    finally:
        c.close()

@app.on_event("startup")
def init():
    c = db(); c.executescript(SCHEMA); c.commit(); c.close()
    if not q("SELECT 1 FROM users WHERE role='admin'", one=True):
        ins("INSERT INTO users(name,phone,role) VALUES(?,?,'admin')", ("Admin", ADMIN_PHONE))
    if not q("SELECT 1 FROM exams", one=True):
        eid = ins("INSERT INTO exams(title,minutes) VALUES(?,?)", ("Web Basics Quiz", 5))
        for t, o, a in SAMPLE:
            ins("INSERT INTO questions(exam_id,text,options,answer) VALUES(?,?,?,?)", (eid, t, json.dumps(o), a))

def user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Please log in")
    r = q("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?", (authorization[7:],), one=True)
    if not r:
        raise HTTPException(401, "Session expired, please log in again")
    return dict(r)

def admin(u=Depends(user)):
    if u["role"] != "admin":
        raise HTTPException(403, "Admins only")
    return u

class Login(BaseModel):
    name: str
    phone: str
    password: str = ""

class Submit(BaseModel):
    answers: dict = {}

class ExamIn(BaseModel):
    title: str
    minutes: int

class QuestionIn(BaseModel):
    text: str
    options: list[str]
    answer: int

@app.post("/api/login")
def login(b: Login):
    name = " ".join(b.name.split())
    phone = "".join(ch for ch in b.phone if ch.isdigit())
    if len(name) < 2 or not 10 <= len(phone) <= 15:
        raise HTTPException(400, "Enter your name and a valid phone number (10 digits)")
    u = q("SELECT * FROM users WHERE phone=?", (phone,), one=True)
    if not u:  # first visit: create the student automatically
        ins("INSERT INTO users(name,phone) VALUES(?,?)", (name, phone))
        u = q("SELECT * FROM users WHERE phone=?", (phone,), one=True)
    if u["role"] == "admin" and not hmac.compare_digest(b.password.encode(), ADMIN_PASSWORD.encode()):
        raise HTTPException(401, "Enter the admin password")
    token = secrets.token_hex(24)
    ins("INSERT INTO sessions VALUES(?,?,?)", (token, u["id"], time.time()))
    return {"token": token, "name": u["name"], "role": u["role"]}

@app.get("/api/exams")
def exams(u=Depends(user)):
    return [dict(r) for r in q("SELECT e.id,e.title,e.minutes,(SELECT COUNT(*) FROM questions WHERE exam_id=e.id) n FROM exams e")]

def grade(aid, answers):
    a = q("SELECT * FROM attempts WHERE id=?", (aid,), one=True)
    qs = q("SELECT * FROM questions WHERE exam_id=?", (a["exam_id"],))
    score = sum(1 for r in qs if answers.get(str(r["id"])) == r["answer"])
    ins("UPDATE attempts SET finished=?, score=?, total=? WHERE id=?", (time.time(), score, len(qs), aid))
    review = [{"text": r["text"], "options": json.loads(r["options"]), "correct": r["answer"], "chosen": answers.get(str(r["id"]))} for r in qs]
    return {"score": score, "total": len(qs), "percent": round(100 * score / len(qs)) if qs else 0, "review": review}

@app.post("/api/exams/{eid}/start")
def start(eid: int, u=Depends(user)):
    e = q("SELECT * FROM exams WHERE id=?", (eid,), one=True)
    if not e:
        raise HTTPException(404, "Exam not found")
    a = q("SELECT * FROM attempts WHERE user_id=? AND exam_id=? AND finished IS NULL", (u["id"], eid), one=True)
    if a and time.time() > a["started"] + e["minutes"] * 60 + GRACE:
        grade(a["id"], {})  # an abandoned attempt past its time is closed with a score from no answers
        a = None
    if not a:
        aid = ins("INSERT INTO attempts(user_id,exam_id,started) VALUES(?,?,?)", (u["id"], eid, time.time()))
        a = q("SELECT * FROM attempts WHERE id=?", (aid,), one=True)
    qs = [{"id": r["id"], "text": r["text"], "options": json.loads(r["options"])} for r in q("SELECT * FROM questions WHERE exam_id=?", (eid,))]
    left = max(0, int(a["started"] + e["minutes"] * 60 - time.time()))
    return {"attempt_id": a["id"], "title": e["title"], "seconds_left": left, "questions": qs}

@app.post("/api/attempts/{aid}/submit")
def submit(aid: int, b: Submit, u=Depends(user)):
    a = q("SELECT a.*, e.minutes FROM attempts a JOIN exams e ON e.id=a.exam_id WHERE a.id=? AND a.user_id=?", (aid, u["id"]), one=True)
    if not a:
        raise HTTPException(404, "Attempt not found")
    if a["finished"]:
        raise HTTPException(400, "This attempt was already submitted")
    late = time.time() > a["started"] + a["minutes"] * 60 + GRACE
    return grade(aid, {} if late else b.answers)  # answers sent after the deadline are ignored

@app.get("/api/results")
def results(u=Depends(user)):
    return [dict(r) for r in q("SELECT a.id,e.title,a.score,a.total,a.finished FROM attempts a JOIN exams e ON e.id=a.exam_id WHERE a.user_id=? AND a.finished IS NOT NULL ORDER BY a.finished DESC", (u["id"],))]

@app.post("/api/admin/exams")
def add_exam(b: ExamIn, u=Depends(admin)):
    if not b.title.strip() or b.minutes < 1:
        raise HTTPException(400, "Enter a title and at least 1 minute")
    return {"id": ins("INSERT INTO exams(title,minutes) VALUES(?,?)", (b.title.strip(), b.minutes))}

@app.post("/api/admin/exams/{eid}/questions")
def add_question(eid: int, b: QuestionIn, u=Depends(admin)):
    opts = [o.strip() for o in b.options if o.strip()]
    if not b.text.strip() or len(opts) < 2 or not 0 <= b.answer < len(opts):
        raise HTTPException(400, "Enter a question, 2+ options, and a valid correct option")
    return {"id": ins("INSERT INTO questions(exam_id,text,options,answer) VALUES(?,?,?,?)", (eid, b.text.strip(), json.dumps(opts), b.answer))}

@app.get("/api/admin/results")
def all_results(u=Depends(admin)):
    return [dict(r) for r in q("SELECT u.name,e.title,a.score,a.total,a.finished FROM attempts a JOIN users u ON u.id=a.user_id JOIN exams e ON e.id=a.exam_id WHERE a.finished IS NOT NULL ORDER BY a.finished DESC LIMIT 100")]

app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend"), html=True), name="web")
