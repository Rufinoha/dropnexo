from pathlib import Path

root = Path(__file__).resolve().parent / "templates"
repls = [
    ("{% block head %}", "{% block head_extra %}"),
    ("{% block page_scripts %}", "{% block page_js %}"),
    ("url_for('static', filename='style/Cnfse.css')", "url_for('nfse.static', filename='style/Cnfse.css')"),
    ("url_for('static', filename='script/Snfse_notas.js')", "url_for('nfse.static', filename='script/Snfse_notas.js')"),
    ("url_for('static', filename='script/Snfse_dashboard.js')", "url_for('nfse.static', filename='script/Snfse_dashboard.js')"),
    ("url_for('static', filename='script/Snfse_parametros.js')", "url_for('nfse.static', filename='script/Snfse_parametros.js')"),
    ("url_for('static', filename='script/Snfse_nota_apoio.js')", "url_for('nfse.static', filename='script/Snfse_nota_apoio.js')"),
    ("· H74 Painel", "· DropNexo"),
]
for p in root.glob("frm_nfse_*.html"):
    t = p.read_text(encoding="utf-8")
    for a, b in repls:
        t = t.replace(a, b)
    p.write_text(t, encoding="utf-8")
    print("ok", p.name)
