# sistema/perfil/reativacao.py — conta encerrada, pedido e aprovação de reativação
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
log = logging.getLogger(__name__)

CUPOM_REATIVACAO = "REATIVA30"


def garantir_colunas_reativacao(cur) -> None:
    cur.execute(
        """
        ALTER TABLE tbl_cancelamento_conta
            ADD COLUMN IF NOT EXISTS solicitacao_reativacao_em TIMESTAMP,
            ADD COLUMN IF NOT EXISTS id_usuario_solicitante INTEGER,
            ADD COLUMN IF NOT EXISTS reativado_em TIMESTAMP,
            ADD COLUMN IF NOT EXISTS id_usuario_admin INTEGER
        """
    )


def _fmt_data_br(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        d = v.date()
    elif isinstance(v, date):
        d = v
    else:
        texto = str(v)[:10]
        if len(texto) == 10 and texto[4] == "-":
            y, m, d = texto.split("-")
            return f"{d}/{m}/{y}"
        return texto
    return d.strftime("%d/%m/%Y")


def localizar_conta_encerrada(cur, email: str) -> dict | None:
    """Usuário com senha ok, mas a conta do tenant foi encerrada."""
    garantir_colunas_reativacao(cur)
    cur.execute(
        """
        SELECT u.id, u.senha_hash, u.ativo, u.nome, u.email,
               t.id, COALESCE(NULLIF(t.nome_fantasia, ''), NULLIF(t.nome, ''), t.slug),
               c.concluido_em, c.solicitacao_reativacao_em
        FROM tbl_usuario u
        JOIN tbl_usuario_tenant ut ON ut.id_usuario = u.id
        JOIN tbl_tenant t ON t.id = ut.id_tenant
        JOIN tbl_cancelamento_conta c ON c.id_tenant = t.id
        WHERE lower(u.email) = %s
          AND t.ativo = FALSE
          AND (c.concluido_em IS NOT NULL OR COALESCE(c.etapa, 1) >= 3)
          AND c.reativado_em IS NULL
        ORDER BY c.concluido_em DESC NULLS LAST, t.id DESC
        LIMIT 1
        """,
        ((email or "").strip().lower(),),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "id_usuario": int(row[0]),
        "senha_hash": row[1],
        "usuario_ativo": bool(row[2]),
        "nome": row[3] or "",
        "email": row[4] or "",
        "id_tenant": int(row[5]),
        "tenant_nome": (row[6] or "").strip() or f"Conta #{row[5]}",
        "encerrada_em": row[7],
        "encerrada_em_br": _fmt_data_br(row[7]),
        "ja_solicitou": bool(row[8]),
        "solicitacao_em_br": _fmt_data_br(row[8]),
    }


def solicitar_reativacao(cur, *, id_tenant: int, id_usuario: int) -> dict:
    garantir_colunas_reativacao(cur)
    cur.execute(
        """
        SELECT concluido_em, solicitacao_reativacao_em, reativado_em
        FROM tbl_cancelamento_conta
        WHERE id_tenant = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    cur.execute("SELECT ativo FROM tbl_tenant WHERE id = %s", (id_tenant,))
    tenant = cur.fetchone()
    if not tenant:
        raise ValueError("Conta não encontrada.")
    if tenant[0]:
        raise ValueError("Esta conta já está ativa.")
    if row and row[2]:
        raise ValueError("Esta conta já foi reativada.")
    if row and row[1]:
        return {
            "ok": True,
            "ja_solicitou": True,
            "mensagem": (
                "Sua solicitação de reativação já está com a equipe DropNexo. "
                "Avisamos por e-mail quando a conta for liberada."
            ),
        }
    if row:
        cur.execute(
            """
            UPDATE tbl_cancelamento_conta
            SET solicitacao_reativacao_em = NOW(),
                id_usuario_solicitante = %s
            WHERE id_tenant = %s
              AND reativado_em IS NULL
            """,
            (id_usuario, id_tenant),
        )
    else:
        cur.execute(
            """
            INSERT INTO tbl_cancelamento_conta (
                id_tenant, id_usuario, etapa, concluido_em,
                solicitacao_reativacao_em, id_usuario_solicitante
            ) VALUES (%s, %s, 3, NOW(), NOW(), %s)
            ON CONFLICT (id_tenant) DO UPDATE SET
                solicitacao_reativacao_em = NOW(),
                id_usuario_solicitante = EXCLUDED.id_usuario_solicitante
            """,
            (id_tenant, id_usuario, id_usuario),
        )
    return {
        "ok": True,
        "ja_solicitou": False,
        "mensagem": (
            "Recebemos o pedido de reativação. "
            "A equipe DropNexo analisa e libera a conta. Você recebe um e-mail na liberação."
        ),
    }


def listar_solicitacoes_reativacao(cur) -> list[dict]:
    garantir_colunas_reativacao(cur)
    cur.execute(
        """
        SELECT t.id,
               COALESCE(NULLIF(t.nome_fantasia, ''), NULLIF(t.nome, ''), t.slug),
               t.slug, t.tipo_negocio, t.plano,
               c.concluido_em, c.solicitacao_reativacao_em,
               COALESCE(u.nome, ''), COALESCE(u.email, '')
        FROM tbl_cancelamento_conta c
        JOIN tbl_tenant t ON t.id = c.id_tenant
        LEFT JOIN tbl_usuario u ON u.id = c.id_usuario_solicitante
        WHERE c.solicitacao_reativacao_em IS NOT NULL
          AND c.reativado_em IS NULL
          AND t.ativo = FALSE
        ORDER BY c.solicitacao_reativacao_em DESC
        """
    )
    out = []
    for r in cur.fetchall():
        out.append(
            {
                "id_tenant": int(r[0]),
                "nome": (r[1] or "").strip() or f"Tenant #{r[0]}",
                "slug": r[2] or "",
                "tipo_negocio": r[3] or "",
                "plano": r[4] or "",
                "encerrada_em": r[5].isoformat() if r[5] else None,
                "encerrada_br": _fmt_data_br(r[5]),
                "solicitada_em": r[6].isoformat() if r[6] else None,
                "solicitada_br": _fmt_data_br(r[6]),
                "solicitante_nome": r[7] or "",
                "solicitante_email": r[8] or "",
            }
        )
    return out


def _garantir_cupom_reativacao(cur) -> dict:
    from sistema.financeiro.cupom import obter_cupom_por_codigo, salvar_cupom

    atual = obter_cupom_por_codigo(cur, CUPOM_REATIVACAO)
    if atual and atual.get("ativo"):
        return atual
    valido = date.today() + timedelta(days=365)
    return salvar_cupom(
        cur,
        {
            "codigo": CUPOM_REATIVACAO,
            "descricao": "Boas-vindas na reativação — 1º mês com 100% de desconto",
            "tipo_desconto": "percentual",
            "valor_desconto": 100,
            "periodo": "mensal",
            "valido_ate": valido.isoformat(),
            "usos_max": None,
            "ativo": True,
            "ciclos_beneficio": 1,
            "beneficio_vitalicio": False,
        },
        id_cupom=int(atual["id"]) if atual else None,
    )


def reativar_conta(cur, id_tenant: int, *, id_admin: int | None = None) -> dict:
    garantir_colunas_reativacao(cur)
    cur.execute(
        """
        SELECT t.ativo, c.solicitacao_reativacao_em, c.reativado_em,
               COALESCE(NULLIF(t.nome_fantasia, ''), NULLIF(t.nome, ''), t.slug)
        FROM tbl_tenant t
        LEFT JOIN tbl_cancelamento_conta c ON c.id_tenant = t.id
        WHERE t.id = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Tenant não encontrado.")
    if row[0]:
        raise ValueError("Esta conta já está ativa.")
    if row[2]:
        raise ValueError("Esta conta já foi reativada.")
    if not row[1]:
        raise ValueError("Não há solicitação de reativação para esta conta.")

    try:
        cur.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'tbl_tenant' AND column_name = 'inativado_em'
            """
        )
        if cur.fetchone():
            cur.execute(
                "UPDATE tbl_tenant SET ativo = TRUE, inativado_em = NULL WHERE id = %s",
                (id_tenant,),
            )
        else:
            cur.execute("UPDATE tbl_tenant SET ativo = TRUE WHERE id = %s", (id_tenant,))
    except Exception:
        cur.execute("UPDATE tbl_tenant SET ativo = TRUE WHERE id = %s", (id_tenant,))
    cur.execute(
        "UPDATE tbl_usuario_tenant SET ativo = TRUE WHERE id_tenant = %s",
        (id_tenant,),
    )
    cur.execute(
        """
        UPDATE tbl_usuario u
        SET ativo = TRUE
        WHERE u.eh_desenvolvedor IS NOT TRUE
          AND EXISTS (
            SELECT 1 FROM tbl_usuario_tenant ut
            WHERE ut.id_usuario = u.id AND ut.id_tenant = %s
          )
        """,
        (id_tenant,),
    )
    cur.execute(
        """
        UPDATE tbl_cancelamento_conta
        SET reativado_em = NOW(),
            id_usuario_admin = %s
        WHERE id_tenant = %s
        """,
        (id_admin, id_tenant),
    )

    cupom = _garantir_cupom_reativacao(cur)
    try:
        from sistema.financeiro.cobranca import garantir_cobranca_tenant

        garantir_cobranca_tenant(cur, id_tenant)
        # 1 ciclo à frente (1º mês 100%): o cupom ainda não foi usado no checkout.
        cur.execute(
            """
            UPDATE tbl_tenant_cobranca
            SET id_cupom_beneficio = %s,
                cupom_ciclos_restantes = 1,
                atualizado_em = NOW()
            WHERE id_tenant = %s
            """,
            (int(cupom["id"]), int(id_tenant)),
        )
    except Exception:
        log.exception("Benefício %s não aplicado ao tenant %s", CUPOM_REATIVACAO, id_tenant)

    cur.execute(
        """
        SELECT u.email, u.nome
        FROM tbl_usuario_tenant ut
        JOIN tbl_usuario u ON u.id = ut.id_usuario
        JOIN tbl_perfil pf ON pf.id = ut.id_perfil
        WHERE ut.id_tenant = %s AND lower(pf.codigo) = 'dono' AND u.email IS NOT NULL
        ORDER BY ut.id
        LIMIT 1
        """,
        (id_tenant,),
    )
    dono = cur.fetchone()
    if not dono:
        cur.execute(
            """
            SELECT u.email, u.nome
            FROM tbl_usuario_tenant ut
            JOIN tbl_usuario u ON u.id = ut.id_usuario
            WHERE ut.id_tenant = %s AND u.email IS NOT NULL
            ORDER BY ut.id
            LIMIT 1
            """,
            (id_tenant,),
        )
        dono = cur.fetchone()

    return {
        "ok": True,
        "id_tenant": id_tenant,
        "tenant_nome": (row[3] or "").strip() or f"Tenant #{id_tenant}",
        "email": (dono[0] if dono else "") or "",
        "nome_usuario": (dono[1] if dono else "") or "",
        "cupom": CUPOM_REATIVACAO,
        "mensagem": "Conta reativada. E-mail de boas-vindas e cupom REATIVA30 preparados.",
    }


def enviar_email_conta_reativada(
    *,
    email: str,
    nome_usuario: str,
    nome_conta: str,
    cupom: str = CUPOM_REATIVACAO,
) -> tuple[bool, str]:
    from flask import render_template
    from api.brevo.srotas_brevo import enviar_email
    from global_utils import obter_base_url

    if not email or "@" not in email:
        return False, "E-mail do titular ausente."
    link_login = f"{obter_base_url().rstrip('/')}/login"
    html = render_template(
        "cadastro/emails/conta_reativada.html",
        titulo_email="Conta reativada • DropNexo",
        nome_usuario=nome_usuario or "usuário",
        nome_conta=nome_conta or "",
        cupom=cupom,
        link_login=link_login,
        ano=datetime.now().year,
    )
    ok, msg, _ = enviar_email(
        [email],
        "Conta reativada • DropNexo",
        html,
        tag="dropnexo_reativacao",
    )
    return ok, msg
