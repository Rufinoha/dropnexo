#!/usr/bin/env python3
"""
Renova links temporários de imagens Bling (tenants com modo_imagem=link).

Uso:
  python scripts/bling_revalidar_imagens.py
  python scripts/bling_revalidar_imagens.py --tenant-id 1
  python scripts/bling_revalidar_imagens.py --dias 3 --limite 50

Agendar na madrugada (ex.: 03:15):
  see __doc/deploy/dropnexo-bling-imagens.timer.example
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
from api.bling.imagens_revalidar import revalidar_todos
from global_utils import Var_ConectarBanco


def main() -> int:
    parser = argparse.ArgumentParser(description="Revalida links de imagens Bling (modo link)")
    parser.add_argument("--tenant-id", type=int, help="Tenant específico")
    parser.add_argument("--dias", type=int, default=3, help="Antecedência em dias (default 3)")
    parser.add_argument("--limite", type=int, help="Máx. produtos por tenant")
    parser.add_argument("--pausa", type=float, default=0.4, help="Pausa entre produtos (s)")
    args = parser.parse_args()

    if not bling_configurado():
        print("Configure BLING_CLIENT_ID e BLING_CLIENT_SECRET no .env", file=sys.stderr)
        return 1

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        resultados = revalidar_todos(
            cur,
            id_tenant=args.tenant_id,
            dias_antecedencia=args.dias,
            limite_por_tenant=args.limite,
            pausa_s=args.pausa,
        )
        conn.commit()
    finally:
        conn.close()

    if not resultados:
        print("Nenhum tenant com modo_imagem=link.")
        return 0

    falhas = 0
    for item in resultados:
        print(json.dumps(item, ensure_ascii=False, default=str))
        if item.get("erros"):
            falhas += 1
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
