#!/usr/bin/env python3
"""Reimporta pedido ML 2000019497243500 (tenant 348) após fix de truncamento."""
import os
import sys
import traceback

from dotenv import load_dotenv
import psycopg2

load_dotenv("/srv/dropnexo/.env")
os.chdir("/srv/dropnexo")
sys.path.insert(0, "/srv/dropnexo")

from api.mercado_livre.mercado_livre import api_request
from api.mercado_livre import pedidos_ml as pml

TENANT = 348
OID = "2000019497243500"
SHIP = "48501991258"

conn = psycopg2.connect(
    host=os.getenv("DB_HOST_PROD", "127.0.0.1"),
    port=os.getenv("DB_PORT_PROD", "5432"),
    dbname=os.getenv("DB_NAME_PROD", "bd_dropnexo"),
    user=os.getenv("DB_USER_PROD"),
    password=os.getenv("DB_PASSWORD_PROD") or os.getenv("DB_PASS_PROD"),
)
cur = conn.cursor()

# Evidência: complemento cru do ML vs limite da coluna
ship = api_request(cur, TENANT, "GET", f"/shipments/{SHIP}")
addr = (
    (ship or {}).get("receiver_address")
    or (((ship or {}).get("destination") or {}).get("shipping_address") if isinstance((ship or {}).get("destination"), dict) else None)
    or {}
)
comment = (addr.get("comment") or "").strip()
print("ML comment len=", len(comment))
print("ML comment=", repr(comment))

cur.execute(
    """
    SELECT character_maximum_length
      FROM information_schema.columns
     WHERE table_name='tbl_pedido' AND column_name='entrega_complemento'
    """
)
print("DB entrega_complemento varchar=", cur.fetchone()[0])

parsed = pml._entrega_de_shipment(ship)
print("parsed complemento len=", len(parsed.get("complemento") or ""), "val=", repr(parsed.get("complemento")))

# Estado antes
cur.execute(
    "SELECT id, numero, id_ml_pedido, entrega_complemento FROM tbl_pedido WHERE id_ml_pedido=%s AND id_tenant_vendedor=%s",
    (OID, TENANT),
)
print("ANTES:", cur.fetchall())

# Logs de erro_importar se existirem
for tbl in ("tbl_ml_webhook_log", "tbl_integracao_log", "tbl_log", "tbl_evento"):
    try:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_name=%s LIMIT 5
            """,
            (tbl,),
        )
        cols = [r[0] for r in cur.fetchall()]
        if cols:
            print(f"table {tbl} exists cols_sample={cols}")
    except Exception:
        conn.rollback()

print("\n=== IMPORT ===")
try:
    out = pml._importar_um_pedido_ml(cur, TENANT, OID)
    conn.commit()
    print("OK", out)
except Exception as e:
    conn.rollback()
    print("FAIL", type(e).__name__, e)
    traceback.print_exc()

cur.execute(
    """
    SELECT id, numero, id_ml_pedido, left(entrega_complemento,120), length(entrega_complemento),
           status_vendedor, criado_em
      FROM tbl_pedido
     WHERE id_ml_pedido=%s AND id_tenant_vendedor=%s
    """,
    (OID, TENANT),
)
print("DEPOIS:", cur.fetchall())
conn.close()
print("DONE")
