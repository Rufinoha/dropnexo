#!/usr/bin/env python3
"""Verifica se o .env está pronto para integração Mercado Pago."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from api.mercadopago.cliente import mp_configurado, redirect_uri_oauth
from global_utils import obter_base_url


def main() -> int:
    print("=== DropNexo — verificação Mercado Pago ===\n")
    ok = True

    cid = (os.getenv("MP_CLIENT_ID") or "").strip()
    secret = (os.getenv("MP_CLIENT_SECRET") or "").strip()
    if mp_configurado():
        print(f"MP_CLIENT_ID:     {cid[:8]}… ({len(cid)} chars)")
        print(f"MP_CLIENT_SECRET: {'*' * min(12, len(secret))} ({len(secret)} chars)")
    else:
        print("ERRO: MP_CLIENT_ID e/ou MP_CLIENT_SECRET ausentes no .env")
        ok = False

    base = obter_base_url()
    print(f"\nBASE ativa:         {base}")
    print(f"Redirect OAuth:     {redirect_uri_oauth()}")
    print(f"Webhook:            {base.rstrip('/')}/api/integracoes/mercadopago/webhook")

    modo = (os.getenv("MODO_PRODUCAO") or "false").strip().lower()
    print(f"MODO_PRODUCAO:      {modo}")

    if "127.0.0.1" in base or "localhost" in base:
        print(
            "\nAVISO: URL local. OAuth pode funcionar, mas o webhook do MP precisa de URL pública "
            "(ngrok + BASE_HOM ajustado)."
        )

    print("\nPróximos passos:")
    print("  1. Cadastre Redirect e Webhook no painel MP (URLs acima)")
    print("  2. Rode SQL 060 e 061 no PostgreSQL")
    print("  3. Reinicie a app")
    print("  4. Login como FORNECEDOR > Integracoes > Opcoes financeiras > Mercado Pago")
    print("  5. Conectar conta → testar pedido como VENDEDOR")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
