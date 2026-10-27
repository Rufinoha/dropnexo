# -*- coding: utf-8 -*-
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

vals = {}
with open(".env", "rb") as f:
    raw = f.read()
for enc in ("utf-8", "cp1252", "latin-1"):
    try:
        text = raw.decode(enc)
        print("ENV_ENCODING", enc)
        break
    except Exception as e:
        print("fail", enc, e)
else:
    text = raw.decode("latin-1")

for line in text.splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    vals[k.strip()] = v.strip().strip('"').strip("'")

import psycopg2

kw = dict(
    host=vals.get("DB_HOST_PROD"),
    port=vals.get("DB_PORT_PROD"),
    dbname=vals.get("DB_NAME_PROD"),
    user=vals.get("DB_USER_PROD"),
    password=vals.get("DB_PASSWORD_PROD"),
    connect_timeout=15,
)
print(
    "HOST",
    kw["host"],
    "DB",
    kw["dbname"],
    "USER",
    kw["user"],
    "PWD_LEN",
    len(kw["password"] or ""),
)
p = kw["password"] or ""
print("PWD_NONASCII", [hex(ord(c)) for c in p if ord(c) > 127][:10])

conn = psycopg2.connect(**kw)
cur = conn.cursor()
schema = vals.get("DB_SCHEMA_PROD") or "public"
cur.execute(f"SET search_path TO {schema}")
cur.execute(
    """
SELECT f.id, f.id_tenant, f.referencia, f.status, f.efi_charge_id, f.forma_pagamento,
       f.valor_centavos, f.pago_em, f.vencimento_em, t.nome
FROM tbl_fatura f
LEFT JOIN tbl_tenant t ON t.id = f.id_tenant
WHERE f.efi_charge_id = %s
   OR (f.referencia = %s AND f.valor_centavos = 7900)
ORDER BY f.id DESC LIMIT 10
""",
    ("1080311510", "2026-10"),
)
rows = cur.fetchall()
print("FATURAS", len(rows))
for r in rows:
    print(r)

try:
    cur.execute(
        """
    SELECT id, operacao, ok, efi_charge_id, criado_em
    FROM tbl_efi_log
    WHERE efi_charge_id = %s
    ORDER BY id DESC LIMIT 20
    """,
        ("1080311510",),
    )
    logs = cur.fetchall()
    print("LOGS", len(logs))
    for r in logs:
        print(r)
except Exception as e:
    print("LOG_ERR", e)

conn.close()
