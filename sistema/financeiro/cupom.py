# sistema/financeiro/cupom.py — cupons + preço por periodicidade
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

PERIODOS = {
    "mensal": {"meses": 1, "desconto_pct": 0, "rotulo": "Mensal"},
    "semestral": {"meses": 6, "desconto_pct": 10, "rotulo": "Semestral (−10%)"},
    "anual": {"meses": 12, "desconto_pct": 20, "rotulo": "Anual (−20%)"},
}


def normalizar_periodo(periodo: str | None) -> str:
    p = (periodo or "mensal").strip().lower()
    if p not in PERIODOS:
        raise ValueError("Periodicidade inválida. Use mensal, semestral ou anual.")
    return p


def normalizar_codigo(codigo: str | None) -> str:
    return "".join(c for c in (codigo or "").strip().upper() if c.isalnum() or c in "-_")


def _centavos(v: Decimal | float | int) -> int:
    return int(Decimal(str(v)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calcular_preco(
    valor_mensal_centavos: int,
    periodo: str,
    *,
    cupom: dict | None = None,
) -> dict:
    """
    1) mensalidade × meses
    2) desconto do período (semestral 10% / anual 20%)
    3) cupom sobre o valor já com desconto do período
    """
    p = normalizar_periodo(periodo)
    meta = PERIODOS[p]
    meses = int(meta["meses"])
    mensal = max(0, int(valor_mensal_centavos or 0))
    cheio = mensal * meses
    desc_periodo = _centavos(Decimal(cheio) * Decimal(meta["desconto_pct"]) / Decimal(100))
    base = max(0, cheio - desc_periodo)

    desc_cupom = 0
    cupom_info = None
    if cupom:
        tipo = (cupom.get("tipo_desconto") or "").lower()
        valor = Decimal(str(cupom.get("valor_desconto") or 0))
        if tipo == "percentual":
            pct = min(Decimal("100"), max(Decimal("0"), valor))
            desc_cupom = _centavos(Decimal(base) * pct / Decimal(100))
        elif tipo == "fixo":
            desc_cupom = min(base, _centavos(valor * Decimal(100)))
        else:
            raise ValueError("Tipo de desconto do cupom inválido.")
        desc_cupom = max(0, min(base, desc_cupom))
        cupom_info = {
            "id": cupom.get("id"),
            "codigo": cupom.get("codigo"),
            "tipo_desconto": tipo,
            "valor_desconto": float(valor),
            "periodo": cupom.get("periodo"),
        }

    final = max(0, base - desc_cupom)
    return {
        "periodo": p,
        "periodo_rotulo": meta["rotulo"],
        "meses_cobertos": meses,
        "desconto_periodo_pct": meta["desconto_pct"],
        "valor_mensal_centavos": mensal,
        "valor_cheio_centavos": cheio,
        "desconto_periodo_centavos": desc_periodo,
        "desconto_cupom_centavos": desc_cupom,
        "valor_final_centavos": final,
        "valor_final_formatado": f"R$ {(final / 100):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "valor_cheio_formatado": f"R$ {(cheio / 100):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "cupom": cupom_info,
    }


def cupom_dict(row) -> dict:
    # id, codigo, descricao, tipo, valor, periodo, valido_ate, usos_max, usos_count, ativo, criado
    return {
        "id": row[0],
        "codigo": row[1],
        "descricao": row[2] or "",
        "tipo_desconto": row[3],
        "valor_desconto": float(row[4] or 0),
        "periodo": row[5],
        "valido_ate": row[6].isoformat() if row[6] else None,
        "usos_max": row[7],
        "usos_count": int(row[8] or 0),
        "ativo": bool(row[9]),
        "criado_em": row[10].isoformat() if len(row) > 10 and row[10] else None,
        "ilimitado": row[7] is None,
        "esgotado": row[7] is not None and int(row[8] or 0) >= int(row[7]),
    }


_CUPOM_COLS = """
    id, codigo, descricao, tipo_desconto, valor_desconto, periodo,
    valido_ate, usos_max, usos_count, ativo, criado_em
"""


def listar_cupons(cur, *, incluir_inativos: bool = True) -> list[dict]:
    sql = f"SELECT {_CUPOM_COLS} FROM tbl_cupom_desconto"
    if not incluir_inativos:
        sql += " WHERE ativo = TRUE"
    sql += " ORDER BY criado_em DESC, id DESC"
    cur.execute(sql)
    return [cupom_dict(r) for r in cur.fetchall()]


def obter_cupom_por_codigo(cur, codigo: str) -> dict | None:
    cod = normalizar_codigo(codigo)
    if not cod:
        return None
    cur.execute(
        f"SELECT {_CUPOM_COLS} FROM tbl_cupom_desconto WHERE upper(codigo) = %s LIMIT 1",
        (cod,),
    )
    row = cur.fetchone()
    return cupom_dict(row) if row else None


def obter_cupom_por_id(cur, id_cupom: int) -> dict | None:
    cur.execute(f"SELECT {_CUPOM_COLS} FROM tbl_cupom_desconto WHERE id = %s", (id_cupom,))
    row = cur.fetchone()
    return cupom_dict(row) if row else None


def validar_cupom_para_periodo(cur, codigo: str, periodo: str) -> dict:
    """Valida cupom ativo, prazo, estoque e período. Retorna dict do cupom."""
    p = normalizar_periodo(periodo)
    cupom = obter_cupom_por_codigo(cur, codigo)
    if not cupom:
        raise ValueError("Cupom inválido.")
    if not cupom["ativo"]:
        raise ValueError("Este cupom está inativo.")
    if cupom["periodo"] != p:
        rotulos = {k: v["rotulo"] for k, v in PERIODOS.items()}
        raise ValueError(
            f"Este cupom só é válido para assinatura {rotulos.get(cupom['periodo'], cupom['periodo'])}."
        )
    if cupom.get("valido_ate"):
        limite = date.fromisoformat(cupom["valido_ate"])
        if date.today() > limite:
            raise ValueError("Este cupom expirou.")
    if cupom.get("esgotado"):
        raise ValueError("Este cupom esgotou o limite de usos.")
    return cupom


def salvar_cupom(cur, dados: dict, *, id_cupom: int | None = None) -> dict:
    codigo = normalizar_codigo(dados.get("codigo"))
    if len(codigo) < 3:
        raise ValueError("Código do cupom deve ter ao menos 3 caracteres.")
    tipo = (dados.get("tipo_desconto") or "percentual").strip().lower()
    if tipo not in ("percentual", "fixo"):
        raise ValueError("Tipo de desconto inválido.")
    periodo = normalizar_periodo(dados.get("periodo"))
    try:
        valor = Decimal(str(dados.get("valor_desconto") or 0))
    except Exception as e:
        raise ValueError("Valor do desconto inválido.") from e
    if valor < 0:
        raise ValueError("Valor do desconto não pode ser negativo.")
    if tipo == "percentual" and valor > 100:
        raise ValueError("Percentual máximo é 100%.")

    valido_ate = dados.get("valido_ate") or None
    if valido_ate == "":
        valido_ate = None
    if isinstance(valido_ate, str):
        valido_ate = date.fromisoformat(valido_ate[:10])

    usos_raw = dados.get("usos_max")
    if usos_raw in (None, "", "null", "ilimitado", "inf", "infinito"):
        usos_max = None
    else:
        usos_max = int(usos_raw)
        if usos_max < 1:
            raise ValueError("Limite de usos deve ser ≥ 1 ou ilimitado.")

    descricao = (dados.get("descricao") or "").strip()[:255] or None
    ativo = bool(dados.get("ativo", True))

    if id_cupom:
        cur.execute(
            """
            UPDATE tbl_cupom_desconto SET
              codigo = %s, descricao = %s, tipo_desconto = %s, valor_desconto = %s,
              periodo = %s, valido_ate = %s, usos_max = %s, ativo = %s, atualizado_em = NOW()
            WHERE id = %s
            RETURNING id
            """,
            (codigo, descricao, tipo, valor, periodo, valido_ate, usos_max, ativo, id_cupom),
        )
        if not cur.fetchone():
            raise ValueError("Cupom não encontrado.")
        return obter_cupom_por_id(cur, id_cupom) or {}

    cur.execute(
        "SELECT 1 FROM tbl_cupom_desconto WHERE upper(codigo) = %s",
        (codigo,),
    )
    if cur.fetchone():
        raise ValueError("Já existe um cupom com este código.")

    cur.execute(
        """
        INSERT INTO tbl_cupom_desconto (
          codigo, descricao, tipo_desconto, valor_desconto, periodo,
          valido_ate, usos_max, ativo
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (codigo, descricao, tipo, valor, periodo, valido_ate, usos_max, ativo),
    )
    new_id = int(cur.fetchone()[0])
    return obter_cupom_por_id(cur, new_id) or {}


def registrar_uso_cupom(
    cur,
    *,
    id_cupom: int,
    id_tenant: int,
    id_fatura: int | None,
    codigo: str,
    desconto_centavos: int,
) -> None:
    cur.execute(
        """
        INSERT INTO tbl_cupom_uso (id_cupom, id_tenant, id_fatura, codigo, desconto_centavos)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (id_cupom, id_tenant, id_fatura, normalizar_codigo(codigo), int(desconto_centavos or 0)),
    )
    cur.execute(
        """
        UPDATE tbl_cupom_desconto
        SET usos_count = usos_count + 1, atualizado_em = NOW()
        WHERE id = %s
        """,
        (id_cupom,),
    )


def periodos_opcoes() -> list[dict]:
    return [
        {
            "id": k,
            "rotulo": v["rotulo"],
            "meses": v["meses"],
            "desconto_pct": v["desconto_pct"],
        }
        for k, v in PERIODOS.items()
    ]


def preview_assinatura(
    cur,
    *,
    valor_mensal_centavos: int,
    periodo: str,
    cupom_codigo: str | None = None,
) -> dict:
    p = normalizar_periodo(periodo)
    cupom = None
    if cupom_codigo and cupom_codigo.strip():
        cupom = validar_cupom_para_periodo(cur, cupom_codigo, p)
    preco = calcular_preco(valor_mensal_centavos, p, cupom=cupom)
    return {"success": True, **preco, "periodos": periodos_opcoes()}
