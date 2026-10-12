# Youth Digital Well-being Analyzer

A software-only Community Engagement Project (CEP) on **Impact of Mobile Phones on Youth**. Built with Flask, SQLite, Chart.js and ReportLab.

## Product features

- Responsive project landing page and accessible anonymous survey.
- Server-side allow-list validation, numeric range checks, request-size limit and CSRF protection.
- Public dashboard with aggregate screen-time, study-time and sleep metrics.
- Visual breakdowns by primary phone use, perceived impact and age group.
- Contextual discussion prompts that avoid presenting the survey as a diagnosis.
- PDF report export and health-check endpoint.
- CSV export protected by an admin login; raw notes/comments are not included in exports.
- Basic security headers, secure/HTTP-only session cookies and custom error pages.
- Local SQLite storage for development and classroom demonstrations.

## Run locally on macOS

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export ADMIN_PASSWORD="choose-a-strong-local-password"
python app.py
```

Open http://127.0.0.1:5000. Use **Take survey** to add a response, **Dashboard** to view aggregated trends, and **Export PDF report** to create a report. The local database is `wellbeing.db`.

## Deploy to Vercel

1. Import this GitHub repository in Vercel and deploy from the repository root.
2. In **Project → Settings → Environment Variables**, add:
   - `SECRET_KEY`: a long random secret (generate one locally; never commit it).
   - `ADMIN_PASSWORD`: a strong, unique password for the raw CSV export.
3. Redeploy after adding environment variables.
4. Test `/`, `/survey`, `/dashboard`, `/report.pdf`, `/export.csv` (should redirect to admin login when signed out), and `/health`.

### Important data-storage limitation

Vercel serverless filesystem storage is temporary. This demo uses `/tmp/wellbeing.db` on Vercel, so responses can be isolated between instances or disappear. Do **not** use this configuration as the permanent database for an actual community study. Before collecting real responses, connect a managed persistent database and update the database layer accordingly.

## Privacy and responsible use

- The survey does not request names, phone numbers or email addresses. Do not include identifying details in the optional comment.
- Public charts and the PDF contain aggregated summaries. CSV export requires the admin password and excludes optional comments.
- Do not share the admin password or put secrets in GitHub. Use HTTPS in deployment.
- Follow school/college project rules and any required consent process, especially when collecting information from minors.
- Results are self-reported, may be affected by sampling bias, and do not prove that phone use causes a change in sleep, study or well-being. This is not a medical or diagnostic tool.

## Render alternative

The included `Procfile` and `render.yaml` provide an alternative host configuration. Verify persistent disk/database settings before using any hosted instance for real research.
