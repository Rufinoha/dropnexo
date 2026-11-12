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

# Sempre existentes no DropNexo (cadastro / Minha empresa).
_COLS_BASE = (
    "id",
    "tipo_pessoa",
    "documento",
    "nome",
    "nome_completo",
    "razao_social",
    "nome_fantasia",
    "inscricao_municipal",
    "cidade",
    "uf",
    "cep",
    "logradouro",
    "numero",
    "complemento",
    "bairro",
    "telefone_comercial",
    "email_comercial",
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
        try:
            if _coluna_existe(conn, nome):
                continue
            db_execute(conn, f"ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS {nome} {tipo}")
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass


def sincronizar_legado_config_empresa(conn, id_tenant: int) -> None:
    """Copia dados antigos de tbl_nfse_config_empresa → tbl_tenant (sem sobrescrever)."""
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
        try:
            conn.rollback()
        except Exception:
            pass


def _ler_tenant_row(conn, id_tenant: int) -> dict:
    """Lê só colunas que existem — nunca quebra se faltar campo fiscal novo."""
    presentes = [c for c in _COLS_BASE if _coluna_existe(conn, c)]
    extras = [n for n, _ in _COLUNAS if n not in presentes and _coluna_existe(conn, n)]
    cols = presentes + extras
    if "id" not in cols:
        cols.insert(0, "id")
    cur = db_execute(
        conn,
        f"SELECT {', '.join(cols)} FROM tbl_tenant WHERE id = %s LIMIT 1",
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return {}
    return dict(zip([c[0] for c in cur.description], row))


def _fmt_percentual(valor) -> str:
    if valor is None or valor == "":
        return ""
    if isinstance(valor, Decimal):
        return f"{valor:.2f}".replace(".", ",")
    return str(valor).replace(".", ",")


def carregar_empresa_fiscal(conn, id_tenant: int) -> dict:
    try:
        garantir_colunas_tenant_fiscal(conn)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    try:
        sincronizar_legado_config_empresa(conn, id_tenant)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass

    d = _ler_tenant_row(conn, id_tenant)
    if not d:
        return {"eh_pj": False, "tipo_pessoa": "", "id_tenant": id_tenant}

    tipo = (d.get("tipo_pessoa") or "").strip().upper()
    doc = somente_digitos(d.get("documento") or "")
    cnpj_col = somente_digitos(d.get("cnpj") or "")
    cnpj = doc if len(doc) == 14 else (cnpj_col if len(cnpj_col) == 14 else (cnpj_col or doc))
    eh_pj = tipo == "J" or len(somente_digitos(cnpj)) == 14

    razao = (
        (d.get("razao_social") or "").strip()
        or (d.get("nome_completo") or "").strip()
        or (d.get("nome") or "").strip()
    )
    fantasia = (d.get("nome_fantasia") or d.get("nome") or "").strip()
    municipio = (d.get("municipio_nome") or d.get("cidade") or "").strip()
    ambiente = (d.get("ambiente_nfse") or "homologacao").strip()
    if ambiente not in ("homologacao", "producao"):
        ambiente = "homologacao"

    return {
        "id_tenant": id_tenant,
        "tipo_pessoa": tipo or ("J" if eh_pj else ""),
        "eh_pj": eh_pj,
        "razao_social": razao,
        "nome_fantasia": fantasia,
        "cnpj": somente_digitos(cnpj) if eh_pj else "",
        "inscricao_municipal": (d.get("inscricao_municipal") or "").strip(),
        "municipio_ibge_codigo": somente_digitos(d.get("municipio_ibge_codigo") or ""),
        "municipio_nome": municipio,
        "uf": (d.get("uf") or "").strip().upper(),
        "cep": somente_digitos(d.get("cep") or ""),
        "logradouro": (d.get("logradouro") or "").strip(),
        "numero": (d.get("numero") or "").strip(),
        "complemento": (d.get("complemento") or "").strip(),
        "bairro": (d.get("bairro") or "").strip(),
        "telefone_comercial": (d.get("telefone_comercial") or "").strip(),
        "email_comercial": (d.get("email_comercial") or "").strip(),
        "regime_tributario": (d.get("regime_tributario") or "simples_nacional").strip(),
        "optante_simples": bool(
            d.get("optante_simples") if d.get("optante_simples") is not None else True
        ),
        "incentivador_cultural": bool(d.get("incentivador_cultural") or False),
        "regime_especial_tributacao": (d.get("regime_especial_tributacao") or "").strip(),
        "percentual_tributos_sn": _fmt_percentual(d.get("percentual_tributos_sn")),
        "serie_dps": ((d.get("serie_dps") or "1").strip() or "1"),
        "proximo_numero_dps": int(d.get("proximo_numero_dps") or 1),
        "ambiente": ambiente,
        "ambiente_nfse": ambiente,
        "ultimo_nsu_adn": int(d.get("ultimo_nsu_adn") or 0),
        "cnpj_bloqueado": True,
        "razao_bloqueada": True,
    }


def salvar_empresa_fiscal(conn, id_tenant: int, dados: dict) -> dict:
    garantir_colunas_tenant_fiscal(conn)
    atual = carregar_empresa_fiscal(conn, id_tenant)
    if not atual.get("eh_pj"):
        raise PermissionError(
            "Empresa fiscal só se aplica a cadastro pessoa jurídica (PJ). "
            "Atualize em Minha empresa para tipo PJ."
        )

    cnpj = somente_digitos(atual.get("cnpj") or "")
    razao = (atual.get("razao_social") or "").strip()
    if len(cnpj) != 14:
        raise ValueError("CNPJ da sua empresa ausente ou inválido. Corrija em Minha empresa.")
    if not razao:
        raise ValueError("Razão social da sua empresa ausente. Corrija em Minha empresa.")

    uf = (dados.get("uf") or "").strip().upper()
    ibge = somente_digitos(dados.get("municipio_ibge_codigo"))
    municipio = (dados.get("municipio_nome") or "").strip()
    cep = somente_digitos(dados.get("cep") or "")[:8] or None
    logradouro = (dados.get("logradouro") or "").strip() or None
    bairro = (dados.get("bairro") or "").strip() or None
    fantasia = (dados.get("nome_fantasia") or "").strip() or None
    im = (dados.get("inscricao_municipal") or "").strip() or None
    ambiente = (
        dados.get("ambiente")
        if dados.get("ambiente") in {"homologacao", "producao"}
        else "homologacao"
    )
    serie = (dados.get("serie_dps") or "1").strip() or "1"
    proximo = max(1, int(dados.get("proximo_numero_dps") or 1))
    regime = (dados.get("regime_tributario") or "simples_nacional").strip() or "simples_nacional"
    regime_esp = (dados.get("regime_especial_tributacao") or "").strip() or None
    optante = bool(dados.get("optante_simples"))
    cultural = bool(dados.get("incentivador_cultural"))
    percentual = dados.get("percentual_tributos_sn")
    if percentual is not None and str(percentual).strip() == "":
        percentual = None

    sets = [
        "nome_fantasia = %s",
        "inscricao_municipal = %s",
        "uf = %s",
    ]
    vals: list = [fantasia, im, uf or None]

    if _coluna_existe(conn, "cnpj"):
        sets.append("cnpj = COALESCE(NULLIF(TRIM(cnpj), ''), %s)")
        vals.append(cnpj)
    sets.append("documento = COALESCE(NULLIF(TRIM(documento), ''), %s)")
    vals.append(cnpj)
    if _coluna_existe(conn, "razao_social"):
        sets.append("razao_social = COALESCE(NULLIF(TRIM(razao_social), ''), %s)")
        vals.append(razao)
    sets.append("nome_completo = COALESCE(NULLIF(TRIM(nome_completo), ''), %s)")
    vals.append(razao)

    for col, val in (
        ("municipio_ibge_codigo", ibge or None),
        ("municipio_nome", municipio or None),
        ("cep", cep),
        ("logradouro", logradouro),
        ("bairro", bairro),
        ("regime_tributario", regime),
        ("optante_simples", optante),
        ("incentivador_cultural", cultural),
        ("regime_especial_tributacao", regime_esp),
        ("percentual_tributos_sn", percentual),
        ("serie_dps", serie),
        ("proximo_numero_dps", proximo),
        ("ambiente_nfse", ambiente),
    ):
        if val is None and col in {"logradouro", "bairro", "cep"}:
            # Não apaga endereço existente se a tela não enviou o campo.
            continue
        if _coluna_existe(conn, col):
            sets.append(f"{col} = %s")
            vals.append(val)

    if municipio and _coluna_existe(conn, "cidade"):
        sets.append("cidade = COALESCE(NULLIF(TRIM(%s), ''), cidade)")
        vals.append(municipio)

    if _coluna_existe(conn, "dt_atualizacao"):
        sets.append("dt_atualizacao = NOW()")

    vals.append(id_tenant)
    db_execute(
        conn,
        f"UPDATE tbl_tenant SET {', '.join(sets)} WHERE id = %s",
        tuple(vals),
    )
    return carregar_empresa_fiscal(conn, id_tenant)
