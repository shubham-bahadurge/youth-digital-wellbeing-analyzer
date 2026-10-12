import csv
import io
import json
import math
import os
import secrets
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from flask import Flask, abort, flash, jsonify, make_response, redirect, render_template, request, send_file, session, url_for
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.environ.get(
    "DATABASE_PATH",
    "/tmp/wellbeing.db" if os.environ.get("VERCEL") else os.path.join(BASE_DIR, "wellbeing.db"),
)
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local-demo-key-change-before-production")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("VERCEL")),
    MAX_CONTENT_LENGTH=16 * 1024,
)

AGE_GROUPS = ["Under 13", "13–15", "16–18", "19–24", "25 or older"]
PHONE_USES = ["Education", "Social media", "Gaming", "Communication", "Entertainment", "Other"]
EFFECTS = ["Mostly positive", "Mixed", "Mostly negative", "Not sure"]


def connect_db():
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DATABASE) or ".", exist_ok=True)
    with connect_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            age_group TEXT NOT NULL,
            screen_time REAL NOT NULL CHECK(screen_time BETWEEN 0 AND 24),
            study_hours REAL NOT NULL CHECK(study_hours BETWEEN 0 AND 24),
            sleep_hours REAL NOT NULL CHECK(sleep_hours BETWEEN 0 AND 24),
            primary_use TEXT NOT NULL,
            perceived_effect TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT ''
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_responses_created_at ON responses(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_responses_age_group ON responses(age_group)")


def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


@app.context_processor
def inject_template_helpers():
    return {"csrf_token": csrf_token}


@app.before_request
def verify_csrf():
    if request.method == "POST":
        submitted = request.form.get("_csrf_token", "")
        expected = session.get("_csrf_token", "")
        if not submitted or not expected or not secrets.compare_digest(submitted, expected):
            abort(400, description="Your form session expired. Refresh the page and try again.")


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cache-Control", "no-store" if request.path in ("/survey", "/dashboard", "/api/stats") else "public, max-age=0, must-revalidate")
    return response


def safe_number(value):
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 24:
        raise ValueError("Hours must be between 0 and 24.")
    return number


def get_stats():
    with connect_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
        avg = conn.execute(
            "SELECT AVG(screen_time) screen, AVG(study_hours) study, AVG(sleep_hours) sleep FROM responses"
        ).fetchone()
        by_use = conn.execute(
            "SELECT primary_use label, COUNT(*) value FROM responses GROUP BY primary_use ORDER BY value DESC, label"
        ).fetchall()
        by_age = conn.execute("""SELECT age_group label, ROUND(AVG(screen_time), 1) value,
            COUNT(*) count FROM responses GROUP BY age_group
            ORDER BY CASE age_group WHEN 'Under 13' THEN 1 WHEN '13–15' THEN 2
            WHEN '16–18' THEN 3 WHEN '19–24' THEN 4 ELSE 5 END""").fetchall()
        effects = conn.execute(
            "SELECT perceived_effect label, COUNT(*) value FROM responses GROUP BY perceived_effect ORDER BY value DESC, label"
        ).fetchall()
        recent = conn.execute(
            "SELECT created_at, age_group, screen_time, study_hours, sleep_hours, primary_use, perceived_effect "
            "FROM responses ORDER BY id DESC LIMIT 5"
        ).fetchall()
        last_30_days = conn.execute(
            "SELECT COUNT(*) FROM responses WHERE created_at >= ?",
            ((datetime.now() - timedelta(days=30)).isoformat(timespec="seconds"),),
        ).fetchone()[0]
    return {
        "total": total,
        "avg_screen": round(avg["screen"] or 0, 1),
        "avg_study": round(avg["study"] or 0, 1),
        "avg_sleep": round(avg["sleep"] or 0, 1),
        "by_use": [dict(x) for x in by_use],
        "by_age": [dict(x) for x in by_age],
        "effects": [dict(x) for x in effects],
        "recent": [dict(x) for x in recent],
        "last_30_days": last_30_days,
    }


def build_insights(stats):
    tips = []
    if stats["total"] == 0:
        return [
            {"title": "Start with a sample", "text": "Collect a few anonymous responses to reveal community-level patterns."},
            {"title": "Keep the context", "text": "This is a learning survey, not a medical or diagnostic assessment."},
        ]
    if stats["avg_screen"] >= 6:
        tips.append({"title": "Explore screen-time routines", "text": "The sample average is relatively high. Discuss purposeful use and regular breaks without judging individuals."})
    else:
        tips.append({"title": "Look beyond the average", "text": "Compare phone-use purposes and age groups; an average cannot describe every respondent."})
    if stats["avg_sleep"] < 7:
        tips.append({"title": "Discuss sleep routines", "text": "The sample reports less than seven hours on average. Explore routines and school schedules; this does not establish a cause."})
    else:
        tips.append({"title": "Protect consistent routines", "text": "Consider how respondents balance sleep, study, connection and recreation."})
    tips.append({"title": "Treat findings carefully", "text": "Responses are self-reported and may not represent all young people. Correlation is not proof of causation."})
    return tips[:3]


@app.route("/")
def home():
    stats = get_stats()
    return render_template("index.html", stats=stats)


@app.route("/survey", methods=["GET", "POST"])
def survey():
    if request.method == "POST":
        try:
            age = request.form.get("age_group", "")
            screen = safe_number(request.form.get("screen_time", ""))
            study = safe_number(request.form.get("study_hours", ""))
            sleep = safe_number(request.form.get("sleep_hours", ""))
            use = request.form.get("primary_use", "")
            effect = request.form.get("perceived_effect", "")
            notes = request.form.get("notes", "").strip()[:300]
            if age not in AGE_GROUPS or use not in PHONE_USES or effect not in EFFECTS:
                raise ValueError("Please choose a valid option for each question.")
            with connect_db() as conn:
                conn.execute(
                    """INSERT INTO responses
                    (created_at, age_group, screen_time, study_hours, sleep_hours, primary_use, perceived_effect, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (datetime.now().isoformat(timespec="seconds"), age, screen, study, sleep, use, effect, notes),
                )
            session.pop("_csrf_token", None)
            flash("Thank you! Your anonymous response has been recorded.", "success")
            return redirect(url_for("survey"))
        except (ValueError, TypeError):
            flash("Please check your answers. Hours must be valid numbers from 0 to 24.", "error")
    return render_template("survey.html")


@app.route("/dashboard")
def dashboard():
    stats = get_stats()
    return render_template("dashboard.html", stats=stats, insights=build_insights(stats))


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    configured_password = os.environ.get("ADMIN_PASSWORD", "")
    if not configured_password:
        return render_template("admin_login.html", unavailable=True), 503
    if request.method == "POST":
        password = request.form.get("password", "")
        if secrets.compare_digest(password, configured_password):
            session["admin_authenticated"] = True
            flash("Admin session started.", "success")
            return redirect(url_for("export_csv"))
        flash("Password not recognised. Please try again.", "error")
    return render_template("admin_login.html", unavailable=False)


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin_authenticated", None)
    flash("You have been signed out.", "success")
    return redirect(url_for("dashboard"))


@app.route("/export.csv")
def export_csv():
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin_login"))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Submitted at", "Age group", "Screen time hours/day", "Study hours/day",
                     "Sleep hours/night", "Primary phone use", "Perceived effect"])
    with connect_db() as conn:
        rows = conn.execute(
            "SELECT created_at, age_group, screen_time, study_hours, sleep_hours, primary_use, perceived_effect "
            "FROM responses ORDER BY id ASC"
        ).fetchall()
    for row in rows:
        writer.writerow(list(row))
    response = make_response("\ufeff" + output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = 'attachment; filename="youth-wellbeing-responses.csv"'
    return response


@app.route("/report.pdf")
def report_pdf():
    stats, output = get_stats(), io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=42)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Youth Digital Well-being Analyzer", styles["Title"]),
        Paragraph("CEP Project: Impact of Mobile Phones on Youth", styles["Heading2"]),
        Paragraph("Survey summary generated " + datetime.now().strftime("%d %b %Y, %I:%M %p"), styles["Normal"]),
        Spacer(1, 16), Paragraph("Overview", styles["Heading2"]),
        Paragraph("Total anonymous responses: " + str(stats["total"]), styles["Normal"]),
        Paragraph("Responses in the last 30 days: " + str(stats["last_30_days"]), styles["Normal"]),
        Paragraph("Average daily screen time: " + str(stats["avg_screen"]) + " hours", styles["Normal"]),
        Paragraph("Average daily study time: " + str(stats["avg_study"]) + " hours", styles["Normal"]),
        Paragraph("Average sleep: " + str(stats["avg_sleep"]) + " hours", styles["Normal"]),
        Spacer(1, 12),
    ]
    for heading, key in (("Primary phone use", "by_use"), ("Perceived impact", "effects")):
        story.append(Paragraph(heading, styles["Heading2"]))
        rows = [["Category", "Responses"]] + [[x["label"], str(x["value"])] for x in stats[key]]
        if len(rows) == 1:
            rows.append(["No responses yet", "0"])
        table = Table(rows, colWidths=[300, 120])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5146c8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
            ("PADDING", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.extend([table, Spacer(1, 12)])
    story.append(Paragraph(
        "Method note: These self-reported results describe this survey sample only. They do not prove that phone use causes changes in sleep, study habits or well-being.",
        styles["Italic"],
    ))
    doc.build(story)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="youth-digital-wellbeing-report.pdf", mimetype="application/pdf")


@app.route("/health")
def health():
    try:
        with connect_db() as conn:
            conn.execute("SELECT 1")
        return jsonify({"status": "ok", "database": "reachable"}), 200
    except sqlite3.Error:
        return jsonify({"status": "error", "database": "unavailable"}), 503


@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", code=400, message=getattr(error, "description", "Please refresh and try again.")), 400


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="The page you requested could not be found."), 404


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
