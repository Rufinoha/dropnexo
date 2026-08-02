# core/dominio.py — categorias, CNPJ e vínculos vendedor×fornecedor
from __future__ import annotations

# ── categorias ────────────────────────────────────────

MAX_NIVEL_CATEGORIA = 3


def montar_arvore_categorias(rows: list[tuple]) -> list[dict]:
    """rows: id, nome, parent_id, ordem, nivel, qtd_produtos"""
    nodes = []
    for r in rows:
        nodes.append(
            {
                "id": r[0],
                "nome": r[1],
                "parent_id": r[2],
                "ordem": r[3],
                "nivel": int(r[4] or 1),
                "qtd_produtos": int(r[5] or 0),
                "filhos": [],
            }
        )
    by_id = {n["id"]: n for n in nodes}
    raiz = []
    for n in nodes:
        pid = n["parent_id"]
        if pid and pid in by_id:
            by_id[pid]["filhos"].append(n)
        else:
            raiz.append(n)

    def ordenar(lst):
        lst.sort(key=lambda x: (x["ordem"], x["nome"]))
        for c in lst:
            ordenar(c["filhos"])

    ordenar(raiz)
    return raiz


def caminho_categoria(nome: str, parent_id: int | None, by_id: dict) -> str:
    partes = [nome]
    pid = parent_id
    while pid and pid in by_id:
        p = by_id[pid]
        partes.insert(0, p["nome"])
        pid = p.get("parent_id")
    return " › ".join(partes)


def flatten_arvore_com_caminho(raiz: list[dict], prefixo: str = "") -> list[dict]:
    """Lista plana para combos (produto): id, nome, caminho, nivel."""
    out = []
    for n in raiz:
        caminho = f"{prefixo}{n['nome']}" if prefixo else n["nome"]
        out.append(
            {
                "id": n["id"],
                "nome": n["nome"],
                "caminho": caminho,
                "nivel": n["nivel"],
            }
        )
        out.extend(flatten_arvore_com_caminho(n["filhos"], caminho + " › "))
    return out


# ── cnpj ──────────────────────────────────────────────

import re

import requests

_BRASIL_API = "https://brasilapi.com.br/api/cnpj/v1"


def _so_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def consultar_cnpj(cnpj: str) -> dict:
    """Consulta dados públicos do CNPJ. Levanta ValueError se inválido/não encontrado."""
    doc = _so_digitos(cnpj)
    if len(doc) != 14:
        raise ValueError("CNPJ inválido.")

    try:
        r = requests.get(f"{_BRASIL_API}/{doc}", timeout=15)
    except requests.RequestException as exc:
        raise ValueError(f"Não foi possível consultar o CNPJ: {exc}") from exc

    if r.status_code == 404:
        raise ValueError("CNPJ não encontrado na base pública. Preencha os dados manualmente.")
    if r.status_code == 429:
        raise ValueError("Consulta de CNPJ temporariamente indisponível. Aguarde um minuto ou preencha manualmente.")
    if r.status_code >= 400:
        raise ValueError(
            f"Serviço de consulta CNPJ indisponível (HTTP {r.status_code}). Preencha os dados manualmente."
        )

    data = r.json()
    if not isinstance(data, dict):
        raise ValueError("Resposta inválida da consulta CNPJ.")

    cep = _so_digitos(str(data.get("cep") or ""))
    return {
        "cnpj": doc,
        "razao_social": (data.get("razao_social") or "").strip(),
        "nome_fantasia": (data.get("nome_fantasia") or data.get("razao_social") or "").strip(),
        "situacao_cadastral": (data.get("descricao_situacao_cadastral") or "").strip(),
        "cnae_principal": str(data.get("cnae_fiscal") or data.get("cnae") or "").strip(),
        "cep": cep,
        "logradouro": (data.get("logradouro") or "").strip(),
        "numero": (data.get("numero") or "").strip(),
        "complemento": (data.get("complemento") or "").strip(),
        "bairro": (data.get("bairro") or "").strip(),
        "cidade": (data.get("municipio") or "").strip(),
        "uf": (data.get("uf") or "").strip().upper(),
    }


# ── vinculos ──────────────────────────────────────────

from flask import session

_VINCOLO_COLS_OK: bool | None = None


def _rollback_vinculo(cur) -> None:
    try:
        cur.connection.rollback()
    except Exception:
        pass


def garantir_colunas_vinculo_status(cur) -> None:
    """motivo + auditoria de pausa/encerramento (SQL 095)."""
    global _VINCOLO_COLS_OK
    if _VINCOLO_COLS_OK is True:
        return
    try:
        cur.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'tbl_vinculo_vendedor_fornecedor'
              AND column_name = 'motivo_status'
              AND table_schema IN (current_schema(), 'public')
            LIMIT 1
            """
        )
        if cur.fetchone():
            _VINCOLO_COLS_OK = True
            return
        for ddl in (
            "ALTER TABLE tbl_vinculo_vendedor_fornecedor ADD COLUMN IF NOT EXISTS motivo_status TEXT",
            "ALTER TABLE tbl_vinculo_vendedor_fornecedor ADD COLUMN IF NOT EXISTS status_alterado_em TIMESTAMPTZ",
            "ALTER TABLE tbl_vinculo_vendedor_fornecedor ADD COLUMN IF NOT EXISTS status_alterado_por_usuario INTEGER",
            "ALTER TABLE tbl_vinculo_vendedor_fornecedor ADD COLUMN IF NOT EXISTS status_alterado_por_lado VARCHAR(20)",
        ):
            cur.execute(ddl)
        _VINCOLO_COLS_OK = True
    except Exception:
        _rollback_vinculo(cur)
        try:
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'tbl_vinculo_vendedor_fornecedor'
                  AND column_name = 'motivo_status'
                  AND table_schema IN (current_schema(), 'public')
                LIMIT 1
                """
            )
            if cur.fetchone():
                _VINCOLO_COLS_OK = True
                return
        except Exception:
            _rollback_vinculo(cur)
        raise RuntimeError(
            "Colunas de status do vínculo indisponíveis. "
            "Aplique o SQL 095_vinculo_pausar_encerrar.sql no banco."
        )


def _zerar_estoque_vitrine_vinculo(cur, id_vendedor: int, id_fornecedor: int) -> int:
    """Zera estoque mantendo produtos visíveis (ativo = TRUE)."""
    cur.execute(
        """
        UPDATE tbl_produto_vendedor
        SET estoque_vitrine = 0, atualizado_em = NOW()
        WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
        """,
        (id_vendedor, id_fornecedor),
    )
    return int(cur.rowcount or 0)


def _enviar_email_vinculo(
    cur,
    *,
    id_destinatario_tenant: int,
    assunto: str,
    html: str,
    tag: str,
) -> None:
    from core.pedidos.notificacoes import email_dono_tenant

    email, _nome = email_dono_tenant(cur, id_destinatario_tenant)
    if not email:
        return
    try:
        from api.brevo.srotas_brevo import enviar_email

        enviar_email([email], assunto, html, tag=tag)
    except Exception:
        pass


def _carregar_vinculo(cur, id_vinculo: int) -> dict | None:
    garantir_colunas_vinculo_status(cur)
    cur.execute(
        """
        SELECT id, id_tenant_vendedor, id_tenant_fornecedor, status,
               motivo_status, status_alterado_por_usuario, status_alterado_por_lado
        FROM tbl_vinculo_vendedor_fornecedor
        WHERE id = %s
        """,
        (id_vinculo,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "id": int(row[0]),
        "id_tenant_vendedor": int(row[1]),
        "id_tenant_fornecedor": int(row[2]),
        "status": (row[3] or "").strip().lower(),
        "motivo_status": row[4] or "",
        "status_alterado_por_usuario": int(row[5]) if row[5] is not None else None,
        "status_alterado_por_lado": (row[6] or "").strip().lower() or None,
    }


def _nomes_tenants(cur, id_vendedor: int, id_fornecedor: int) -> tuple[str, str]:
    cur.execute(
        """
        SELECT id, COALESCE(NULLIF(TRIM(nome_fantasia), ''), NULLIF(TRIM(nome), ''), 'Conta')
        FROM tbl_tenant WHERE id IN (%s, %s)
        """,
        (id_vendedor, id_fornecedor),
    )
    mapa = {int(r[0]): (r[1] or "Conta") for r in cur.fetchall()}
    return mapa.get(id_vendedor, "Vendedor"), mapa.get(id_fornecedor, "Fornecedor")


def pausar_vinculo(
    cur,
    id_vinculo: int,
    *,
    id_tenant_ator: int,
    lado: str,
    id_usuario: int | None,
    motivo: str,
) -> dict:
    """Pausa vínculo: mantém associação, zera estoques, bloqueia novos produtos."""
    motivo = (motivo or "").strip()
    if len(motivo) < 5:
        raise ValueError("Informe o motivo da pausa (mínimo 5 caracteres).")
    lado = (lado or "").strip().lower()
    if lado not in ("vendedor", "fornecedor"):
        raise ValueError("Lado inválido.")

    vinc = _carregar_vinculo(cur, id_vinculo)
    if not vinc:
        raise ValueError("Vínculo não encontrado.")
    if lado == "fornecedor" and vinc["id_tenant_fornecedor"] != id_tenant_ator:
        raise ValueError("Vínculo não pertence a este fornecedor.")
    if lado == "vendedor" and vinc["id_tenant_vendedor"] != id_tenant_ator:
        raise ValueError("Vínculo não pertence a este vendedor.")
    if vinc["status"] != "ativo":
        raise ValueError("Só é possível pausar um vínculo ativo.")

    cur.execute(
        """
        UPDATE tbl_vinculo_vendedor_fornecedor
        SET status = 'pausado',
            motivo_status = %s,
            status_alterado_em = NOW(),
            status_alterado_por_usuario = %s,
            status_alterado_por_lado = %s
        WHERE id = %s AND status = 'ativo'
        """,
        (motivo[:2000], id_usuario, lado, id_vinculo),
    )
    if cur.rowcount == 0:
        raise ValueError("Não foi possível pausar o vínculo.")

    qtd = _zerar_estoque_vitrine_vinculo(
        cur, vinc["id_tenant_vendedor"], vinc["id_tenant_fornecedor"]
    )
    nome_vd, nome_fn = _nomes_tenants(cur, vinc["id_tenant_vendedor"], vinc["id_tenant_fornecedor"])
    outro = vinc["id_tenant_vendedor"] if lado == "fornecedor" else vinc["id_tenant_fornecedor"]
    quem = nome_fn if lado == "fornecedor" else nome_vd
    com = nome_vd if lado == "fornecedor" else nome_fn
    html = (
        f"<p>Olá,</p>"
        f"<p>O vínculo entre <strong>{esc_html(quem)}</strong> e <strong>{esc_html(com)}</strong> "
        f"foi <strong>pausado</strong>.</p>"
        f"<p>Os estoques dos produtos desse vínculo foram zerados e novos produtos ficam bloqueados "
        f"até a retomada.</p>"
        f"<p><strong>Motivo:</strong> {esc_html(motivo)}</p>"
        f"<p>Pedidos já abertos continuam normalmente.</p>"
    )
    _enviar_email_vinculo(
        cur,
        id_destinatario_tenant=outro,
        assunto="Vínculo pausado • DropNexo",
        html=html,
        tag="dropnexo_vinculo_pausado",
    )
    return {"status": "pausado", "produtos_zerados": qtd, "motivo": motivo}


def despausar_vinculo(
    cur,
    id_vinculo: int,
    *,
    id_tenant_ator: int,
    lado: str,
    id_usuario: int | None,
) -> dict:
    """Retoma vínculo pausado — somente quem pausou (mesmo usuário)."""
    lado = (lado or "").strip().lower()
    if lado not in ("vendedor", "fornecedor"):
        raise ValueError("Lado inválido.")

    vinc = _carregar_vinculo(cur, id_vinculo)
    if not vinc:
        raise ValueError("Vínculo não encontrado.")
    if lado == "fornecedor" and vinc["id_tenant_fornecedor"] != id_tenant_ator:
        raise ValueError("Vínculo não pertence a este fornecedor.")
    if lado == "vendedor" and vinc["id_tenant_vendedor"] != id_tenant_ator:
        raise ValueError("Vínculo não pertence a este vendedor.")
    if vinc["status"] != "pausado":
        raise ValueError("Este vínculo não está pausado.")
    if vinc["status_alterado_por_lado"] and vinc["status_alterado_por_lado"] != lado:
        raise ValueError("Somente quem pausou o vínculo pode retomá-lo.")
    if (
        vinc["status_alterado_por_usuario"] is not None
        and id_usuario is not None
        and int(vinc["status_alterado_por_usuario"]) != int(id_usuario)
    ):
        raise ValueError("Somente o usuário que pausou pode despausar este vínculo.")

    cur.execute(
        """
        UPDATE tbl_vinculo_vendedor_fornecedor
        SET status = 'ativo',
            motivo_status = NULL,
            status_alterado_em = NOW(),
            status_alterado_por_usuario = %s,
            status_alterado_por_lado = %s
        WHERE id = %s AND status = 'pausado'
        """,
        (id_usuario, lado, id_vinculo),
    )
    if cur.rowcount == 0:
        raise ValueError("Não foi possível despausar o vínculo.")

    nome_vd, nome_fn = _nomes_tenants(cur, vinc["id_tenant_vendedor"], vinc["id_tenant_fornecedor"])
    outro = vinc["id_tenant_vendedor"] if lado == "fornecedor" else vinc["id_tenant_fornecedor"]
    quem = nome_fn if lado == "fornecedor" else nome_vd
    com = nome_vd if lado == "fornecedor" else nome_fn
    html = (
        f"<p>Olá,</p>"
        f"<p>O vínculo entre <strong>{esc_html(quem)}</strong> e <strong>{esc_html(com)}</strong> "
        f"foi <strong>retomado</strong> (despausado).</p>"
        f"<p>A operação de catálogo e novos produtos volta a ficar liberada. "
        f"Os estoques serão atualizados conforme a sincronização/operação normal.</p>"
    )
    _enviar_email_vinculo(
        cur,
        id_destinatario_tenant=outro,
        assunto="Vínculo retomado • DropNexo",
        html=html,
        tag="dropnexo_vinculo_despausado",
    )
    return {"status": "ativo"}


def encerrar_vinculo(
    cur,
    id_vinculo: int,
    *,
    id_tenant_ator: int,
    lado: str,
    id_usuario: int | None,
    motivo: str,
) -> dict:
    """Encerra vínculo: exige nova solicitação; zera estoques; produtos ficam visíveis."""
    motivo = (motivo or "").strip()
    if len(motivo) < 5:
        raise ValueError("Informe o motivo do encerramento (mínimo 5 caracteres).")
    lado = (lado or "").strip().lower()
    if lado not in ("vendedor", "fornecedor"):
        raise ValueError("Lado inválido.")

    vinc = _carregar_vinculo(cur, id_vinculo)
    if not vinc:
        raise ValueError("Vínculo não encontrado.")
    if lado == "fornecedor" and vinc["id_tenant_fornecedor"] != id_tenant_ator:
        raise ValueError("Vínculo não pertence a este fornecedor.")
    if lado == "vendedor" and vinc["id_tenant_vendedor"] != id_tenant_ator:
        raise ValueError("Vínculo não pertence a este vendedor.")
    if vinc["status"] not in ("ativo", "pausado"):
        raise ValueError("Só é possível encerrar um vínculo ativo ou pausado.")

    cur.execute(
        """
        UPDATE tbl_vinculo_vendedor_fornecedor
        SET status = 'inativo',
            inativado_em = NOW(),
            motivo_status = %s,
            status_alterado_em = NOW(),
            status_alterado_por_usuario = %s,
            status_alterado_por_lado = %s
        WHERE id = %s AND status IN ('ativo', 'pausado')
        """,
        (motivo[:2000], id_usuario, lado, id_vinculo),
    )
    if cur.rowcount == 0:
        raise ValueError("Não foi possível encerrar o vínculo.")

    qtd = _zerar_estoque_vitrine_vinculo(
        cur, vinc["id_tenant_vendedor"], vinc["id_tenant_fornecedor"]
    )
    nome_vd, nome_fn = _nomes_tenants(cur, vinc["id_tenant_vendedor"], vinc["id_tenant_fornecedor"])
    outro = vinc["id_tenant_vendedor"] if lado == "fornecedor" else vinc["id_tenant_fornecedor"]
    quem = nome_fn if lado == "fornecedor" else nome_vd
    com = nome_vd if lado == "fornecedor" else nome_fn
    html = (
        f"<p>Olá,</p>"
        f"<p>O vínculo entre <strong>{esc_html(quem)}</strong> e <strong>{esc_html(com)}</strong> "
        f"foi <strong>encerrado</strong>.</p>"
        f"<p>Os estoques foram zerados. Para voltar a operar juntos, será necessário "
        f"<strong>solicitar o vínculo novamente</strong> e aguardar aprovação.</p>"
        f"<p><strong>Motivo:</strong> {esc_html(motivo)}</p>"
        f"<p>Pedidos já abertos continuam normalmente.</p>"
    )
    _enviar_email_vinculo(
        cur,
        id_destinatario_tenant=outro,
        assunto="Vínculo encerrado • DropNexo",
        html=html,
        tag="dropnexo_vinculo_encerrado",
    )
    return {"status": "inativo", "produtos_zerados": qtd, "motivo": motivo}


def inativar_vinculo(cur, id_vinculo: int, id_fornecedor: int, motivo: str | None = None) -> None:
    """Compat: encerra pelo lado fornecedor."""
    encerrar_vinculo(
        cur,
        id_vinculo,
        id_tenant_ator=id_fornecedor,
        lado="fornecedor",
        id_usuario=session.get("id_usuario"),
        motivo=(motivo or "Vínculo encerrado pelo fornecedor.").strip(),
    )


def esc_html(s: str | None) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def listar_alertas_vinculo_tenant(cur, id_tenant: int) -> list[dict]:
    """Alertas globais de vínculos pausados/encerrados envolvendo o tenant."""
    garantir_colunas_vinculo_status(cur)
    cur.execute(
        """
        SELECT
          v.id, v.status, v.motivo_status, v.status_alterado_em, v.status_alterado_por_lado,
          v.id_tenant_vendedor, v.id_tenant_fornecedor,
          COALESCE(NULLIF(TRIM(tv.nome_fantasia), ''), NULLIF(TRIM(tv.nome), ''), 'Vendedor'),
          COALESCE(NULLIF(TRIM(tf.nome_fantasia), ''), NULLIF(TRIM(tf.nome), ''), 'Fornecedor')
        FROM tbl_vinculo_vendedor_fornecedor v
        JOIN tbl_tenant tv ON tv.id = v.id_tenant_vendedor
        JOIN tbl_tenant tf ON tf.id = v.id_tenant_fornecedor
        WHERE v.status IN ('pausado', 'inativo')
          AND (v.id_tenant_vendedor = %s OR v.id_tenant_fornecedor = %s)
          AND v.status_alterado_em IS NOT NULL
          AND v.status_alterado_em >= (NOW() - INTERVAL '90 days')
        ORDER BY v.status_alterado_em DESC
        LIMIT 8
        """,
        (id_tenant, id_tenant),
    )
    out = []
    for row in cur.fetchall():
        st = (row[1] or "").strip().lower()
        lado_ator = (row[4] or "").strip().lower()
        id_vd, id_fn = int(row[5]), int(row[6])
        nome_vd, nome_fn = row[7], row[8]
        sou_vendedor = id_tenant == id_vd
        outro_nome = nome_fn if sou_vendedor else nome_vd
        if st == "pausado":
            texto = f"Vínculo com {outro_nome} está pausado. Estoques zerados e novos produtos bloqueados."
        else:
            texto = (
                f"Vínculo com {outro_nome} foi encerrado. "
                f"Estoques zerados — para retomar, solicite o vínculo novamente."
            )
        motivo = (row[2] or "").strip()
        if motivo:
            texto += f" Motivo: {motivo}"
        out.append(
            {
                "id": int(row[0]),
                "status": st,
                "texto": texto,
                "motivo": motivo,
                "alterado_em": row[3].isoformat() if row[3] else "",
                "por_lado": lado_ator or "",
                "parceiro": outro_nome,
            }
        )
    return out


def snapshot_vendedor_sessao() -> dict:
    return {
        "tenant_nome": session.get("tenant_nome"),
        "tenant_slug": session.get("tenant_slug"),
        "usuario_nome": session.get("nome"),
        "usuario_email": session.get("email"),
        "id_tenant": session.get("id_tenant"),
        "id_usuario": session.get("id_usuario"),
    }


def _formatar_documento(doc: str | None, tipo: str | None) -> str:
    d = "".join(c for c in (doc or "") if c.isdigit())
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return doc or ""


def montar_snapshot_vendedor(cur, id_vendedor: int, id_usuario: int | None) -> dict:
    """Snapshot completo gravado na solicitação de vínculo (dados para decisão do fornecedor)."""
    base: dict = {"id_tenant": id_vendedor, "id_usuario": id_usuario}
    cur.execute(
        """
        SELECT COALESCE(t.nome_fantasia, t.nome), t.slug,
               t.tipo_pessoa, t.documento, t.nome_completo, COALESCE(t.nome_fantasia, t.nome),
               t.razao_social, t.cep, t.logradouro, t.numero, t.complemento,
               t.bairro, t.cidade, t.uf, t.telefone_comercial, t.celular_comercial,
               t.email_comercial, t.criado_em, t.tipo_negocio, t.site,
               t.faturamento_ultimo_ano, t.tamanho_empresa
        FROM tbl_tenant t
        WHERE t.id = %s
        """,
        (id_vendedor,),
    )
    row = cur.fetchone()
    if row:
        base["tenant_nome"] = row[0]
        base["tenant_slug"] = row[1]
        endereco_parts = [row[8], row[9], row[10], row[11], row[12], row[13]]
        endereco = ", ".join(p for p in endereco_parts if p)
        base.update(
            {
                "tipo_pessoa": row[2],
                "documento": row[3],
                "documento_formatado": _formatar_documento(row[3], row[2]),
                "nome_completo": row[4],
                "nome_fantasia": row[5],
                "razao_social": row[6] or "",
                "cep": row[7] or "",
                "endereco": endereco,
                "logradouro": row[8] or "",
                "numero": row[9] or "",
                "complemento": row[10] or "",
                "bairro": row[11] or "",
                "cidade": row[12] or "",
                "uf": row[13] or "",
                "telefone_comercial": row[14] or "",
                "celular_comercial": row[15] or "",
                "email_comercial": row[16] or "",
                "cadastro_desde": row[17].isoformat() if row[17] else "",
                "tipo_negocio": row[18] or "",
                "site": row[19] or "",
                "faturamento_ultimo_ano": row[20] or "",
                "tamanho_empresa": row[21] or "",
            }
        )

    if id_usuario:
        cur.execute(
            "SELECT nome, email, whatsapp FROM tbl_usuario WHERE id = %s",
            (id_usuario,),
        )
        u = cur.fetchone()
        if u:
            base["usuario_nome"] = u[0]
            base["usuario_email"] = u[1]
            base["usuario_whatsapp"] = u[2] or ""

    cur.execute(
        """
        SELECT COUNT(*)::int FROM tbl_vinculo_vendedor_fornecedor
        WHERE id_tenant_vendedor = %s AND status = 'ativo'
        """,
        (id_vendedor,),
    )
    base["qtd_fornecedores_ativos"] = int(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT COUNT(*)::int FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s AND ativo = TRUE
        """,
        (id_vendedor,),
    )
    base["qtd_produtos_vitrine"] = int(cur.fetchone()[0] or 0)

    return base
