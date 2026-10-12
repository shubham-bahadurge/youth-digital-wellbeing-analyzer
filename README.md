# Youth Digital Well-being Analyzer

A software-only Community Engagement Project (CEP) on **Impact of Mobile Phones on Youth**. Includes an anonymous survey, SQLite storage, responsive analytics dashboard, and PDF report export.

## Features
- Responsive landing page explaining both benefits and challenges of mobile phones.
- Anonymous questionnaire; no name, phone number, email, or login is requested.
- SQLite storage for local demonstrations.
- Dashboard with average screen time, study time, sleep, and Chart.js charts.
- Downloadable PDF summary.
- Health endpoint at `/health`.

## Run locally on macOS
```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000. Use Take survey to add responses, Dashboard to view trends, and Export PDF report to generate a report. Local responses are stored in `wellbeing.db`.

## Deploy to Vercel
This repo includes `vercel.json` for a Flask serverless deployment. Import this GitHub repository in Vercel, keep the project root as `./`, and deploy. After deployment test `/`, `/survey`, `/dashboard`, `/report.pdf`, and `/health`.

### Important: survey data persistence
Vercel serverless functions have a temporary filesystem. For the online demo, the app uses `/tmp/wellbeing.db`; data may disappear or be isolated between instances and should **not** be treated as a permanent shared survey database. For a real community survey, configure a persistent managed database and adapt the database connection before collecting real responses. Do not enter names or sensitive personal information. Results are self-reported and do not prove causation.

## Render alternative
The included `Procfile` and `render.yaml` can be used as an alternative deployment path. Free hosting storage may also reset, so verify persistence before using it for a real study.
