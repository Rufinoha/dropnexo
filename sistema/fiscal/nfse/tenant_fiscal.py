"""Empresa fiscal = dados do tenant PJ em tbl_tenant (sem cadastro paralelo)."""
from __future__ import annotations

from decimal import Decimal

from global_utils import db_execute, somente_digitos

# Campos fiscais / NFS-e no próprio tenant.
_COLUNAS = (
    ("razao_social", "VARCHAR(220)"),
    ("nome_fantasia", "VARCHAR(220)"),
    ("cnpj", "VARCHAR(14)"),
    ("inscricao_municipal", "VARCHAR(40)"),
    ("municipio_ibge_codigo", "VARCHAR(7)"),
    ("municipio_nome", "VARCHAR(120)"),
    ("regime_tributario", "VARCHAR(40) DEFAULT 'simples_nacional'"),
    ("optante_simples", "BOOLEAN DEFAULT TRUE"),
    ("incentivador_cultural", "BOOLEAN DEFAULT FALSE"),
    ("regime_especial_tributacao", "VARCHAR(60)"),
    ("percentual_tributos_sn", "NUMERIC(5,2)"),
    ("serie_dps", "VARCHAR(10) DEFAULT '1'"),
    ("proximo_numero_dps", "BIGINT DEFAULT 1"),
    ("ambiente_nfse", "VARCHAR(20) DEFAULT 'homologacao'"),
    ("ultimo_nsu_adn", "BIGINT DEFAULT 0"),
    ("dt_atualizacao", "TIMESTAMPTZ"),
)


def _coluna_existe(conn, coluna: str) -> bool:
    cur = db_execute(
        conn,
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = 'tbl_tenant'
           AND column_name = %s
         LIMIT 1
        """,
        (coluna,),
    )
    return bool(cur.fetchone())


def garantir_colunas_tenant_fiscal(conn) -> None:
    for nome, tipo in _COLUNAS:
        if _coluna_existe(conn, nome):
            continue
        db_execute(conn, f"ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS {nome} {tipo}")
    conn.commit()


def sincronizar_legado_config_empresa(conn, id_tenant: int) -> None:
    """Copia uma vez dados antigos de tbl_nfse_config_empresa → tbl_tenant (sem sobrescrever)."""
    if not id_tenant:
        return
    try:
        db_execute(
            conn,
            """
            UPDATE tbl_tenant t
               SET razao_social = COALESCE(NULLIF(TRIM(t.razao_social), ''), NULLIF(TRIM(c.razao_social), '')),
                   nome_fantasia = COALESCE(NULLIF(TRIM(t.nome_fantasia), ''), NULLIF(TRIM(c.nome_fantasia), '')),
                   cnpj = COALESCE(NULLIF(TRIM(t.cnpj), ''), NULLIF(TRIM(c.cnpj), ''),
                                   CASE WHEN UPPER(COALESCE(t.tipo_pessoa,'')) = 'J'
                                        THEN NULLIF(TRIM(t.documento), '') END),
                   inscricao_municipal = COALESCE(NULLIF(TRIM(t.inscricao_municipal), ''), c.inscricao_municipal),
                   municipio_ibge_codigo = COALESCE(NULLIF(TRIM(t.municipio_ibge_codigo), ''), NULLIF(TRIM(c.municipio_ibge_codigo), '')),
                   municipio_nome = COALESCE(NULLIF(TRIM(t.municipio_nome), ''), NULLIF(TRIM(c.municipio_nome), ''),
                                             NULLIF(TRIM(t.cidade), '')),
                   uf = COALESCE(NULLIF(TRIM(t.uf), ''), NULLIF(TRIM(c.uf), '')),
                   regime_tributario = COALESCE(NULLIF(TRIM(t.regime_tributario), ''), c.regime_tributario, 'simples_nacional'),
                   optante_simples = COALESCE(t.optante_simples, c.optante_simples, TRUE),
                   incentivador_cultural = COALESCE(t.incentivador_cultural, c.incentivador_cultural, FALSE),
                   regime_especial_tributacao = COALESCE(t.regime_especial_tributacao, c.regime_especial_tributacao),
                   percentual_tributos_sn = COALESCE(t.percentual_tributos_sn, c.percentual_tributos_sn),
                   serie_dps = COALESCE(NULLIF(TRIM(t.serie_dps), ''), NULLIF(TRIM(c.serie_dps), ''), '1'),
                   proximo_numero_dps = COALESCE(NULLIF(t.proximo_numero_dps, 0), c.proximo_numero_dps, 1),
                   ambiente_nfse = COALESCE(NULLIF(TRIM(t.ambiente_nfse), ''), NULLIF(TRIM(c.ambiente), ''), 'homologacao'),
                   ultimo_nsu_adn = GREATEST(COALESCE(t.ultimo_nsu_adn, 0), COALESCE(c.ultimo_nsu_adn, 0))
              FROM tbl_nfse_config_empresa c
             WHERE c.id_tenant = t.id
               AND t.id = %s
            """,
            (id_tenant,),
        )
        conn.commit()
    except Exception:
        conn.rollback()


def carregar_empresa_fiscal(conn, id_tenant: int) -> dict:
    garantir_colunas_tenant_fiscal(conn)
    sincronizar_legado_config_empresa(conn, id_tenant)
    cur = db_execute(
        conn,
        """
        SELECT id, tipo_pessoa, documento, nome, nome_completo,
               razao_social, nome_fantasia, cnpj, inscricao_municipal,
               municipio_ibge_codigo, municipio_nome, cidade, uf,
               regime_tributario, optante_simples, incentivador_cultural,
               regime_especial_tributacao, percentual_tributos_sn,
               serie_dps, proximo_numero_dps, ambiente_nfse, ultimo_nsu_adn
          FROM tbl_tenant
         WHERE id = %s
         LIMIT 1
        """,
        (id_tenant,),
    )
    cols = [c[0] for c in cur.description]
    row = cur.fetchone()
    if not row:
        return {"eh_pj": False, "tipo_pessoa": "", "id_tenant": id_tenant}
    d = dict(zip(cols, row))
    tipo = (d.get("tipo_pessoa") or "").strip().upper()
    eh_pj = tipo == "J"
    cnpj = somente_digitos(d.get("cnpj") or "") or (
        somente_digitos(d.get("documento") or "") if eh_pj else ""
    )
    municipio = (d.get("municipio_nome") or d.get("cidade") or "").strip()
    razao = (d.get("razao_social") or d.get("nome_completo") or d.get("nome") or "").strip()
    fantasia = (d.get("nome_fantasia") or "").strip()
    ambiente = (d.get("ambiente_nfse") or "homologacao").strip()
    if ambiente not in ("homologacao", "producao"):
        ambiente = "homologacao"
    percentual = d.get("percentual_tributos_sn")
    if isinstance(percentual, Decimal):
        percentual = f"{percentual:.2f}".replace(".", ",")
    elif percentual is not None:
        percentual = str(percentual).replace(".", ",")
    else:
        percentual = ""
    return {
        "id_tenant": id_tenant,
        "tipo_pessoa": tipo,
        "eh_pj": eh_pj,
        "razao_social": razao,
        "nome_fantasia": fantasia,
        "cnpj": cnpj,
        "inscricao_municipal": (d.get("inscricao_municipal") or "").strip(),
        "municipio_ibge_codigo": somente_digitos(d.get("municipio_ibge_codigo") or ""),
        "municipio_nome": municipio,
        "uf": (d.get("uf") or "").strip().upper(),
        "regime_tributario": (d.get("regime_tributario") or "simples_nacional").strip(),
        "optante_simples": bool(d.get("optante_simples") if d.get("optante_simples") is not None else True),
        "incentivador_cultural": bool(d.get("incentivador_cultural") or False),
        "regime_especial_tributacao": (d.get("regime_especial_tributacao") or "").strip(),
        "percentual_tributos_sn": percentual,
        "serie_dps": (d.get("serie_dps") or "1").strip() or "1",
        "proximo_numero_dps": int(d.get("proximo_numero_dps") or 1),
        "ambiente": ambiente,
        "ambiente_nfse": ambiente,
        "ultimo_nsu_adn": int(d.get("ultimo_nsu_adn") or 0),
    }


def salvar_empresa_fiscal(conn, id_tenant: int, dados: dict) -> dict:
    garantir_colunas_tenant_fiscal(conn)
    cur = db_execute(
        conn,
        "SELECT tipo_pessoa FROM tbl_tenant WHERE id = %s LIMIT 1",
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Tenant não encontrado.")
    tipo = (row[0] or "").strip().upper()
    if tipo != "J":
        raise PermissionError(
            "Empresa fiscal só se aplica a tenant pessoa jurídica (PJ). "
            "Atualize o cadastro do tenant para tipo PJ."
        )

    cnpj = somente_digitos(dados.get("cnpj"))
    uf = (dados.get("uf") or "").strip().upper()
    ibge = somente_digitos(dados.get("municipio_ibge_codigo"))
    municipio = (dados.get("municipio_nome") or "").strip()
    razao = (dados.get("razao_social") or "").strip()
    fantasia = (dados.get("nome_fantasia") or "").strip() or None
    im = (dados.get("inscricao_municipal") or "").strip() or None
    ambiente = dados.get("ambiente") if dados.get("ambiente") in {"homologacao", "producao"} else "homologacao"
    serie = (dados.get("serie_dps") or "1").strip() or "1"
    proximo = max(1, int(dados.get("proximo_numero_dps") or 1))
    regime = (dados.get("regime_tributario") or "simples_nacional").strip() or "simples_nacional"
    regime_esp = (dados.get("regime_especial_tributacao") or "").strip() or None
    optante = bool(dados.get("optante_simples"))
    cultural = bool(dados.get("incentivador_cultural"))
    percentual = dados.get("percentual_tributos_sn")
    if percentual is not None and str(percentual).strip() == "":
        percentual = None

    db_execute(
        conn,
        """
        UPDATE tbl_tenant SET
            razao_social = %s,
            nome_fantasia = %s,
            nome_completo = COALESCE(NULLIF(TRIM(nome_completo), ''), %s),
            cnpj = %s,
            documento = %s,
            inscricao_municipal = %s,
            municipio_ibge_codigo = %s,
            municipio_nome = %s,
            cidade = COALESCE(NULLIF(TRIM(%s), ''), cidade),
            uf = %s,
            regime_tributario = %s,
            optante_simples = %s,
            incentivador_cultural = %s,
            regime_especial_tributacao = %s,
            percentual_tributos_sn = %s,
            serie_dps = %s,
            proximo_numero_dps = %s,
            ambiente_nfse = %s,
            dt_atualizacao = NOW()
         WHERE id = %s
        """,
        (
            razao or None,
            fantasia,
            razao or None,
            cnpj or None,
            cnpj or None,
            im,
            ibge or None,
            municipio or None,
            municipio or None,
            uf or None,
            regime,
            optante,
            cultural,
            regime_esp,
            percentual,
            serie,
            proximo,
            ambiente,
            id_tenant,
        ),
    )
    return carregar_empresa_fiscal(conn, id_tenant)
