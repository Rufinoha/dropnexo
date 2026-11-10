"""Quem pode ver/usar NFS-e e NFe no DropNexo (fase de teste)."""
from __future__ import annotations

from flask import session

# Fase de teste: só estes tenants veem o menu Nota Fiscal.
TENANTS_NOTA_FISCAL_BETA = frozenset({1, 2})


def tenant_pode_nota_fiscal(id_tenant: int | None = None) -> bool:
    tid = id_tenant
    if tid is None:
        raw = session.get("id_tenant")
        tid = int(raw) if raw else None
    if not tid:
        return False
    if session.get("eh_desenvolvedor") and int(tid) in TENANTS_NOTA_FISCAL_BETA:
        return True
    return int(tid) in TENANTS_NOTA_FISCAL_BETA


def garantir_sessao_nfse() -> None:
    """Marca session.permite_nfse para o módulo portado do H74."""
    session["permite_nfse"] = bool(tenant_pode_nota_fiscal())
