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

_CUPOM_ESCOPO_OK: bool | None = None


def normalizar_periodo(periodo: str | None) -> str:
    p = (periodo or "mensal").strip().lower()
    if p not in PERIODOS:
        raise ValueError("Periodicidade inválida. Use mensal, semestral ou anual.")
    return p


def normalizar_codigo(codigo: str | None) -> str:
    return "".join(c for c in (codigo or "").strip().upper() if c.isalnum() or c in "-_")


def _centavos(v: Decimal | float | int) -> int:
    return int(Decimal(str(v)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _rollback_cur(cur) -> None:
    try:
        cur.connection.rollback()
    except Exception:
        pass


def _escopo_cupom_existe(cur) -> bool:
    """Detecta SQL 092/093 sem exigir permissão de DDL."""
    cur.execute(
        """
        SELECT
          EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'tbl_cupom_desconto'
              AND column_name = 'publico_alvo'
              AND table_schema IN (current_schema(), 'public')
          )
          AND to_regclass('tbl_cupom_tenant') IS NOT NULL
          AND to_regclass('tbl_cupom_plano') IS NOT NULL
        """
    )
    row = cur.fetchone()
    return bool(row and row[0])


def garantir_escopo_cupom(cur) -> bool:
    """publico_alvo + tbl_cupom_tenant (092) + tbl_cupom_plano (093).

    Prioriza detecção (SELECT). Só tenta DDL se faltar algo — o usuário da app
    muitas vezes não tem CREATE/ALTER, e CREATE IF NOT EXISTS ainda exige CREATE.
    """
    global _CUPOM_ESCOPO_OK
    if _CUPOM_ESCOPO_OK is True:
        return True
    try:
        if _escopo_cupom_existe(cur):
            _CUPOM_ESCOPO_OK = True
            return True
    except Exception:
        _rollback_cur(cur)

    try:
        cur.execute(
            """
            ALTER TABLE tbl_cupom_desconto
                ADD COLUMN IF NOT EXISTS publico_alvo VARCHAR(20)
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tbl_cupom_tenant (
                id_cupom INTEGER NOT NULL REFERENCES tbl_cupom_desconto(id) ON DELETE CASCADE,
                id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
                PRIMARY KEY (id_cupom, id_tenant)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tbl_cupom_plano (
                id_cupom INTEGER NOT NULL REFERENCES tbl_cupom_desconto(id) ON DELETE CASCADE,
                plano_slug VARCHAR(60) NOT NULL,
                PRIMARY KEY (id_cupom, plano_slug)
            )
            """
        )
        if _escopo_cupom_existe(cur):
            _CUPOM_ESCOPO_OK = True
            return True
    except Exception:
        _rollback_cur(cur)
        # DDL falhou (sem permissão). Revalida: SQL manual pode já ter aplicado.
        try:
            if _escopo_cupom_existe(cur):
                _CUPOM_ESCOPO_OK = True
                return True
        except Exception:
            _rollback_cur(cur)

    _CUPOM_ESCOPO_OK = False
    return False


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


def _normalizar_publico_alvo(raw) -> str | None:
    v = (raw or "").strip().lower()
    if not v or v in ("todos", "qualquer", "all", "*"):
        return None
    if v not in ("vendedor", "fornecedor"):
        raise ValueError("Público do cupom inválido. Use vazio, vendedor ou fornecedor.")
    return v


def _normalizar_ids_tenants(raw) -> list[int]:
    if raw is None or raw == "" or raw == []:
        return []
    if isinstance(raw, str):
        partes = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
        src = partes
    elif isinstance(raw, (list, tuple, set)):
        src = list(raw)
    else:
        src = [raw]
    out: list[int] = []
    vistos: set[int] = set()
    for x in src:
        try:
            tid = int(x)
        except (TypeError, ValueError):
            continue
        if tid > 0 and tid not in vistos:
            out.append(tid)
            vistos.add(tid)
    return out


def _carregar_mapa_tenants_cupom(cur, ids_cupom: list[int]) -> dict[int, list[int]]:
    if not ids_cupom or not garantir_escopo_cupom(cur):
        return {}
    cur.execute(
        """
        SELECT id_cupom, id_tenant
        FROM tbl_cupom_tenant
        WHERE id_cupom = ANY(%s)
        ORDER BY id_cupom, id_tenant
        """,
        (ids_cupom,),
    )
    out: dict[int, list[int]] = {}
    for id_cupom, id_tenant in cur.fetchall():
        out.setdefault(int(id_cupom), []).append(int(id_tenant))
    return out


def _sincronizar_tenants_cupom(cur, id_cupom: int, ids_tenants: list[int]) -> None:
    if not garantir_escopo_cupom(cur):
        if ids_tenants:
            raise ValueError(
                "Não foi possível restringir o cupom a tenants. Aplique o SQL 092 no banco."
            )
        return
    cur.execute("DELETE FROM tbl_cupom_tenant WHERE id_cupom = %s", (id_cupom,))
    for tid in ids_tenants:
        cur.execute(
            """
            INSERT INTO tbl_cupom_tenant (id_cupom, id_tenant)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (id_cupom, tid),
        )


def _chave_plano_cupom(slug: str, tipo_negocio: str) -> str:
    return f"{(slug or '').strip().lower()}|{(tipo_negocio or '').strip().lower()}"


def _normalizar_planos_slug(raw) -> list[str]:
    """Aceita slug legado ('starter') ou chave 'starter|vendedor'."""
    if raw is None or raw == "" or raw == []:
        return []
    if isinstance(raw, str):
        src = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    elif isinstance(raw, (list, tuple, set)):
        src = list(raw)
    else:
        src = [raw]
    out: list[str] = []
    vistos: set[str] = set()
    for x in src:
        if isinstance(x, dict):
            slug = str(x.get("slug") or x.get("plano_slug") or "").strip().lower()
            tipo = str(x.get("tipo_negocio") or x.get("tipo") or "").strip().lower()
            chave = _chave_plano_cupom(slug, tipo) if tipo in ("vendedor", "fornecedor") else slug
        else:
            chave = str(x or "").strip().lower()
        if not chave:
            continue
        if "|" in chave:
            slug, tipo = chave.split("|", 1)
            if not slug or tipo not in ("vendedor", "fornecedor"):
                raise ValueError(f"Plano inválido: {chave}")
            chave = _chave_plano_cupom(slug, tipo)
        if chave not in vistos:
            out.append(chave)
            vistos.add(chave)
    return out


def _carregar_mapa_planos_cupom(cur, ids_cupom: list[int]) -> dict[int, list[str]]:
    if not ids_cupom or not garantir_escopo_cupom(cur):
        return {}
    cur.execute(
        """
        SELECT id_cupom, plano_slug
        FROM tbl_cupom_plano
        WHERE id_cupom = ANY(%s)
        ORDER BY id_cupom, plano_slug
        """,
        (ids_cupom,),
    )
    out: dict[int, list[str]] = {}
    for id_cupom, slug in cur.fetchall():
        out.setdefault(int(id_cupom), []).append(str(slug).strip().lower())
    return out


def _sincronizar_planos_cupom(cur, id_cupom: int, planos_slug: list[str]) -> None:
    if not garantir_escopo_cupom(cur):
        if planos_slug:
            raise ValueError(
                "Não foi possível restringir o cupom a planos. Aplique o SQL 093 no banco."
            )
        return
    cur.execute("DELETE FROM tbl_cupom_plano WHERE id_cupom = %s", (id_cupom,))
    for slug in planos_slug:
        cur.execute(
            """
            INSERT INTO tbl_cupom_plano (id_cupom, plano_slug)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (id_cupom, slug[:60]),
        )


def cupom_dict(
    row,
    *,
    ids_tenants: list[int] | None = None,
    planos_slug: list[str] | None = None,
) -> dict:
    # id, codigo, descricao, tipo, valor, periodo, valido_ate, usos_max, usos_count, ativo, criado[, publico]
    publico = None
    if len(row) > 11 and row[11]:
        publico = str(row[11]).strip().lower() or None
    ids = list(ids_tenants or [])
    planos = list(planos_slug or [])
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
        "publico_alvo": publico,
        "ids_tenants": ids,
        "planos_slug": planos,
        "ilimitado": row[7] is None,
        "esgotado": row[7] is not None and int(row[8] or 0) >= int(row[7]),
    }


def _cupom_cols(cur) -> str:
    if garantir_escopo_cupom(cur):
        return """
            id, codigo, descricao, tipo_desconto, valor_desconto, periodo,
            valido_ate, usos_max, usos_count, ativo, criado_em, publico_alvo
        """
    return """
        id, codigo, descricao, tipo_desconto, valor_desconto, periodo,
        valido_ate, usos_max, usos_count, ativo, criado_em
    """


def listar_cupons(cur, *, incluir_inativos: bool = True) -> list[dict]:
    cols = _cupom_cols(cur)
    sql = f"SELECT {cols} FROM tbl_cupom_desconto"
    if not incluir_inativos:
        sql += " WHERE ativo = TRUE"
    sql += " ORDER BY criado_em DESC, id DESC"
    cur.execute(sql)
    rows = cur.fetchall()
    ids = [int(r[0]) for r in rows]
    mapa_t = _carregar_mapa_tenants_cupom(cur, ids)
    mapa_p = _carregar_mapa_planos_cupom(cur, ids)
    return [
        cupom_dict(
            r,
            ids_tenants=mapa_t.get(int(r[0]), []),
            planos_slug=mapa_p.get(int(r[0]), []),
        )
        for r in rows
    ]


def obter_cupom_por_codigo(cur, codigo: str) -> dict | None:
    cod = normalizar_codigo(codigo)
    if not cod:
        return None
    cols = _cupom_cols(cur)
    cur.execute(
        f"SELECT {cols} FROM tbl_cupom_desconto WHERE upper(codigo) = %s LIMIT 1",
        (cod,),
    )
    row = cur.fetchone()
    if not row:
        return None
    cid = int(row[0])
    mapa_t = _carregar_mapa_tenants_cupom(cur, [cid])
    mapa_p = _carregar_mapa_planos_cupom(cur, [cid])
    return cupom_dict(
        row,
        ids_tenants=mapa_t.get(cid, []),
        planos_slug=mapa_p.get(cid, []),
    )


def obter_cupom_por_id(cur, id_cupom: int) -> dict | None:
    cols = _cupom_cols(cur)
    cur.execute(f"SELECT {cols} FROM tbl_cupom_desconto WHERE id = %s", (id_cupom,))
    row = cur.fetchone()
    if not row:
        return None
    cid = int(row[0])
    mapa_t = _carregar_mapa_tenants_cupom(cur, [cid])
    mapa_p = _carregar_mapa_planos_cupom(cur, [cid])
    return cupom_dict(
        row,
        ids_tenants=mapa_t.get(cid, []),
        planos_slug=mapa_p.get(cid, []),
    )


def _tipo_negocio_tenant(cur, id_tenant: int) -> str:
    cur.execute(
        "SELECT COALESCE(NULLIF(TRIM(tipo_negocio), ''), 'vendedor') FROM tbl_tenant WHERE id = %s",
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Conta não encontrada para validar o cupom.")
    return str(row[0] or "vendedor").strip().lower()


def validar_cupom_para_periodo(
    cur,
    codigo: str,
    periodo: str,
    *,
    id_tenant: int | None = None,
    plano_slug: str | None = None,
) -> dict:
    """Valida cupom ativo, prazo, estoque, período e escopo (tipo/tenant/plano)."""
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

    publico = (cupom.get("publico_alvo") or "").strip().lower() or None
    ids_ok = list(cupom.get("ids_tenants") or [])
    planos_ok = list(cupom.get("planos_slug") or [])
    if publico or ids_ok:
        if not id_tenant:
            raise ValueError("Este cupom é restrito e não pode ser usado neste contexto.")
        if ids_ok and int(id_tenant) not in ids_ok:
            raise ValueError("Este cupom não está disponível para a sua conta.")
        if publico:
            tipo = _tipo_negocio_tenant(cur, int(id_tenant))
            if publico == "vendedor" and tipo not in ("vendedor", "hibrido"):
                raise ValueError("Este cupom é exclusivo para vendedores.")
            if publico == "fornecedor" and tipo not in ("fornecedor", "hibrido"):
                raise ValueError("Este cupom é exclusivo para fornecedores.")
    if planos_ok:
        slug = (plano_slug or "").strip().lower()
        if not slug:
            raise ValueError("Este cupom é válido só para planos específicos.")
        tipo_conta = ""
        if id_tenant:
            tipo_conta = _tipo_negocio_tenant(cur, int(id_tenant))
        candidatos = {slug}
        if tipo_conta in ("vendedor", "fornecedor"):
            candidatos.add(_chave_plano_cupom(slug, tipo_conta))
        elif tipo_conta == "hibrido":
            candidatos.add(_chave_plano_cupom(slug, "vendedor"))
            candidatos.add(_chave_plano_cupom(slug, "fornecedor"))
        if not candidatos.intersection(planos_ok):
            raise ValueError("Este cupom não é válido para o plano selecionado.")
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
    publico_alvo = _normalizar_publico_alvo(dados.get("publico_alvo"))
    ids_tenants = _normalizar_ids_tenants(
        dados.get("ids_tenants") if "ids_tenants" in dados else dados.get("tenants")
    )
    planos_slug = _normalizar_planos_slug(
        dados.get("planos_slug") if "planos_slug" in dados else dados.get("planos")
    )

    if ids_tenants:
        cur.execute(
            "SELECT id FROM tbl_tenant WHERE id = ANY(%s)",
            (ids_tenants,),
        )
        existentes = {int(r[0]) for r in cur.fetchall()}
        faltando = [i for i in ids_tenants if i not in existentes]
        if faltando:
            raise ValueError(f"Tenant(s) inválido(s): {', '.join(str(x) for x in faltando)}.")

    if planos_slug:
        slugs_base = []
        for chave in planos_slug:
            slugs_base.append(chave.split("|", 1)[0] if "|" in chave else chave)
        cur.execute(
            "SELECT slug FROM tbl_plano WHERE ativo = TRUE AND lower(slug) = ANY(%s)",
            ([s.lower() for s in slugs_base],),
        )
        existentes_p = {str(r[0]).strip().lower() for r in cur.fetchall()}
        faltando_p = [s for s in slugs_base if s not in existentes_p]
        if faltando_p:
            raise ValueError(f"Plano(s) inválido(s): {', '.join(faltando_p)}.")

    tem_escopo = garantir_escopo_cupom(cur)
    if (publico_alvo or ids_tenants or planos_slug) and not tem_escopo:
        raise ValueError(
            "Escopo de cupom indisponível. Aplique os SQL 092/093 no banco."
        )

    if id_cupom:
        if tem_escopo:
            cur.execute(
                """
                UPDATE tbl_cupom_desconto SET
                  codigo = %s, descricao = %s, tipo_desconto = %s, valor_desconto = %s,
                  periodo = %s, valido_ate = %s, usos_max = %s, ativo = %s,
                  publico_alvo = %s, atualizado_em = NOW()
                WHERE id = %s
                RETURNING id
                """,
                (
                    codigo,
                    descricao,
                    tipo,
                    valor,
                    periodo,
                    valido_ate,
                    usos_max,
                    ativo,
                    publico_alvo,
                    id_cupom,
                ),
            )
        else:
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
        _sincronizar_tenants_cupom(cur, id_cupom, ids_tenants)
        _sincronizar_planos_cupom(cur, id_cupom, planos_slug)
        return obter_cupom_por_id(cur, id_cupom) or {}

    cur.execute(
        "SELECT 1 FROM tbl_cupom_desconto WHERE upper(codigo) = %s",
        (codigo,),
    )
    if cur.fetchone():
        raise ValueError("Já existe um cupom com este código.")

    if tem_escopo:
        cur.execute(
            """
            INSERT INTO tbl_cupom_desconto (
              codigo, descricao, tipo_desconto, valor_desconto, periodo,
              valido_ate, usos_max, ativo, publico_alvo
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                codigo,
                descricao,
                tipo,
                valor,
                periodo,
                valido_ate,
                usos_max,
                ativo,
                publico_alvo,
            ),
        )
    else:
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
    _sincronizar_tenants_cupom(cur, new_id, ids_tenants)
    _sincronizar_planos_cupom(cur, new_id, planos_slug)
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


def listar_tenants_para_cupom(cur) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT id, nome, slug, COALESCE(NULLIF(TRIM(tipo_negocio), ''), 'vendedor')
        FROM tbl_tenant
        WHERE COALESCE(ativo, TRUE) = TRUE
          AND COALESCE(NULLIF(TRIM(tipo_negocio), ''), 'vendedor')
              IN ('vendedor', 'fornecedor', 'hibrido')
        ORDER BY nome NULLS LAST, id
        LIMIT 500
        """
    )
    out = []
    for r in cur.fetchall():
        out.append(
            {
                "id": int(r[0]),
                "nome": r[1] or f"Tenant #{r[0]}",
                "slug": r[2] or "",
                "tipo_negocio": str(r[3] or "vendedor").lower(),
            }
        )
    return out


def combobox_tenants_para_cupom(
    cur, filtro: str = "", limitar: int = 20
) -> list[dict[str, Any]]:
    """Busca remota no padrão BARACAT (sucesso/dados) para combobox personalizada."""
    termo = (filtro or "").strip()
    try:
        limite = min(40, max(1, int(limitar or 20)))
    except (TypeError, ValueError):
        limite = 20

    params: list[Any] = []
    where_extra = ""
    if termo:
        if termo.isdigit():
            where_extra = "AND (t.id = %s OR t.nome ILIKE %s OR COALESCE(t.slug, '') ILIKE %s)"
            like = f"%{termo}%"
            params.extend([int(termo), like, like])
        else:
            where_extra = "AND (t.nome ILIKE %s OR COALESCE(t.slug, '') ILIKE %s)"
            like = f"%{termo}%"
            params.extend([like, like])

    cur.execute(
        f"""
        SELECT t.id, t.nome, t.slug,
               COALESCE(NULLIF(TRIM(t.tipo_negocio), ''), 'vendedor')
        FROM tbl_tenant t
        WHERE COALESCE(t.ativo, TRUE) = TRUE
          AND COALESCE(NULLIF(TRIM(t.tipo_negocio), ''), 'vendedor')
              IN ('vendedor', 'fornecedor', 'hibrido')
          {where_extra}
        ORDER BY t.nome NULLS LAST, t.id
        LIMIT %s
        """,
        (*params, limite),
    )
    out = []
    for r in cur.fetchall():
        tid = int(r[0])
        nome = r[1] or f"Tenant #{tid}"
        slug = r[2] or ""
        tipo = str(r[3] or "vendedor").lower()
        out.append(
            {
                "id": tid,
                "nome": nome,
                "titulo": f"#{tid} — {nome}",
                "slug": slug,
                "tipo_negocio": tipo,
            }
        )
    return out


def listar_planos_para_cupom(cur) -> list[dict[str, Any]]:
    """Uma opção por plano × perfil (vendedor/fornecedor), rótulo: Nome comercial | Perfil."""
    from sistema.planos.limites import limites_plano

    try:
        cur.execute(
            """
            SELECT slug, nome, COALESCE(valor_centavos, 0)
            FROM tbl_plano
            WHERE ativo = TRUE
            ORDER BY ordem NULLS LAST, nome, slug
            """
        )
    except Exception:
        _rollback_cur(cur)
        cur.execute(
            """
            SELECT slug, nome, COALESCE(valor_centavos, 0)
            FROM tbl_plano
            WHERE ativo = TRUE
            ORDER BY nome, slug
            """
        )
    base = []
    for r in cur.fetchall():
        base.append(
            {
                "slug": str(r[0] or "").strip().lower(),
                "nome_base": r[1] or str(r[0] or ""),
                "valor_centavos": int(r[2] or 0),
            }
        )
    out: list[dict[str, Any]] = []
    for tipo, rotulo in (("vendedor", "Vendedor"), ("fornecedor", "Fornecedor")):
        for p in base:
            chave = _chave_plano_cupom(p["slug"], tipo)
            nome_com = (
                limites_plano(plano=p["slug"], tipo_negocio=tipo).get("nome")
                or p["nome_base"]
            )
            out.append(
                {
                    "key": chave,
                    "slug": p["slug"],
                    "tipo_negocio": tipo,
                    "nome": f"{nome_com} | {rotulo}",
                    "valor_centavos": p["valor_centavos"],
                }
            )
    return out


def preview_assinatura(
    cur,
    *,
    valor_mensal_centavos: int,
    periodo: str,
    cupom_codigo: str | None = None,
    id_tenant: int | None = None,
    plano_slug: str | None = None,
) -> dict:
    p = normalizar_periodo(periodo)
    cupom = None
    if cupom_codigo and cupom_codigo.strip():
        cupom = validar_cupom_para_periodo(
            cur,
            cupom_codigo,
            p,
            id_tenant=id_tenant,
            plano_slug=plano_slug,
        )
    preco = calcular_preco(valor_mensal_centavos, p, cupom=cupom)
    return {"success": True, **preco, "periodos": periodos_opcoes()}
