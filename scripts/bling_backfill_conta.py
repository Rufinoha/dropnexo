#!/usr/bin/env python3
"""
Backfill bling_conta_info (company_id, CNPJ) para tenants Bling já conectados.

Uso:
  python scripts/bling_backfill_conta.py --tenant-id 1
  python scripts/bling_backfill_conta.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from api.bling.cliente import bling_configurado
from api.bling.conta_empresa import backfill_contas_conectadas
from global_utils import Var_ConectarBanco


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill bling_conta_info via API Bling")
    parser.add_argument("--tenant-id", type=int, help="Tenant específico (ex.: 1 Trovarelli)")
    args = parser.parse_args()

    if not bling_configurado():
        print("Configure BLING_CLIENT_ID e BLING_CLIENT_SECRET no .env", file=sys.stderr)
        return 1

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        resultados = backfill_contas_conectadas(cur, id_tenant=args.tenant_id)
        conn.commit()
    finally:
        conn.close()

    for item in resultados:
        if item.get("ok"):
            print(f"OK tenant {item['id_tenant']}: {json.dumps(item.get('info') or {}, ensure_ascii=False)}")
        else:
            print(f"ERRO tenant {item['id_tenant']}: {item.get('erro')}", file=sys.stderr)

    if not resultados:
        print("Nenhum tenant pendente de backfill.")
    return 0 if all(r.get("ok") for r in resultados) else 1


if __name__ == "__main__":
    raise SystemExit(main())
