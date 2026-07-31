#!/usr/bin/env python
"""Job diário financeiro — vencidas, avisos, rebaixamento boleto (7 dias úteis), renovações.

Uso (cron):
  python scripts/financeiro_job_diario.py

Ou HTTP:
  POST /api/financeiro/job-diario
  Header: X-Cron-Token: <CRON_SECRET ou EFI_WEBHOOK_SECRET>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from global_utils import Var_ConectarBanco  # noqa: E402
from sistema.financeiro.cobranca import job_financeiro_diario  # noqa: E402


def main() -> int:
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        res = job_financeiro_diario(cur)
        conn.commit()
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        conn.rollback()
        print("ERRO:", e, file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
