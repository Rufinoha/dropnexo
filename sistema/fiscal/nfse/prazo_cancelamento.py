"""Prazo de cancelamento da NFS-e no município de Louveira/SP.

Lei municipal 3.023/2025, art. 2º, § 5º: não se cancela a nota depois do
dia 15 do mês seguinte ao da emissão. O dia 15 ainda entra no prazo.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

_BRASILIA = timezone(timedelta(hours=-3))


def _dia_brasilia(valor: datetime | date) -> date:
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=_BRASILIA)
        return valor.astimezone(_BRASILIA).date()
    return valor


def limite_cancelamento_nfse(emissao: datetime | date) -> date:
    """Último dia em que o cancelamento ainda é permitido."""
    dia = _dia_brasilia(emissao)
    if dia.month == 12:
        return date(dia.year + 1, 1, 15)
    return date(dia.year, dia.month + 1, 15)


def motivo_bloqueio_cancelamento(
    emissao: datetime | date | None,
    agora: datetime | None = None,
) -> str | None:
    """None quando o cancelamento ainda cabe no prazo de Louveira."""
    if emissao is None:
        return (
            "Esta NFS-e não tem data de autorização gravada. "
            "Sem ela não dá para conferir o prazo de cancelamento de Louveira."
        )
    limite = limite_cancelamento_nfse(emissao)
    hoje = _dia_brasilia(agora or datetime.now(_BRASILIA))
    if hoje <= limite:
        return None
    emitida = _dia_brasilia(emissao)
    return (
        f"Esta NFS-e foi emitida em {emitida.strftime('%d/%m/%Y')}. "
        f"Em Louveira, a Lei 3.023/2025 permite cancelar só até o dia 15 do mês seguinte "
        f"— neste caso, até {limite.strftime('%d/%m/%Y')}. Esse prazo já passou."
    )
