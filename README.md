# 🚨 Community Emergency Response Platform

An SOS and emergency coordination platform for gated societies and apartments. A resident at home alone (an elderly parent, a child, a dependent) presses one button, and guardians, security staff and nearby volunteers are alerted instantly. If nobody responds in time, the alert escalates automatically.

> 🚧 **Work in progress.** A solo project: a production-style Django backend, with an AI layer (LangGraph triage agent, RAG first-aid assistant, multilingual voice SOS) planned on top.

## ✅ Features built so far

- **Users and roles:** Resident, Guardian, Volunteer, Security Staff, Admin (custom Django user model)
- **Society structure:** Society → Tower → Flat → Resident
- **Guardians and emergency contacts:** guardians are ranked by priority to set the escalation order
- **JWT authentication:** register, log in, refresh token, profile
- **SOS alerts:** one API call creates an incident and immediately alerts the primary guardian, the society's security staff and available volunteers
- **Alert tracking:** every alert is stored with its audience, channel, escalation level and delivery status

## 🛠 Tech stack

Python · Django · Django REST Framework · SimpleJWT · SQLite (dev) → PostgreSQL

*Planned:* Celery + Redis, Django Channels, Firebase / Twilio, LangGraph, Whisper, pgvector, Docker

## 🚀 Run locally

```bash
git clone https://github.com/Ankit-builds1/community-sos-platform.git
cd community-sos-platform
python -m venv venv
venv\Scripts\activate            # Windows  (source venv/bin/activate on Mac/Linux)
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo       # demo society + one user per role (password: Demo@1234)
python manage.py createsuperuser
python manage.py runserver
```

Admin panel: http://127.0.0.1:8000/admin

## 📡 API endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register/` | Create an account (Resident / Guardian / Volunteer) |
| POST | `/api/auth/login/` | Get JWT access and refresh tokens |
| POST | `/api/auth/refresh/` | Refresh the access token |
| GET / PATCH | `/api/auth/me/` | Your own profile |
| GET | `/api/societies/` | Societies with their towers and flats |
| CRUD | `/api/my/guardians/` | Manage your guardians |
| CRUD | `/api/my/emergency-contacts/` | Manage your emergency contacts |
| POST | `/api/incidents/raise/` | **Raise an SOS** |
| GET | `/api/incidents/` | Incidents you raised or were alerted about |

## 🗺 Roadmap

- [x] Module 1: users, roles, society structure, JWT APIs
- [ ] Module 2: SOS alerts ✅ · real push / SMS / email notifications
- [ ] Module 3: responder accept, automatic guardian escalation, emergency chat
- [ ] Module 4: mobile app, testing, deployment
- [ ] AI layer: LangGraph triage agent, RAG first-aid assistant, voice SOS, AI incident reports

## 👤 Author

**Ankit Dash** · [GitHub](https://github.com/Ankit-builds1)
