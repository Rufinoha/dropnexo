#!/usr/bin/env python3
"""
Executa o teste de homologação Bling (aba Homologação → Execução).

Pré-requisito: conta Bling conectada no DropNexo (OAuth) ou tokens informados.

Uso (na raiz do projeto):
  python scripts/bling_homologacao.py --tenant-id 1
  python scripts/bling_homologacao.py --access-token SEU_TOKEN --refresh-token SEU_REFRESH
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from api.bling.cliente import bling_configurado, obter_access_token_valido, renovar_access_token
from api.bling.homologacao import executar_homologacao
from api.bling.tokens import descriptografar_token
from global_utils import Var_ConectarBanco


def _tokens_por_tenant(id_tenant: int) -> tuple[str, str | None]:
    access = obter_access_token_valido(id_tenant)
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT refresh_token_enc FROM tbl_integracao_bling WHERE id_tenant = %s AND status = 'conectado'",
            (id_tenant,),
        )
        row = cur.fetchone()
        refresh = descriptografar_token(row[0]) if row and row[0] else None
    finally:
        conn.close()
    return access, refresh


def main() -> int:
    parser = argparse.ArgumentParser(description="Homologação Bling API v3 — produtos")
    parser.add_argument("--tenant-id", type=int, help="ID do tenant com Bling conectado")
    parser.add_argument("--access-token", help="Access token OAuth (alternativa ao tenant)")
    parser.add_argument("--refresh-token", help="Refresh token (recomendado para passo de renovação)")
    args = parser.parse_args()

    if not bling_configurado():
        print("Erro: configure BLING_CLIENT_ID e BLING_CLIENT_SECRET no .env", file=sys.stderr)
        return 1

    access = (args.access_token or os.getenv("BLING_HOMOLOG_ACCESS_TOKEN") or "").strip()
    refresh = (args.refresh_token or os.getenv("BLING_HOMOLOG_REFRESH_TOKEN") or "").strip() or None

    if args.tenant_id:
        access, refresh_db = _tokens_por_tenant(args.tenant_id)
        refresh = refresh or refresh_db

    if not access:
        print(
            "Erro: informe --tenant-id ou --access-token (conecte o Bling em Integrações antes).",
            file=sys.stderr,
        )
        return 1

    refresh_holder = {"token": refresh}

    def refresh_fn() -> str:
        rt = refresh_holder["token"]
        if not rt:
            raise RuntimeError("Access token expirou e não há refresh_token. Reconecte o Bling.")
        payload = renovar_access_token(rt)
        refresh_holder["token"] = payload.get("refresh_token") or rt
        novo = payload["access_token"]
        print("  ↻ Token renovado via refresh_token")
        return novo

    print("Iniciando homologação Bling (5 passos, ~8–10s)...")
    resultado = executar_homologacao(
        access,
        refresh_token_fn=refresh_fn if refresh else None,
    )

    for p in resultado.passos:
        icone = "OK" if p.ok else "ERRO"
        print(f"  [{icone}] {p.ordem}. {p.metodo} {p.url} → {p.status} — {p.resumo}")
        if p.detalhe and not p.ok:
            print(f"       {p.detalhe}")

    print()
    print(resultado.mensagem)
    print(json.dumps(resultado.to_dict(), ensure_ascii=False, indent=2))

    return 0 if resultado.sucesso else 1


if __name__ == "__main__":
    raise SystemExit(main())
