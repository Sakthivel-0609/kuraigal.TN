# Kuraigal.TN — Citizen Civic Issue Reporting & Grievance Redressal System

A full-stack **Government Smart City Citizen Grievance Management Portal** built with Django.
Citizens report local civic issues (potholes, garbage, water leaks, streetlight failures, and
more), pin the exact GPS location, and track resolution in real time — in the same spirit as
MyGov India, Chennai Corporation, and the Smart Cities Mission.

Three roles are supported: **Citizens** (report & track issues, earn community recognition),
**Officers** (auto-assigned complaints by department, resolve with full accountability), and
**Administrators** (oversee the system via a dedicated dashboard + Django's admin panel).

---

## ✨ Features

**Citizen Reporting** — GPS + photo reporting, voice input, anonymous reporting, auto-save
draft, ward tagging, AI duplicate detection, tracking numbers, QR codes, PDF receipts, email
confirmation, before/after photo comparison, AI-estimated resolution time.

**Artificial Intelligence** *(fully offline, zero API cost)* — category & priority
auto-suggestion, spam detection, extractive summaries, smart search, and an AI chatbot that
understands English, Tamil, and Tanglish with live database-aware answers.

**Maps & Location** — interactive map with marker clustering, heatmap, nearby-issues radius
filter, grid/map toggle view.

**Community** — upvotes, comments, bookmarks, leaderboard (citizens + officers), reputation
tiers, volunteer registration, citizen feedback, officer star ratings.

**Government Administration** — 12 departments with auto-routing, officer dashboard, staff
assignment panel, full Django admin, audit log, SLA-based auto-escalation, ward-wise
analytics, Excel/CSV export.

**Emergency Management** — 10 emergency types, live auto-refreshing dashboard, instant staff
broadcast, helpline numbers on the report form.

**Accessibility & PWA** — installable on Android/iOS, offline mode, bilingual (English/Tamil),
font-size & high-contrast controls, browser push-style notifications.

**Security & Performance** — role-based access, login brute-force protection, CSRF/XSS/SQLi
protection, file upload validation, pagination, database indexing, query caching.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django (Python), Django ORM |
| Database | SQLite (dev), PostgreSQL-ready (production) |
| Frontend | HTML5, CSS3, Bootstrap 5, JavaScript, AJAX |
| Maps | Leaflet.js + OpenStreetMap |
| Charts | Chart.js |
| AI | Custom rule-based Python engine (offline) |
| PDF / QR / Email | ReportLab, qrcode, SMTP |
| PWA | Service Worker + Web App Manifest |
| Production server | Gunicorn + WhiteNoise |

---

## 🚀 Local Setup

```bash
git clone https://github.com/<your-username>/kuraigal-tn.git
cd kuraigal-tn

python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt

python manage.py makemigrations issues
python manage.py migrate
python manage.py loaddata issues/fixtures/initial_departments.json
python manage.py loaddata issues/fixtures/initial_categories.json
python manage.py createsuperuser

python manage.py runserver
```

Visit `http://127.0.0.1:8000`.

### Optional: Email confirmations

To enable real email confirmations (citizens get a PDF receipt by email), set an app password
for the sending Gmail account and export it before running the server:

```bash
set DJANGO_EMAIL_PASSWORD=your16characterapppassword     # Windows
# export DJANGO_EMAIL_PASSWORD=your16characterapppassword  # macOS/Linux
```

Without this set, emails print to the terminal instead of sending — safe for local testing.

---

## 🌐 Deploying (Live URL)

GitHub itself only hosts the **code** — to get a live URL, connect this repo to a real Python
host. [Render.com](https://render.com) has a free tier and reads the included `render.yaml`
automatically:

1. Push this repo to GitHub (see below).
2. On [render.com](https://render.com), click **New +** → **Blueprint**, and connect this repo.
3. Render provisions a free PostgreSQL database and a web service automatically from
   `render.yaml`.
4. Add your `DJANGO_EMAIL_PASSWORD` in the Render dashboard's environment variables (marked
   `sync: false` in the blueprint, so it must be entered manually for security).
5. Deploy — Render gives you a live `https://kuraigal-tn.onrender.com`-style URL.

*(Railway.app and PythonAnywhere are similar free alternatives if preferred.)*

---

## 📤 Pushing to GitHub

```bash
git init
git add .
git commit -m "Initial commit - Kuraigal.TN"
git branch -M main
git remote add origin https://github.com/<your-username>/kuraigal-tn.git
git push -u origin main
```

**Never commit** `db.sqlite3`, your `venv/` folder, or any `.env` file with real secrets — the
included `.gitignore` already excludes these.

---

## 📄 License

Built as an educational Government Smart City Portal project.
