#!/usr/bin/env python3
"""Testa revogação Bling para um tenant (diagnóstico de desconectar)."""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))

from api.bling.cliente import carregar_tokens_armazenados, revogar_tokens_bling
from global_utils import Var_ConectarBanco


def main() -> int:
    p = argparse.ArgumentParser(description="Diagnóstico revoke/uninstall Bling")
    p.add_argument("id_tenant", type=int, help="ID do tenant conectado ao Bling")
    p.add_argument(
        "--aplicar",
        action="store_true",
        help="Executa revoke de verdade (sem apagar tokens locais)",
    )
    args = p.parse_args()

    client_id = (os.getenv("BLING_CLIENT_ID") or "")[:12]
    print(f"BLING_CLIENT_ID prefix: {client_id or '(vazio)'}")

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        tokens = carregar_tokens_armazenados(cur, args.id_tenant)
    finally:
        conn.close()

    has_access = bool((tokens.get("access_token") or "").strip())
    has_refresh = bool((tokens.get("refresh_token") or "").strip())
    print(f"tokens: access={has_access} refresh={has_refresh}")
    if not has_access and not has_refresh:
        print("Sem tokens — reconecte no DropNexo antes de testar.")
        return 1

    if not args.aplicar:
        print("Dry-run. Use --aplicar para chamar POST /oauth/revoke no Bling.")
        return 0

    resultado = revogar_tokens_bling(
        access_token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
    )
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    return 0 if resultado.get("token_inativo") or resultado.get("instalacao_removida") else 2


if __name__ == "__main__":
    raise SystemExit(main())
