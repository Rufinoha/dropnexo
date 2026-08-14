# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
import psycopg2

TABELAS = [
    "tbl_armazem_fornecedor",
    "tbl_armazem_parametros",
    "tbl_armazem_movimentacao",
]


def fix(suf: str) -> None:
    dbname = os.getenv(f"DB_NAME_{suf}")
    host = os.getenv(f"DB_HOST_{suf}", "127.0.0.1")
    port = os.getenv(f"DB_PORT_{suf}", "5432")
    app_user = os.getenv(f"DB_USER_{suf}")
    user = "postgres"
    pwd = os.getenv("DB_PASSWORD_DEV")
    print(f"=== {suf} as {user}@{host}/{dbname} owner={app_user} ===")
    conn = psycopg2.connect(dbname=dbname, user=user, password=pwd, host=host, port=port)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        "ALTER TABLE tbl_armazem_fornecedor ADD COLUMN IF NOT EXISTS logo_caminho VARCHAR(500)"
    )
    print("logo_caminho ok")
    for t in TABELAS:
        try:
            cur.execute(f"ALTER TABLE {t} OWNER TO {app_user}")
            print(f"owner {t} ok")
        except Exception as e:
            print(f"owner {t} fail: {e}")
    for t in TABELAS:
        seq = f"{t}_id_seq"
        try:
            cur.execute(f"ALTER SEQUENCE IF EXISTS {seq} OWNER TO {app_user}")
            print(f"seq {seq} ok")
        except Exception as e:
            print(f"seq {seq} fail: {e}")
    # verify as app user
    conn.close()
    app_pwd = os.getenv(f"DB_PASSWORD_{suf}")
    conn2 = psycopg2.connect(
        dbname=dbname, user=app_user, password=app_pwd, host=host, port=port
    )
    cur2 = conn2.cursor()
    cur2.execute("SELECT logo_caminho FROM tbl_armazem_fornecedor LIMIT 1")
    print("app select logo_caminho ok")
    try:
        cur2.execute(
            "ALTER TABLE tbl_armazem_fornecedor ADD COLUMN IF NOT EXISTS logo_caminho VARCHAR(500)"
        )
        conn2.commit()
        print("app alter ok (is owner)")
    except Exception as e:
        conn2.rollback()
        print(f"app alter fail: {e}")
    conn2.close()


for s in ("DEV", "PROD"):
    try:
        fix(s)
    except Exception as e:
        print(f"ERRO {s}: {e}")
