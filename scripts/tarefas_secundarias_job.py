#!/usr/bin/env python
"""Job de tarefas secundárias (cache ML/TikTok/Amazon + sync XML Dropshipping).

Agenda: dia + hora (America/Sao_Paulo), janela de 60 minutos.
Defaults: domingo ML 02:00 · TikTok 03:00 · Amazon 04:00 · XML sync diário 06:00
(editáveis em Configurações → Tarefas secundárias).

Cron recomendado (a cada hora):
  5 * * * * cd /path/app && python scripts/tarefas_secundarias_job.py

Uso:
  python scripts/tarefas_secundarias_job.py
  python scripts/tarefas_secundarias_job.py --force
  python scripts/tarefas_secundarias_job.py --codigo tiktok_categorias_cache --force

HTTP:
  POST /api/tarefas-secundarias/job
  Header: X-Cron-Token: <CRON_SECRET ou EFI_WEBHOOK_SECRET>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from global_utils import Var_ConectarBanco  # noqa: E402
from sistema.tarefas_secundarias.servico import (  # noqa: E402
    executar_tarefa,
    executar_tarefas_agendadas,
    garantir_tabelas_tarefas,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--force",
        action="store_true",
        help="Executa mesmo fora do dia/hora agendados",
    )
    ap.add_argument(
        "--codigo",
        default="",
        help="Código da tarefa (vazio = todas as agendadas para agora)",
    )
    args = ap.parse_args()

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabelas_tarefas(cur)
        if args.codigo:
            res = executar_tarefa(
                cur,
                args.codigo,
                disparado_por="cron",
                forcar=bool(args.force),
                conn=conn,
            )
        else:
            res = executar_tarefas_agendadas(
                cur,
                disparado_por="cron",
                forcar=bool(args.force),
                conn=conn,
            )
        conn.commit()
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
        return 0
    except Exception as e:
        conn.rollback()
        print("ERRO:", e, file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
