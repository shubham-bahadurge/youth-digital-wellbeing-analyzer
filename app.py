import os
import sqlite3
from datetime import datetime
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# Vercel's writable filesystem is temporary; use DATABASE_PATH for local/persistent hosts.
DATABASE = os.environ.get("DATABASE_PATH", "/tmp/wellbeing.db" if os.environ.get("VERCEL") else os.path.join(BASE_DIR, "wellbeing.db"))
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "development-only-change-me")

def connect_db():
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DATABASE) or ".", exist_ok=True)
    with connect_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
            age_group TEXT NOT NULL, screen_time REAL NOT NULL, study_hours REAL NOT NULL,
            sleep_hours REAL NOT NULL, primary_use TEXT NOT NULL,
            perceived_effect TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '')""")

def get_stats():
    with connect_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
        avg = conn.execute("SELECT AVG(screen_time) screen, AVG(study_hours) study, AVG(sleep_hours) sleep FROM responses").fetchone()
        by_use = conn.execute("SELECT primary_use label, COUNT(*) value FROM responses GROUP BY primary_use ORDER BY value DESC").fetchall()
        by_age = conn.execute("""SELECT age_group label, ROUND(AVG(screen_time),1) value FROM responses GROUP BY age_group
          ORDER BY CASE age_group WHEN 'Under 13' THEN 1 WHEN '13–15' THEN 2 WHEN '16–18' THEN 3 WHEN '19–24' THEN 4 ELSE 5 END""").fetchall()
        effects = conn.execute("SELECT perceived_effect label, COUNT(*) value FROM responses GROUP BY perceived_effect ORDER BY value DESC").fetchall()
    return {"total": total, "avg_screen": round(avg["screen"] or 0, 1), "avg_study": round(avg["study"] or 0, 1),
            "avg_sleep": round(avg["sleep"] or 0, 1), "by_use": [dict(x) for x in by_use],
            "by_age": [dict(x) for x in by_age], "effects": [dict(x) for x in effects]}

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/survey", methods=["GET", "POST"])
def survey():
    if request.method == "POST":
        try:
            age = request.form["age_group"]
            screen, study, sleep = (float(request.form[k]) for k in ("screen_time", "study_hours", "sleep_hours"))
            use, effect = request.form["primary_use"], request.form["perceived_effect"]
            notes = request.form.get("notes", "").strip()[:300]
            if age not in ["Under 13", "13–15", "16–18", "19–24", "25 or older"]: raise ValueError()
            if not all(0 <= n <= 24 for n in (screen, study, sleep)): raise ValueError()
            if use not in ["Education", "Social media", "Gaming", "Communication", "Entertainment", "Other"]: raise ValueError()
            if effect not in ["Mostly positive", "Mixed", "Mostly negative", "Not sure"]: raise ValueError()
            with connect_db() as conn:
                conn.execute("INSERT INTO responses (created_at,age_group,screen_time,study_hours,sleep_hours,primary_use,perceived_effect,notes) VALUES (?,?,?,?,?,?,?,?)",
                    (datetime.now().isoformat(timespec="seconds"), age, screen, study, sleep, use, effect, notes))
            flash("Thank you! Your anonymous response has been recorded.", "success")
            return redirect(url_for("survey"))
        except (ValueError, KeyError):
            flash("Please check your answers and enter hours from 0 to 24.", "error")
    return render_template("survey.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", stats=get_stats())

@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())

@app.route("/report.pdf")
def report_pdf():
    stats, output = get_stats(), BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=42)
    styles = getSampleStyleSheet()
    story = [Paragraph("Youth Digital Well-being Analyzer", styles["Title"]),
      Paragraph("CEP Project: Impact of Mobile Phones on Youth", styles["Heading2"]),
      Paragraph("Survey summary generated " + datetime.now().strftime("%d %b %Y, %I:%M %p"), styles["Normal"]),
      Spacer(1, 16), Paragraph("Overview", styles["Heading2"]),
      Paragraph(f"Total anonymous responses: {stats['total']}", styles["Normal"]),
      Paragraph(f"Average daily screen time: {stats['avg_screen']} hours", styles["Normal"]),
      Paragraph(f"Average daily study time: {stats['avg_study']} hours", styles["Normal"]),
      Paragraph(f"Average sleep: {stats['avg_sleep']} hours", styles["Normal"]), Spacer(1, 12),
      Paragraph("Primary phone use", styles["Heading2"])]
    for heading, key in (("Primary phone use", "by_use"), ("Perceived impact", "effects")):
        if heading != "Primary phone use": story.append(Paragraph(heading, styles["Heading2"]))
        rows = [["Category", "Responses"]] + [[x["label"], str(x["value"])] for x in stats[key]]
        if len(rows) == 1: rows.append(["No responses yet", "0"])
        table = Table(rows, colWidths=[300, 120])
        table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#5146c8")),
          ("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#d1d5db")),
          ("PADDING",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"TOP")]))
        story.extend([table, Spacer(1, 12)])
    story.append(Paragraph("These self-reported results describe this survey sample only. They do not prove that phone use causes changes in sleep, study habits or well-being.", styles["Italic"]))
    doc.build(story)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="youth-digital-wellbeing-report.pdf", mimetype="application/pdf")

@app.route("/health")
def health():
    return {"status": "ok"}

with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
