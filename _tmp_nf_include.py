from pathlib import Path

p = Path("vendedor/notas/templates/frm_vd_notas.html")
text = p.read_text(encoding="utf-8")
start = text.find('  <form id="nf_aba_parametros"')
end = text.find('  <div id="nf_modal"')
if start < 0 or end < 0:
    raise SystemExit(f"markers {start} {end}")
text = text[:start] + '  {% include "_nf_aba_parametros.html" %}\n\n' + text[end:]
p.write_text(text, encoding="utf-8")
print("ok", start, end)
