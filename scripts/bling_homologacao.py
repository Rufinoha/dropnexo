#!/usr/bin/env python3
"""
Executa o teste de homologação Bling (aba Homologação → Execução).

Pré-requisito: conta Bling conectada no DropNexo (OAuth) ou tokens informados.

Uso (na raiz do projeto):
  python scripts/bling_homologacao.py --tenant-id 1

Sem --tenant-id o script não renova o token: o refresh novo precisa ser gravado na conta conectada.
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

from api.bling.cliente import bling_configurado, obter_access_token_valido
from api.bling.homologacao import executar_homologacao


def _tokens_por_tenant(id_tenant: int) -> str:
    return obter_access_token_valido(id_tenant)


def main() -> int:
    parser = argparse.ArgumentParser(description="Homologação Bling API v3 — produtos")
    parser.add_argument("--tenant-id", type=int, help="ID do tenant com Bling conectado")
    parser.add_argument("--access-token", help="Access token OAuth (alternativa ao tenant)")
    parser.add_argument(
        "--refresh-token",
        help="Não usa este valor para renovar. A renovação só grava com --tenant-id.",
    )
    parser.add_argument("--debug", action="store_true", help="Exibe payload GET e respostas de erro completas")
    args = parser.parse_args()

    if not bling_configurado():
        print("Erro: configure BLING_CLIENT_ID e BLING_CLIENT_SECRET no .env", file=sys.stderr)
        return 1

    access = (args.access_token or os.getenv("BLING_HOMOLOG_ACCESS_TOKEN") or "").strip()
    refresh_informado = bool((args.refresh_token or os.getenv("BLING_HOMOLOG_REFRESH_TOKEN") or "").strip())

    if args.tenant_id:
        access = _tokens_por_tenant(args.tenant_id)

    if not access:
        print(
            "Erro: informe --tenant-id ou --access-token (conecte o Bling em Integrações antes).",
            file=sys.stderr,
        )
        return 1

    def refresh_fn() -> str:
        if not args.tenant_id:
            raise RuntimeError(
                "Homologação sem --tenant-id não renova o token: o refresh novo ficaria só na memória. "
                "Use --tenant-id da conta conectada."
            )
        novo = obter_access_token_valido(int(args.tenant_id), forcar=True)
        print("  ↻ Token renovado e gravado")
        return novo

    print("Iniciando homologação Bling (5 passos, máx. ~10s)...")
    resultado = executar_homologacao(
        access,
        refresh_token_fn=refresh_fn if (args.tenant_id or refresh_informado) else None,
        verbose=args.debug,
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
