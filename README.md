# 🚨 Community Emergency Response Platform

An AI-powered SOS and emergency coordination platform for gated societies and apartments. A resident at home alone (an elderly parent, a child, a dependent) presses one button, and guardians, security staff and nearby volunteers are alerted instantly. If nobody responds in time, the alert escalates automatically. An AI agent then triages the emergency, and a RAG assistant gives grounded first-aid steps while help is on the way. Both work in **English, Hindi and Odia**.

> 🚧 **Work in progress**, solo project. Next up: Docker + PostgreSQL + Celery, a web dashboard and deployment.

## ✨ Features

### Core emergency system (Django + DRF)
- **Users and roles:** Resident, Guardian, Volunteer, Security Staff, Admin (custom user model, JWT auth)
- **Society structure:** Society → Tower → Flat → Resident, with guardians ranked by priority and emergency contacts
- **One-tap SOS:** creates an incident and **immediately** alerts the primary guardian, security staff and available volunteers
- **Automatic 3-level escalation:** secondary guardian → emergency contacts (SMS) → flagged for human review. Critical cases escalate 4× faster.
- **Responder workflow:** accept / decline / resolve, where the first responder wins (row-level locking prevents two people taking the same incident)
- **Alert audit trail:** every alert is stored with audience, channel, escalation level, delivery status and response time

### 🤖 AI triage agent (LangGraph)
```
SOS saved + alerts SENT  →  (background)
START → rule baseline → LLM classify (Groq, JSON + Pydantic)
      → confidence < 0.6 or error? → use rules
      → guardrail: severity can only go UP from rule evidence → save
```
- Reads the SOS message and fills in **category, severity and a calm English summary** for the guardian
- **Never blocks an alert:** it runs only after alerts are sent
- **Fallbacks:** rule-based triage when the LLM fails, plus a **backup model** when the main model hits its rate limit
- **Prompt-injection defence:** the message is treated as data, injection attempts are flagged, and the AI can't lower severity below the rule-based evidence

### 🩺 RAG first-aid assistant
```
question (any language) → LLM query rewriting → English search query
  → local multilingual embeddings → parent-document retrieval (search small pieces, return the whole guide)
  → LLM answers ONLY from the retrieved guides → steps + sources + "Call 108 / 112"
```
- **14 first-aid guides** (chest pain, CPR, choking, stroke, bleeding, falls, seizures, low sugar, burns, poisoning, allergies, fire/gas leaks, intruder safety…)
- **Guardrails:** refuses medicine-dose and diagnosis questions, says "no guide" instead of guessing, never drops a real SOS as off-topic, and falls back to the guide text when the LLM is down
- Embeddings run **locally** (fastembed / ONNX), so retrieval costs nothing

## 📊 Evaluation

All numbers come from the eval commands in this repo (`eval_triage`, `eval_firstaid`). The test sets were written for this project in English, Hinglish, Hindi script, Odia script and Odia in Roman letters.

### Triage agent
| Metric | Rules only (dev set, 100 msgs) | AI agent v1 (dev set, 100 msgs) | **AI agent v2 (held-out set, 50 unseen msgs)** |
|---|---|---|---|
| Category accuracy | 61% | 84% | **98%** |
| Category macro-F1 | 0.66 | 0.83 | **0.97** |
| Severity exact match | 29% | 57% | **78%** |
| **Under-triage** (rated less serious than reality, lower is better) | 51% | 19% | **4%** |
| Critical-case recall | 34% | 66% | **93%** |
| LLM latency p50 / p95 | — | 1.5 s / 3.6 s | **1.3 s / 2.0 s** |

v2 changes (prompt severity policy, multilingual rule keywords, safer defaults) were made after studying v1's errors on the dev set, then measured on a **separate held-out set**. Known limitation: held-out injection-detection results are incomplete because of API rate limits during the run.

### RAG retrieval (34 questions: 28 in-scope, 3 out-of-scope, 3 dose/diagnosis)
| Metric | Raw question | **With query rewriting** |
|---|---|---|
| Hit@1 | 60.7% | **82.1%** |
| Hit@3 | 89.3% | **92.9%** |
| MRR | 0.73 | **0.87** |
| Hinglish Hit@1 | 33% | **83%** |
| Odia Hit@1 | 0% | **75%** |
| Out-of-scope → "no guide" | 100% | **100%** |
| Dose / diagnosis refused | 100% | **100%** |

Query rewrites use a fixed seed, so results are repeatable. Known confusions: stroke vs choking, convulsions vs CPR.

## 🛠 Tech stack

**Backend:** Python, Django 6, Django REST Framework, SimpleJWT, SQLite (dev)
**AI:** LangGraph, Groq (`gpt-oss-120b` + `gpt-oss-20b` backup), Pydantic, fastembed (`paraphrase-multilingual-MiniLM-L12-v2`), NumPy vector search
**Quality:** 35 automated tests (LLM mocked, run offline), evaluation harnesses for triage and RAG

*Planned:* PostgreSQL + pgvector, Redis + Celery, Docker, Django Channels, web dashboard

## 🚀 Run locally

```bash
git clone https://github.com/Ankit-builds1/community-sos-platform.git
cd community-sos-platform
python -m venv venv
venv\Scripts\activate             # Windows  (source venv/bin/activate on Mac/Linux)
pip install -r requirements.txt
copy .env.example .env            # then add your free Groq API key (console.groq.com)
python manage.py migrate
python manage.py seed_demo        # demo society + one user per role (password: Demo@1234)
python manage.py build_firstaid_index
python manage.py createsuperuser
python manage.py runserver
```

In a second terminal, start the escalation worker: `python manage.py run_escalations`

| Command | Purpose |
|---|---|
| `python manage.py test` | Run all tests |
| `python manage.py eval_triage --mode full --dataset holdout` | Triage evaluation |
| `python manage.py eval_firstaid` | RAG retrieval evaluation |

## 📡 API endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register/` | Create an account (Resident / Guardian / Volunteer) |
| POST | `/api/auth/login/` | Get JWT access and refresh tokens |
| GET / PATCH | `/api/auth/me/` | Your own profile |
| GET | `/api/societies/` | Societies with their towers and flats |
| CRUD | `/api/my/guardians/`, `/api/my/emergency-contacts/` | Manage your guardians and contacts |
| POST | `/api/incidents/raise/` | **Raise an SOS** |
| GET | `/api/incidents/` | Incidents you raised or were alerted about |
| POST | `/api/incidents/<id>/accept/` · `decline/` · `resolve/` | Responder actions |
| GET | `/api/incidents/<id>/first-aid/` | RAG first-aid steps for an incident |
| POST | `/api/first-aid/ask/` | Ask the first-aid assistant directly |

## 🗺 Roadmap

- [x] Users, roles, society structure, JWT APIs
- [x] SOS alerts, 3-level escalation, responder workflow
- [x] LangGraph AI triage agent + evaluation
- [x] RAG first-aid assistant + evaluation
- [ ] Docker + PostgreSQL (pgvector) + Redis + Celery
- [ ] Web dashboard for security and admin
- [ ] Deployment + demo video
- [ ] Voice SOS (Whisper), real push/SMS notifications, live chat

## ⚠️ Disclaimer
The first-aid guides are written for this project and kept deliberately conservative. They're not medical advice. In a real emergency, call **108** (ambulance) or **112**.

## 👤 Author

**Ankit Dash** · [GitHub](https://github.com/Ankit-builds1)
