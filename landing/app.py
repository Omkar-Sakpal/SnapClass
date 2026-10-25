import os
from flask import Flask, render_template_string

app = Flask(__name__)
APP_URL = os.environ.get("SNAPCLASS_APP_URL", "https://YOUR-STREAMLIT-APP.streamlit.app")

PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SnapClass — Smarter Attendance</title>
<style>
:root{--ink:#14231f;--green:#087f5b;--mint:#e7f6ef;--line:#dce8e2}
*{box-sizing:border-box}body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink);background:#fbfdfb}
nav{display:flex;justify-content:space-between;align-items:center;padding:22px max(6vw,24px);border-bottom:1px solid var(--line);background:#fff}
.logo{font-weight:800;font-size:1.25rem}.logo span{color:var(--green)}
nav a,.btn{color:var(--green);text-decoration:none;font-weight:700}
.hero{max-width:1120px;margin:auto;padding:88px 24px 64px;display:grid;grid-template-columns:1.15fr .85fr;gap:52px;align-items:center}
.eyebrow{color:var(--green);font-weight:800;letter-spacing:.12em;text-transform:uppercase;font-size:.8rem}
h1{font-size:clamp(2.6rem,5vw,4.6rem);line-height:1.03;letter-spacing:-.05em;margin:18px 0}
p{color:#53645e;line-height:1.7;font-size:1.06rem}.actions{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-top:28px}
.btn{display:inline-block;background:var(--green);color:#fff;padding:14px 20px;border-radius:12px}.sub{font-weight:700;color:#53645e;text-decoration:none}
.visual{background:linear-gradient(145deg,#e7f6ef,#f4faf6);border:1px solid var(--line);border-radius:28px;padding:26px;box-shadow:0 22px 60px #163c2712}
.card{background:white;border:1px solid var(--line);padding:20px;border-radius:18px;margin:12px 0}.metric{font-size:2rem;font-weight:800}.tag{display:inline-block;background:#e7f6ef;color:var(--green);padding:5px 9px;border-radius:999px;font-size:.8rem;font-weight:700}
.features{max-width:1120px;margin:0 auto;padding:24px;display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.feature{border:1px solid var(--line);border-radius:18px;padding:24px;background:#fff}.feature h3{margin-top:0}
footer{border-top:1px solid var(--line);margin-top:60px;padding:28px 24px;text-align:center;color:#64756e}
@media(max-width:760px){.hero{grid-template-columns:1fr;padding-top:54px}.features{grid-template-columns:1fr}nav{padding:18px 22px}}
</style></head>
<body>
<nav><div class="logo">Snap<span>Class</span></div><a href="{{ app_url }}">Open application ↗</a></nav>
<main>
<section class="hero">
<div><div class="eyebrow">Cloud student attendance</div><h1>Attendance that keeps your class moving.</h1>
<p>SnapClass is a cloud-based attendance demo for teachers and students. Manage subjects, enroll in classes, and review attendance from one simple workspace.</p>
<div class="actions"><a class="btn" href="{{ app_url }}">Launch SnapClass →</a><a class="sub" href="#features">Explore features ↓</a></div></div>
<div class="visual"><div class="card"><span class="tag">Teacher workspace</span><h3>Class overview</h3><div class="metric">92%</div><p>Example attendance summary</p></div><div class="card"><b>Subject management</b><p>Create classes and let students enroll with a subject code.</p></div><div class="card"><b>Attendance records</b><p>Save and review records in your connected cloud database.</p></div></div>
</section>
<section id="features" class="features"><div class="feature"><h3>🎓 Teacher dashboard</h3><p>Create subjects and record attendance for enrolled students.</p></div><div class="feature"><h3>📚 Student workspace</h3><p>Join a subject using its code and review attendance history.</p></div><div class="feature"><h3>☁️ Cloud-backed</h3><p>Supabase stores application records with authenticated access policies.</p></div></section>
</main><footer>SnapClass · Student attendance cloud demonstration</footer>
</body></html>
"""

@app.get("/")
def home():
    return render_template_string(PAGE, app_url=APP_URL)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
