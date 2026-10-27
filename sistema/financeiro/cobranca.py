# sistema/financeiro/cobranca.py — assinatura, faturas Efi, inadimplência boleto
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from flask import render_template

from api.brevo.srotas_brevo import enviar_email
from global_utils import obter_base_url
from sistema.planos.limites import limites_plano_tenant

log = logging.getLogger(__name__)

# Primeiro boleto não libera o plano. Cobrança seguinte mantém o plano.
# 30 dias após o vencimento sem pagamento: volta ao gratuito e cancela a recorrência.
DIAS_UTEIS_GRACA_BOLETO = 30
DIAS_GRACA_INADIMPLENCIA = 30
DIAS_ATRASO_CANCELA = 30
PLANOS_PAGOS = ("professional", "scale", "enterprise")
FORMAS = ("boleto", "pix", "cartao")


def adicionar_dias_uteis(inicio: date, dias: int) -> date:
    """Soma dias úteis (seg–sex), sem feriados."""
    if dias <= 0:
        return inicio
    d = inicio
    add = 0
    while add < dias:
        d += timedelta(days=1)
        if d.weekday() < 5:
            add += 1
    return d


def adicionar_meses(inicio: date, meses: int) -> date:
    """Soma meses calendário mantendo o dia quando possível."""
    meses = max(0, int(meses or 0))
    y = inicio.year + (inicio.month - 1 + meses) // 12
    m = (inicio.month - 1 + meses) % 12 + 1
    # último dia do mês destino
    if m == 12:
        ultimo = date(y + 1, 1, 1) - timedelta(days=1)
    else:
        ultimo = date(y, m + 1, 1) - timedelta(days=1)
    return date(y, m, min(inicio.day, ultimo.day))


def prazo_rebaixa_boleto(criado_em: date | datetime | None) -> date | None:
    if not criado_em:
        return None
    base = criado_em.date() if isinstance(criado_em, datetime) else criado_em
    return adicionar_dias_uteis(base, DIAS_UTEIS_GRACA_BOLETO)


def liberar_plano_tenant(cur, id_tenant: int, plano_slug: str, *, forma: str | None = None) -> None:
    """Aplica o plano pago na conta (ex.: boleto na adesão)."""
    slug = (plano_slug or "").strip().lower()
    if slug not in PLANOS_PAGOS:
        return
    cur.execute("UPDATE tbl_tenant SET plano = %s WHERE id = %s", (slug, id_tenant))
    if forma:
        cur.execute(
            """
            UPDATE tbl_tenant_cobranca
            SET plano_slug = %s, plano_slug_pendente = NULL,
                forma_pagamento = %s, atualizado_em = NOW()
            WHERE id_tenant = %s
            """,
            (slug, forma, id_tenant),
        )
    else:
        cur.execute(
            """
            UPDATE tbl_tenant_cobranca
            SET plano_slug = %s, plano_slug_pendente = NULL, atualizado_em = NOW()
            WHERE id_tenant = %s
            """,
            (slug, id_tenant),
        )

STATUS_LABEL = {
    "pendente": "Emitida",
    "pago": "Paga",
    "vencido": "Vencida",
    "cancelado": "Cancelada",
    "bloqueado": "Bloqueada (MED)",
}


def _json_resumo(obj: Any, lim: int = 4000) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    return s[:lim]


def registrar_efi_log(
    cur,
    *,
    id_tenant: int | None,
    id_fatura: int | None,
    direcao: str,
    operacao: str,
    ok: bool,
    http_status: int | None = None,
    efi_charge_id: str | None = None,
    request_resumo: Any = None,
    response_resumo: Any = None,
) -> None:
    try:
        cur.execute(
            """
            INSERT INTO tbl_efi_log (
                id_tenant, id_fatura, direcao, operacao, http_status, efi_charge_id,
                request_resumo, response_resumo, ok
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                id_tenant,
                id_fatura,
                (direcao or "out")[:20],
                (operacao or "ops")[:80],
                http_status,
                (efi_charge_id or None),
                _json_resumo(request_resumo) if request_resumo is not None else None,
                _json_resumo(response_resumo) if response_resumo is not None else None,
                bool(ok),
            ),
        )
    except Exception:
        log.exception("Falha ao gravar tbl_efi_log")


def _email_fallback_tenant(cur, id_tenant: int) -> str:
    """E-mail de cobrança: dono → comercial → qualquer usuário ativo."""
    try:
        from core.pedidos.notificacoes import email_dono_tenant

        email, _ = email_dono_tenant(cur, id_tenant)
        if email and "@" in email:
            return email.strip()
    except Exception:
        pass
    cur.execute(
        """
        SELECT COALESCE(NULLIF(trim(t.email_comercial), ''), '')
        FROM tbl_tenant t WHERE t.id = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    email = (row[0] if row else "") or ""
    if email and "@" in email:
        return email.strip()
    cur.execute(
        """
        SELECT u.email FROM tbl_usuario_tenant ut
        JOIN tbl_usuario u ON u.id = ut.id_usuario
        WHERE ut.id_tenant = %s AND ut.ativo AND u.ativo
          AND u.email IS NOT NULL AND trim(u.email) <> ''
        ORDER BY ut.id LIMIT 1
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    return ((row[0] if row else "") or "").strip()


def garantir_colunas_assinatura(cur) -> None:
    cur.execute(
        """
        ALTER TABLE tbl_tenant_cobranca
            ADD COLUMN IF NOT EXISTS efi_subscription_id VARCHAR(40),
            ADD COLUMN IF NOT EXISTS efi_plan_id VARCHAR(40),
            ADD COLUMN IF NOT EXISTS assinatura_status VARCHAR(20),
            ADD COLUMN IF NOT EXISTS cancelado_em TIMESTAMP
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_efi_plano_assinatura (
            id SERIAL PRIMARY KEY,
            plano_slug VARCHAR(40) NOT NULL,
            periodicidade VARCHAR(20) NOT NULL,
            valor_centavos INTEGER NOT NULL,
            intervalo_meses INTEGER NOT NULL,
            efi_plan_id VARCHAR(40) NOT NULL,
            criado_em TIMESTAMP DEFAULT NOW(),
            UNIQUE (plano_slug, periodicidade, valor_centavos)
        )
        """
    )


def garantir_cobranca_tenant(cur, id_tenant: int) -> None:
    garantir_colunas_assinatura(cur)
    cur.execute("SELECT 1 FROM tbl_tenant_cobranca WHERE id_tenant = %s", (id_tenant,))
    if cur.fetchone():
        return
    cur.execute("SELECT plano FROM tbl_tenant WHERE id = %s", (id_tenant,))
    row = cur.fetchone()
    plano = (row[0] if row else None) or "starter"
    email = _email_fallback_tenant(cur, id_tenant) or None
    cur.execute(
        """
        INSERT INTO tbl_tenant_cobranca (id_tenant, plano_slug, email_cobranca, inicio_cobranca)
        VALUES (%s, %s, %s, CURRENT_DATE)
        """,
        (id_tenant, plano, email),
    )


def obter_plano_db(cur, slug: str) -> dict | None:
    cur.execute(
        """
        SELECT slug, nome, valor_centavos, periodicidade, descricao
        FROM tbl_plano WHERE slug = %s AND ativo = TRUE
        """,
        (slug,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "slug": row[0],
        "nome": row[1],
        "valor_centavos": int(row[2] or 0),
        "periodicidade": row[3] or "mensal",
        "descricao": row[4] or "",
    }


def _dados_cliente_cobranca(cur, id_tenant: int) -> dict:
    garantir_cobranca_tenant(cur, id_tenant)
    cur.execute(
        """
        SELECT tc.dia_vencimento, tc.email_cobranca, tc.forma_pagamento, tc.plano_slug,
               tc.plano_slug_pendente,
               COALESCE(t.nome_completo, t.nome_fantasia, t.nome), t.documento, t.nome,
               t.plano, t.tipo_negocio,
               COALESCE(t.celular_comercial, t.telefone_comercial, ''),
               COALESCE(t.cep, ''), COALESCE(t.logradouro, ''), COALESCE(t.numero, ''),
               COALESCE(t.complemento, ''), COALESCE(t.bairro, ''),
               COALESCE(t.cidade, ''), COALESCE(t.uf, '')
        FROM tbl_tenant_cobranca tc
        JOIN tbl_tenant t ON t.id = tc.id_tenant
        WHERE tc.id_tenant = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Cobrança não configurada.")
    email = (row[1] or "").strip()
    if not email or "@" not in email:
        email = _email_fallback_tenant(cur, id_tenant)
        if email:
            cur.execute(
                """
                UPDATE tbl_tenant_cobranca
                SET email_cobranca = %s, atualizado_em = NOW()
                WHERE id_tenant = %s
                  AND (email_cobranca IS NULL OR trim(email_cobranca) = '')
                """,
                (email, id_tenant),
            )
    return {
        "dia_vencimento": int(row[0] or 15),
        "email_cobranca": email,
        "forma_pagamento": (row[2] or "boleto").strip().lower(),
        "plano_slug": row[3],
        "plano_slug_pendente": row[4],
        "nome_cliente": row[5] or row[7] or "Cliente",
        "documento": row[6] or "",
        "nome_tenant": row[7] or "",
        "plano_atual": row[8] or "starter",
        "tipo_negocio": row[9] or "vendedor",
        "telefone": (row[10] or "").strip(),
        "endereco": {
            "cep": row[11] or "",
            "logradouro": row[12] or "",
            "numero": row[13] or "",
            "complemento": row[14] or "",
            "bairro": row[15] or "",
            "cidade": row[16] or "",
            "uf": row[17] or "",
        },
    }


def proximo_vencimento(dia: int, base: date | None = None) -> date:
    hoje = base or date.today()
    dia = max(1, min(28, int(dia or 15)))
    try:
        venc = hoje.replace(day=dia)
    except ValueError:
        venc = hoje.replace(day=28)
    if venc <= hoje:
        if hoje.month == 12:
            venc = date(hoje.year + 1, 1, dia)
        else:
            try:
                venc = date(hoje.year, hoje.month + 1, dia)
            except ValueError:
                venc = date(hoje.year, hoje.month + 1, 28)
    return venc


def referencia_mes(d: date | None = None) -> str:
    return (d or date.today()).strftime("%Y-%m")


_FATURA_REF_OK: bool | None = None


def _rollback_cur(cur) -> None:
    try:
        cur.connection.rollback()
    except Exception:
        pass


def garantir_referencia_fatura(cur) -> None:
    """referencia precisa caber YYYY-MM-S / YYYY-MM-A (semestral/anual)."""
    global _FATURA_REF_OK
    if _FATURA_REF_OK is True:
        return
    try:
        cur.execute(
            """
            SELECT character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'tbl_fatura'
              AND column_name = 'referencia'
              AND table_schema IN (current_schema(), 'public')
            LIMIT 1
            """
        )
        row = cur.fetchone()
        lim = int(row[0]) if row and row[0] is not None else None
        if lim is not None and lim >= 20:
            _FATURA_REF_OK = True
            return
        cur.execute(
            """
            ALTER TABLE tbl_fatura
                ALTER COLUMN referencia TYPE VARCHAR(20)
            """
        )
        _FATURA_REF_OK = True
    except Exception as e:
        _rollback_cur(cur)
        # Revalida: DBA pode ter aplicado o ALTER manualmente
        try:
            cur.execute(
                """
                SELECT character_maximum_length
                FROM information_schema.columns
                WHERE table_name = 'tbl_fatura'
                  AND column_name = 'referencia'
                  AND table_schema IN (current_schema(), 'public')
                LIMIT 1
                """
            )
            row = cur.fetchone()
            lim = int(row[0]) if row and row[0] is not None else None
            if lim is not None and lim >= 20:
                _FATURA_REF_OK = True
                return
        except Exception:
            _rollback_cur(cur)
        raise RuntimeError(
            "Campo referencia da fatura está limitado (VARCHAR curto). "
            "Aplique no banco: ALTER TABLE tbl_fatura ALTER COLUMN referencia TYPE VARCHAR(20);"
        ) from e


def fatura_dict(row) -> dict:
    # id, referencia, valor, status, forma, plano, link_boleto, codigo, pix, qr, link_pag,
    # venc, pago, criado, efi_charge, efi_txid,
    # periodicidade, meses, id_cupom, cupom_codigo, valor_cheio, desc_periodo, desc_cupom
    st = row[3] or "pendente"
    d = {
        "id": row[0],
        "referencia": row[1],
        "valor_centavos": int(row[2] or 0),
        "valor_formatado": f"R$ {(int(row[2] or 0) / 100):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "status": st,
        "status_label": STATUS_LABEL.get(st, st),
        "forma_pagamento": row[4] or "boleto",
        "plano_slug": row[5],
        "link_boleto": row[6],
        "codigo_barras": row[7],
        "pix_copia_cola": row[8],
        "pix_qrcode": row[9],
        "link_pagamento": row[10],
        "vencimento_em": row[11].isoformat() if row[11] else None,
        "pago_em": row[12].isoformat() if row[12] else None,
        "criado_em": row[13].isoformat() if row[13] else None,
        "efi_charge_id": row[14],
        "efi_txid": row[15] if len(row) > 15 else None,
        "periodicidade": row[16] if len(row) > 16 else "mensal",
        "meses_cobertos": int(row[17] or 1) if len(row) > 17 else 1,
        "id_cupom": row[18] if len(row) > 18 else None,
        "cupom_codigo": row[19] if len(row) > 19 else None,
        "valor_cheio_centavos": int(row[20] or 0) if len(row) > 20 and row[20] is not None else None,
        "desconto_periodo_centavos": int(row[21] or 0) if len(row) > 21 else 0,
        "desconto_cupom_centavos": int(row[22] or 0) if len(row) > 22 else 0,
    }
    return d


_FATURA_COLS = """
    id, referencia, valor_centavos, status, forma_pagamento, plano_slug,
    link_boleto, codigo_barras, pix_copia_cola, pix_qrcode, link_pagamento,
    vencimento_em, pago_em, criado_em, efi_charge_id, efi_txid,
    periodicidade, meses_cobertos, id_cupom, cupom_codigo,
    valor_cheio_centavos, desconto_periodo_centavos, desconto_cupom_centavos
"""


def referencia_assinatura(periodo: str, d: date | None = None) -> str:
    base = (d or date.today()).strftime("%Y-%m")
    suf = {"mensal": "", "semestral": "-S", "anual": "-A"}.get(periodo, "")
    return f"{base}{suf}"


def listar_faturas(cur, id_tenant: int, *, page: int = 1, por_pagina: int = 20) -> dict:
    page = max(1, page)
    por_pagina = min(50, max(5, por_pagina))
    cur.execute("SELECT COUNT(*) FROM tbl_fatura WHERE id_tenant = %s", (id_tenant,))
    total = int(cur.fetchone()[0] or 0)
    off = (page - 1) * por_pagina
    cur.execute(
        f"""
        SELECT {_FATURA_COLS}
        FROM tbl_fatura WHERE id_tenant = %s
        ORDER BY criado_em DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        (id_tenant, por_pagina, off),
    )
    itens = [fatura_dict(r) for r in cur.fetchall()]
    return {
        "faturas": itens,
        "total": total,
        "pagina": page,
        "total_paginas": max(1, (total + por_pagina - 1) // por_pagina),
    }


def obter_fatura(cur, id_tenant: int, id_fatura: int) -> dict | None:
    cur.execute(
        f"SELECT {_FATURA_COLS} FROM tbl_fatura WHERE id = %s AND id_tenant = %s",
        (id_fatura, id_tenant),
    )
    row = cur.fetchone()
    return fatura_dict(row) if row else None


def fatura_aberta_alerta(cur, id_tenant: int) -> dict | None:
    """Banner: fatura pendente/vencida mais crítica."""
    cur.execute(
        f"""
        SELECT {_FATURA_COLS}
        FROM tbl_fatura
        WHERE id_tenant = %s AND status IN ('pendente', 'vencido')
        ORDER BY
          CASE status WHEN 'vencido' THEN 0 ELSE 1 END,
          vencimento_em ASC NULLS LAST
        LIMIT 1
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    return fatura_dict(row) if row else None


def _email_links() -> dict:
    base = obter_base_url()
    return {
        "url_politica_privacidade": os.getenv("URL_POLITICA_PRIVACIDADE") or f"{base}/privacidade",
        "url_politica_interna": os.getenv("URL_POLITICA_INTERNA") or f"{base}/politica-interna",
        "url_dpo": os.getenv("URL_DPO") or f"{base}/dpo",
        "ano": datetime.now().year,
    }


def _enviar_email_fatura(
    cur,
    id_tenant: int,
    fatura: dict,
    *,
    tipo: str,
    criado_por: int | None = None,
) -> tuple[bool, int | None]:
    cli = _dados_cliente_cobranca(cur, id_tenant)
    email = cli["email_cobranca"]
    if not email or "@" not in email:
        cur.execute(
            """
            SELECT u.email FROM tbl_usuario_tenant ut
            JOIN tbl_usuario u ON u.id = ut.id_usuario
            JOIN tbl_perfil pf ON pf.id = ut.id_perfil
            WHERE ut.id_tenant = %s AND ut.ativo AND u.ativo AND lower(pf.codigo)='dono'
            LIMIT 1
            """,
            (id_tenant,),
        )
        r = cur.fetchone()
        email = (r[0] if r else "") or ""
    if not email or "@" not in email:
        return False, None
    base = obter_base_url().rstrip("/")
    assuntos = {
        "emitida": f"Fatura {fatura['referencia']} emitida • DropNexo",
        "aviso": f"Fatura {fatura['referencia']} em atraso • DropNexo",
        "rebaixado": "Plano rebaixado para Explorar • DropNexo",
        "pago": f"Pagamento confirmado — fatura {fatura['referencia']} • DropNexo",
        "lembrete": f"Lembrete — fatura {fatura['referencia']} • DropNexo",
    }
    forma_email = (fatura.get("forma_pagamento") or "").strip().lower()
    if forma_email == "boleto":
        texto_emitida = (
            "Boleto emitido. O plano só é liberado quando o banco confirmar o pagamento. "
            "Essa confirmação pode levar até 3 dias, conforme o banco em que o boleto foi pago."
        )
    else:
        texto_emitida = (
            "Fatura emitida. O plano será liberado quando o pagamento for confirmado."
        )
    mensagens = {
        "emitida": texto_emitida,
        "aviso": (
            f"Sua fatura ainda não foi paga. Se continuar em aberto por {DIAS_ATRASO_CANCELA} dias "
            "depois do vencimento, o plano volta ao gratuito (Explorar), a recorrência é cancelada "
            "e as integrações ficam bloqueadas (a conexão não é removida)."
        ),
        "rebaixado": (
            "Sua conta voltou ao plano Explorar por falta de pagamento e a recorrência foi cancelada. "
            "Integrações permanecem conectadas, mas o acesso e as atualizações ficam bloqueados até assinar novamente."
        ),
        "pago": "Recebemos o pagamento. Seu plano está liberado.",
        "lembrete": (
            "Há uma cobrança em aberto na sua conta. "
            "Se o pagamento já foi feito, desconsidere este lembrete."
        ),
    }
    tag = "dropnexo_fatura_lembrete" if tipo == "lembrete" else "dropnexo_financeiro"
    link_boleto = (fatura.get("link_boleto") or "").strip()
    link_acao = link_boleto or f"{base}/financeiro"
    rotulo_acao = "Abrir boleto" if link_boleto else "Abrir Financeiro"
    fatura_email = dict(fatura)
    venc = fatura.get("vencimento_em")
    if isinstance(venc, str) and len(venc) >= 10 and venc[4] == "-":
        y, m, d = venc[:10].split("-")
        fatura_email["vencimento_br"] = f"{d}/{m}/{y}"
    try:
        html = render_template(
            "financeiro/emails/fatura.html",
            titulo_email=assuntos.get(tipo, "Fatura • DropNexo"),
            nome_destinatario=cli["nome_cliente"],
            mensagem_principal=mensagens.get(tipo, ""),
            fatura=fatura_email,
            link_financeiro=f"{base}/financeiro",
            link_acao=link_acao,
            rotulo_acao=rotulo_acao,
            dias_graca=DIAS_GRACA_INADIMPLENCIA,
            **_email_links(),
        )
        ok, _msg, id_envio = enviar_email(
            [email],
            assuntos.get(tipo, "Fatura • DropNexo"),
            html,
            tag=tag,
            criado_por=criado_por,
            dest_meta=[{"email": email, "id_tenant": id_tenant, "nome_tenant": cli.get("nome_tenant") or ""}],
        )
        return bool(ok), int(id_envio) if id_envio else None
    except Exception:
        log.exception("E-mail financeiro falhou tenant=%s tipo=%s", id_tenant, tipo)
        return False, None


def _intervalo_meses(periodo: str) -> int:
    return {"mensal": 1, "semestral": 6, "anual": 12}.get((periodo or "").strip().lower(), 1)


def _plan_id_assinatura(cur, *, plano_slug: str, periodo: str, valor_centavos: int, nome_plano: str) -> str:
    intervalo = _intervalo_meses(periodo)
    cur.execute(
        """
        SELECT efi_plan_id FROM tbl_efi_plano_assinatura
        WHERE plano_slug = %s AND periodicidade = %s AND valor_centavos = %s
        """,
        (plano_slug, periodo, int(valor_centavos)),
    )
    row = cur.fetchone()
    if row and row[0]:
        return str(row[0])
    from api.efi.efi import criar_plano_assinatura

    nome = f"DropNexo {nome_plano} {periodo} {int(valor_centavos)}"
    plan_id = criar_plano_assinatura(nome=nome, intervalo_meses=intervalo)
    cur.execute(
        """
        INSERT INTO tbl_efi_plano_assinatura
            (plano_slug, periodicidade, valor_centavos, intervalo_meses, efi_plan_id)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (plano_slug, periodicidade, valor_centavos) DO UPDATE
            SET efi_plan_id = EXCLUDED.efi_plan_id
        RETURNING efi_plan_id
        """,
        (plano_slug, periodo, int(valor_centavos), intervalo, plan_id),
    )
    return str(cur.fetchone()[0])


def _encerrar_assinatura_efi(cur, id_tenant: int) -> None:
    garantir_colunas_assinatura(cur)
    cur.execute(
        "SELECT efi_subscription_id, assinatura_status FROM tbl_tenant_cobranca WHERE id_tenant = %s",
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row or not row[0] or (row[1] or "") == "cancelada":
        return
    from api.efi.efi import cancelar_assinatura

    try:
        cancelar_assinatura(str(row[0]))
    except Exception:
        log.exception("Falha ao cancelar assinatura Efí tenant=%s", id_tenant)
    cur.execute(
        """
        UPDATE tbl_tenant_cobranca
        SET assinatura_status = 'cancelada', cancelado_em = NOW(), atualizado_em = NOW()
        WHERE id_tenant = %s
        """,
        (id_tenant,),
    )


def _criar_cobranca_efi(
    cur,
    *,
    id_tenant: int,
    forma: str,
    valor_centavos: int,
    descricao: str,
    vencimento: date,
    nome_cliente: str,
    documento: str,
    email: str,
    payment_token: str | None = None,
    installments: int = 1,
    telefone: str | None = None,
    endereco: dict | None = None,
    plano_slug: str | None = None,
    periodo: str = "mensal",
    nome_plano: str = "Plano",
) -> dict:
    from api.efi import efi as efi_mod

    if forma == "pix":
        raise ValueError("Use boleto ou cartão de crédito.")
    if forma == "cartao" and not payment_token:
        raise ValueError("Token do cartão ausente. Preencha os dados do cartão novamente.")
    _encerrar_assinatura_efi(cur, id_tenant)
    plan_id = _plan_id_assinatura(
        cur,
        plano_slug=plano_slug or "plano",
        periodo=periodo,
        valor_centavos=valor_centavos,
        nome_plano=nome_plano,
    )
    venc_boleto = vencimento if vencimento and vencimento > date.today() else date.today() + timedelta(days=10)
    cob = efi_mod.criar_assinatura_one_step(
        plan_id=plan_id,
        nome_cliente=nome_cliente,
        documento=documento,
        email=email,
        valor_centavos=valor_centavos,
        descricao=descricao,
        custom_id=f"tn-{id_tenant}",
        forma=forma,
        vencimento=venc_boleto,
        payment_token=payment_token,
        telefone=telefone,
        endereco=endereco,
    )

    registrar_efi_log(
        cur,
        id_tenant=id_tenant,
        id_fatura=None,
        direcao="out",
        operacao=f"criar_{forma}",
        ok=True,
        efi_charge_id=cob.get("charge_id") or cob.get("txid"),
        request_resumo={"forma": forma, "valor_centavos": valor_centavos, "descricao": descricao},
        response_resumo={k: v for k, v in cob.items() if k != "raw"},
    )
    return cob


def emitir_fatura(
    cur,
    id_tenant: int,
    *,
    plano_slug: str,
    forma: str | None = None,
    referencia: str | None = None,
    payment_token: str | None = None,
    installments: int = 1,
    forcar_nova: bool = False,
    periodicidade: str = "mensal",
    cupom_codigo: str | None = None,
) -> dict:
    """Emite fatura do plano (assinatura ou renovação)."""
    from sistema.financeiro.cupom import (
        ativar_beneficio_cupom_tenant,
        calcular_preco,
        consumir_beneficio_cupom_tenant,
        normalizar_periodo,
        obter_cupom_beneficio_renovacao,
        registrar_uso_cupom,
        validar_cupom_para_periodo,
    )

    garantir_referencia_fatura(cur)

    from sistema.planos.fornecedor_fundador import eh_fundador_ativo

    if eh_fundador_ativo(cur, int(id_tenant)):
        raise ValueError("Fornecedor Fundador não gera cobrança.")

    forma = (forma or "boleto").strip().lower()
    if forma not in FORMAS:
        raise ValueError("Forma de pagamento inválida.")
    periodo = normalizar_periodo(periodicidade)
    plano = obter_plano_db(cur, plano_slug)
    if not plano:
        raise ValueError("Plano não encontrado.")
    if int(plano["valor_centavos"] or 0) <= 0:
        raise ValueError("Plano gratuito não gera cobrança.")

    cupom = None
    cupom_novo = False
    if cupom_codigo and str(cupom_codigo).strip():
        cupom = validar_cupom_para_periodo(
            cur,
            cupom_codigo,
            periodo,
            id_tenant=int(id_tenant),
            plano_slug=plano_slug,
        )
        cupom_novo = True
    else:
        cupom = obter_cupom_beneficio_renovacao(
            cur, int(id_tenant), periodo, plano_slug=plano_slug
        )

    preco = calcular_preco(int(plano["valor_centavos"]), periodo, cupom=cupom)
    valor_final = int(preco["valor_final_centavos"])

    cli = _dados_cliente_cobranca(cur, id_tenant)
    ref = referencia or referencia_assinatura(periodo)
    if not forcar_nova:
        cur.execute(
            """
            SELECT id, status FROM tbl_fatura
            WHERE id_tenant = %s AND referencia = %s AND plano_slug = %s
              AND status IN ('pendente', 'pago')
            ORDER BY id DESC LIMIT 1
            """,
            (id_tenant, ref, plano_slug),
        )
        ex = cur.fetchone()
        if ex:
            if ex[1] == "pago":
                raise ValueError("Já existe fatura paga para este período/plano.")
            fat = obter_fatura(cur, id_tenant, int(ex[0]))
            if fat:
                return fat

    email = cli["email_cobranca"] or ""
    venc = proximo_vencimento(cli["dia_vencimento"])
    desc_periodo = preco["periodo_rotulo"]
    descricao = f"DropNexo — {plano['nome']} · {desc_periodo} ({ref})"

    cob: dict = {
        "charge_id": None,
        "txid": None,
        "link_boleto": None,
        "codigo_barras": None,
        "pix_copia_cola": None,
        "pix_qrcode": None,
        "link_pagamento": None,
        "pago": False,
    }
    cortesia = valor_final <= 0

    if not cortesia:
        from api.efi.efi import efi_disponivel

        if not efi_disponivel():
            raise RuntimeError("Efi não configurada no servidor (.env).")
        cob = _criar_cobranca_efi(
            cur,
            id_tenant=id_tenant,
            forma=forma,
            valor_centavos=valor_final,
            descricao=descricao,
            vencimento=venc,
            nome_cliente=cli["nome_cliente"],
            documento=cli["documento"],
            email=email,
            payment_token=payment_token,
            installments=installments,
            telefone=cli.get("telefone"),
            endereco=cli.get("endereco"),
            plano_slug=plano_slug,
            periodo=periodo,
            nome_plano=plano["nome"],
        )

    status_ini = "pago" if cortesia or (forma == "cartao" and cob.get("pago")) else "pendente"
    cur.execute(
        """
        INSERT INTO tbl_fatura (
            id_tenant, referencia, valor_centavos, status, forma_pagamento, plano_slug,
            efi_charge_id, efi_txid, link_boleto, codigo_barras, pix_copia_cola, pix_qrcode,
            link_pagamento, vencimento_em, pago_em, atualizado_em,
            periodicidade, meses_cobertos, id_cupom, cupom_codigo,
            valor_cheio_centavos, desconto_periodo_centavos, desconto_cupom_centavos
        ) VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
            CASE WHEN %s = 'pago' THEN NOW() ELSE NULL END, NOW(),
            %s,%s,%s,%s,%s,%s,%s
        ) RETURNING id
        """,
        (
            id_tenant,
            ref,
            valor_final,
            status_ini,
            forma if not cortesia else (forma or "boleto"),
            plano_slug,
            cob.get("charge_id"),
            cob.get("txid"),
            cob.get("link_boleto"),
            cob.get("codigo_barras"),
            cob.get("pix_copia_cola"),
            cob.get("pix_qrcode"),
            cob.get("link_pagamento"),
            venc,
            status_ini,
            periodo,
            int(preco["meses_cobertos"]),
            cupom["id"] if cupom else None,
            cupom["codigo"] if cupom else None,
            int(preco["valor_cheio_centavos"]),
            int(preco["desconto_periodo_centavos"]),
            int(preco["desconto_cupom_centavos"]),
        ),
    )
    fid = int(cur.fetchone()[0])
    registrar_efi_log(
        cur,
        id_tenant=id_tenant,
        id_fatura=fid,
        direcao="out",
        operacao="fatura_inserida",
        ok=True,
        efi_charge_id=cob.get("charge_id") or cob.get("txid"),
        response_resumo={"id_fatura": fid, "status": status_ini, "preco": preco},
    )

    if cupom and int(preco["desconto_cupom_centavos"] or 0) >= 0:
        if cupom_novo:
            registrar_uso_cupom(
                cur,
                id_cupom=int(cupom["id"]),
                id_tenant=id_tenant,
                id_fatura=fid,
                codigo=cupom["codigo"],
                desconto_centavos=int(preco["desconto_cupom_centavos"]),
            )
            ativar_beneficio_cupom_tenant(cur, int(id_tenant), cupom)
        else:
            # Renovação: não consome usos_max do cupom; só decrementa ciclos restantes
            consumir_beneficio_cupom_tenant(cur, int(id_tenant))

    cur.execute(
        """
        UPDATE tbl_tenant_cobranca
        SET periodicidade = %s, atualizado_em = NOW()
        WHERE id_tenant = %s
        """,
        (periodo, id_tenant),
    )
    if cob.get("subscription_id"):
        cur.execute(
            """
            UPDATE tbl_tenant_cobranca
            SET efi_subscription_id = %s, efi_plan_id = %s,
                assinatura_status = 'ativa', cancelado_em = NULL, atualizado_em = NOW()
            WHERE id_tenant = %s
            """,
            (str(cob["subscription_id"]), str(cob.get("plan_id") or ""), id_tenant),
        )

    if status_ini == "pago":
        aplicar_pagamento_fatura(cur, fid, origem="cartao_imediato" if not cortesia else "cortesia")
    else:
        cur.execute(
            """
            UPDATE tbl_tenant_cobranca
            SET forma_pagamento = %s, plano_slug_pendente = %s, atualizado_em = NOW()
            WHERE id_tenant = %s
            """,
            (forma, plano_slug, id_tenant),
        )

    fat = obter_fatura(cur, id_tenant, fid)
    if fat and status_ini != "pago":
        _enviar_email_fatura(cur, id_tenant, fat, tipo="emitida")
    return fat or {}


def assinar_plano(
    cur,
    id_tenant: int,
    plano_slug: str,
    *,
    forma: str = "boleto",
    payment_token: str | None = None,
    installments: int = 1,
    periodicidade: str = "mensal",
    cupom_codigo: str | None = None,
) -> dict:
    from sistema.financeiro.cupom import normalizar_periodo

    slug = (plano_slug or "").strip().lower()
    if slug not in PLANOS_PAGOS:
        raise ValueError("Selecione um plano pago válido.")
    forma = (forma or "boleto").strip().lower()
    if forma == "pix":
        raise ValueError("PIX será liberado em breve. Use boleto ou cartão.")
    periodo = normalizar_periodo(periodicidade)
    cli = _dados_cliente_cobranca(cur, id_tenant)
    doc = "".join(c for c in (cli["documento"] or "") if c.isdigit())
    if len(doc) not in (11, 14):
        raise ValueError("Cadastre CPF/CNPJ da empresa em Meu perfil antes de assinar.")
    if not (cli["email_cobranca"] or "").strip() or "@" not in (cli["email_cobranca"] or ""):
        raise ValueError(
            "Não encontramos e-mail para cobrança. Cadastre o e-mail do usuário dono "
            "ou informe em Meu perfil → Forma de pagamento."
        )
    if forma == "cartao":
        end = cli.get("endereco") or {}
        cep = "".join(c for c in (end.get("cep") or "") if c.isdigit())
        uf = (end.get("uf") or "").strip()
        if (
            len(cep) != 8
            or not (end.get("logradouro") or "").strip()
            or not (end.get("bairro") or "").strip()
            or not (end.get("cidade") or "").strip()
            or len(uf) != 2
        ):
            raise ValueError(
                "Para pagar com cartão, complete o endereço da empresa em Meu perfil → Empresa "
                "(CEP, rua, bairro, cidade e UF)."
            )

    fatura = emitir_fatura(
        cur,
        id_tenant,
        plano_slug=slug,
        forma=forma,
        payment_token=payment_token,
        installments=installments,
        forcar_nova=False,
        periodicidade=periodo,
        cupom_codigo=cupom_codigo,
    )
    pago = fatura.get("status") == "pago"
    liberado = pago
    if pago and forma == "cartao":
        msg = "Pagamento confirmado. No cartão de crédito a liberação do plano é imediata."
    elif pago:
        msg = "Pagamento confirmado. Plano liberado."
    elif forma == "boleto":
        msg = (
            "Boleto gerado. O plano só é liberado quando o pagamento for confirmado. "
            "A confirmação pode levar até 3 dias, conforme o banco."
        )
    else:
        msg = "Fatura emitida. O plano será liberado após a confirmação do pagamento."
    return {
        "fatura": fatura,
        "message": msg,
        "liberado": liberado,
    }


def _charge_id_numerico(valor) -> str | None:
    s = str(valor or "").strip()
    return s if s.isdigit() else None


def _texto_efi(exc: BaseException) -> str:
    return str(exc or "")[:400]


def _efi_ja_cancelada(msg: str) -> bool:
    t = (msg or "").lower()
    return any(
        m in t
        for m in (
            "já cancel",
            "ja cancel",
            "already cancel",
            "already been cancel",
            "cobrança cancelada",
            "cobranca cancelada",
        )
    )


def _efi_ja_paga(msg: str) -> bool:
    t = (msg or "").lower()
    return any(m in t for m in ("pix pago", "paid", "paga", "settled", "approved", "aprovad"))


def _cancelar_charge_efi(cur, id_tenant: int, id_fatura: int, charge: str) -> str:
    from api.efi.efi import cancelar_cobranca, consultar_cobranca

    try:
        det = consultar_cobranca(charge)
    except Exception as e:
        registrar_efi_log(
            cur,
            id_tenant=id_tenant,
            id_fatura=id_fatura,
            direcao="out",
            operacao="consultar_charge",
            ok=False,
            efi_charge_id=charge,
            response_resumo=_texto_efi(e),
        )
        raise ValueError("Não consultei a cobrança na Efí. A fatura continua na lista.") from e

    st_efi = (det.get("status") or "").strip().lower()
    if st_efi == "pago":
        registrar_efi_log(
            cur,
            id_tenant=id_tenant,
            id_fatura=id_fatura,
            direcao="out",
            operacao="cancelar_charge",
            ok=False,
            efi_charge_id=charge,
            response_resumo="efi status pago",
        )
        raise ValueError("A Efí informa essa cobrança como paga. Ela continua na lista.")
    if st_efi == "cancelado":
        registrar_efi_log(
            cur,
            id_tenant=id_tenant,
            id_fatura=id_fatura,
            direcao="out",
            operacao="cancelar_charge",
            ok=True,
            efi_charge_id=charge,
            response_resumo="já cancelada na Efí",
        )
        return "A cobrança já estava cancelada na Efí."

    try:
        resp = cancelar_cobranca(charge)
    except Exception as e:
        msg = _texto_efi(e)
        if _efi_ja_cancelada(msg):
            registrar_efi_log(
                cur,
                id_tenant=id_tenant,
                id_fatura=id_fatura,
                direcao="out",
                operacao="cancelar_charge",
                ok=True,
                efi_charge_id=charge,
                response_resumo=msg,
            )
            return "A cobrança já estava cancelada na Efí."
        if _efi_ja_paga(msg):
            registrar_efi_log(
                cur,
                id_tenant=id_tenant,
                id_fatura=id_fatura,
                direcao="out",
                operacao="cancelar_charge",
                ok=False,
                efi_charge_id=charge,
                response_resumo=msg,
            )
            raise ValueError("A Efí informa essa cobrança como paga. Ela continua na lista.") from e
        expirada = st_efi == "vencido" and any(
            x in msg.lower()
            for x in ("expir", "não pode ser cancel", "nao pode ser cancel", "cannot be cancel")
        )
        if expirada:
            registrar_efi_log(
                cur,
                id_tenant=id_tenant,
                id_fatura=id_fatura,
                direcao="out",
                operacao="cancelar_charge",
                ok=True,
                efi_charge_id=charge,
                response_resumo=msg,
            )
            return "O boleto já estava expirado na Efí e não aceita mais pagamento."
        registrar_efi_log(
            cur,
            id_tenant=id_tenant,
            id_fatura=id_fatura,
            direcao="out",
            operacao="cancelar_charge",
            ok=False,
            efi_charge_id=charge,
            response_resumo=msg,
        )
        raise ValueError("A Efí não cancelou a cobrança. A fatura continua na lista.") from e

    registrar_efi_log(
        cur,
        id_tenant=id_tenant,
        id_fatura=id_fatura,
        direcao="out",
        operacao="cancelar_charge",
        ok=True,
        efi_charge_id=charge,
        response_resumo=_json_resumo(resp),
    )
    return "A cobrança foi cancelada na Efí."


def _cancelar_pix_efi(cur, id_tenant: int, id_fatura: int, txid: str) -> str:
    from api.efi.efi import cancelar_cobranca_pix

    try:
        resp = cancelar_cobranca_pix(txid)
    except Exception as e:
        msg = _texto_efi(e)
        if _efi_ja_cancelada(msg) or "removida" in msg.lower():
            registrar_efi_log(
                cur,
                id_tenant=id_tenant,
                id_fatura=id_fatura,
                direcao="out",
                operacao="cancelar_pix",
                ok=True,
                response_resumo=msg,
            )
            return "O PIX já estava encerrado na Efí."
        if _efi_ja_paga(msg):
            registrar_efi_log(
                cur,
                id_tenant=id_tenant,
                id_fatura=id_fatura,
                direcao="out",
                operacao="cancelar_pix",
                ok=False,
                response_resumo=msg,
            )
            raise ValueError("A Efí informa esse PIX como pago. A fatura continua na lista.") from e
        registrar_efi_log(
            cur,
            id_tenant=id_tenant,
            id_fatura=id_fatura,
            direcao="out",
            operacao="cancelar_pix",
            ok=False,
            response_resumo=msg,
        )
        raise ValueError("A Efí não cancelou o PIX. A fatura continua na lista.") from e

    registrar_efi_log(
        cur,
        id_tenant=id_tenant,
        id_fatura=id_fatura,
        direcao="out",
        operacao="cancelar_pix",
        ok=True,
        response_resumo=_json_resumo(resp),
    )
    return "O PIX foi cancelado na Efí."


def cancelar_fatura_admin(cur, id_fatura: int, *, id_tenant: int | None = None) -> dict:
    """Cancela a fatura local e a cobrança na Efí. Não altera o plano do tenant."""
    if id_fatura <= 0:
        raise ValueError("Fatura inválida.")
    sql = f"SELECT {_FATURA_COLS}, id_tenant FROM tbl_fatura WHERE id = %s"
    params: list[Any] = [id_fatura]
    if id_tenant:
        sql += " AND id_tenant = %s"
        params.append(int(id_tenant))
    cur.execute(sql, tuple(params))
    row = cur.fetchone()
    if not row:
        raise ValueError("Fatura não encontrada.")
    fat = fatura_dict(row)
    tid = int(row[-1])
    st = (fat.get("status") or "").strip().lower()
    if st == "pago":
        raise ValueError("Fatura já está paga. Cobrança paga não é cancelada.")
    if st not in ("pendente", "vencido", "cancelado"):
        raise ValueError("Essa fatura não está em aberto.")

    charge = _charge_id_numerico(fat.get("efi_charge_id"))
    txid = str(fat.get("efi_txid") or "").strip()
    bruto = str(fat.get("efi_charge_id") or "").strip()
    if not charge and bruto:
        txid = txid or bruto

    if charge:
        efi_detalhe = _cancelar_charge_efi(cur, tid, id_fatura, charge)
    elif txid:
        efi_detalhe = _cancelar_pix_efi(cur, tid, id_fatura, txid)
    else:
        efi_detalhe = "Não havia cobrança na Efí."

    if st != "cancelado":
        cur.execute(
            """
            UPDATE tbl_fatura
            SET status = 'cancelado', atualizado_em = NOW()
            WHERE id = %s AND id_tenant = %s AND status IN ('pendente', 'vencido')
            """,
            (id_fatura, tid),
        )
        if cur.rowcount != 1:
            raise ValueError("A fatura mudou de status antes do cancelamento. Atualize a lista.")

    ref = fat.get("referencia") or str(id_fatura)
    return {
        "id_fatura": id_fatura,
        "id_tenant": tid,
        "message": f"Cobrança {ref} cancelada. {efi_detalhe} O plano do tenant não foi alterado.",
    }


def garantir_tabela_lembrete(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_fatura_lembrete (
            id BIGSERIAL PRIMARY KEY,
            id_fatura INTEGER NOT NULL,
            id_tenant INTEGER NOT NULL,
            id_envio INTEGER,
            email_destino VARCHAR(255) NOT NULL,
            enviado_em TIMESTAMP NOT NULL DEFAULT NOW(),
            id_usuario INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fatura_lembrete_fatura
            ON tbl_fatura_lembrete (id_fatura, enviado_em DESC)
        """
    )


def _fmt_quando_br(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    return "—"


def rotulo_evento_email(status: str | None) -> str:
    s = (status or "").strip().lower().replace(" ", "")
    if s in ("opened", "unique_opened", "uniqueopened", "first_opening", "proxy_open"):
        return "Aberto"
    if s in ("click", "clicks", "clicked"):
        return "Clicou no link"
    if s == "delivered":
        return "Entregue"
    if s in ("request", "enviado", "sent", "requests"):
        return "Enviado"
    if "bounce" in s or s in ("blocked", "invalid", "error", "spam", "falha", "deferred"):
        return "Não entregue"
    if s in ("unsubscribed", "unsubscribe"):
        return "Descadastrado"
    if not s:
        return "Enviado"
    return "Enviado"


def _rotulo_resumo_lembrete(qtd: int, quando, status: str | None) -> str:
    if qtd <= 0:
        return ""
    st = rotulo_evento_email(status)
    dia = _fmt_quando_br(quando)
    if qtd == 1:
        return f"Lembrete {dia} · {st}"
    return f"{qtd} lembretes · último {st.lower()} em {dia}"


def resumo_lembretes(cur, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    cur.execute(
        """
        SELECT l.id_fatura, l.enviado_em, d.status_atual
        FROM tbl_fatura_lembrete l
        LEFT JOIN tbl_email_destinatario d
          ON d.id_envio = l.id_envio
         AND lower(d.email) = lower(l.email_destino)
        WHERE l.id_fatura = ANY(%s)
        ORDER BY l.enviado_em DESC, l.id DESC
        """,
        (ids,),
    )
    acc: dict[int, dict] = {}
    for fid, quando, status in cur.fetchall():
        item = acc.setdefault(int(fid), {"qtd": 0, "quando": None, "status": None})
        item["qtd"] += 1
        if item["quando"] is None:
            item["quando"] = quando
            item["status"] = status
    out: dict[int, dict] = {}
    for fid, item in acc.items():
        out[fid] = {
            "qtd": item["qtd"],
            "rotulo": _rotulo_resumo_lembrete(item["qtd"], item["quando"], item["status"]),
            "status": rotulo_evento_email(item["status"]) if item["qtd"] else "",
        }
    return out


def _lembretes_da_fatura(cur, id_fatura: int, id_tenant: int) -> list[dict]:
    cur.execute(
        """
        SELECT l.id, l.enviado_em, l.email_destino, d.id_destinatario, d.status_atual, d.dt_ultimo_evento
        FROM tbl_fatura_lembrete l
        LEFT JOIN tbl_email_destinatario d
          ON d.id_envio = l.id_envio
         AND lower(d.email) = lower(l.email_destino)
        WHERE l.id_fatura = %s AND l.id_tenant = %s
        ORDER BY l.enviado_em DESC, l.id DESC
        """,
        (id_fatura, id_tenant),
    )
    linhas = cur.fetchall()
    dest_ids = [int(r[3]) for r in linhas if r[3]]
    eventos: dict[int, list[dict]] = {}
    if dest_ids:
        cur.execute(
            """
            SELECT id_destinatario, tipo_evento, data_evento
            FROM tbl_email_evento
            WHERE id_destinatario = ANY(%s)
            ORDER BY data_evento ASC, id_evento ASC
            """,
            (dest_ids,),
        )
        for id_dest, tipo, quando in cur.fetchall():
            eventos.setdefault(int(id_dest), []).append(
                {
                    "tipo": rotulo_evento_email(tipo),
                    "quando": _fmt_quando_br(quando),
                }
            )
    saida = []
    for row in linhas:
        id_dest = int(row[3]) if row[3] else None
        saida.append(
            {
                "enviado_em": _fmt_quando_br(row[1]),
                "email": row[2] or "",
                "status": rotulo_evento_email(row[4]),
                "atualizado_em": _fmt_quando_br(row[5]) if row[5] else "",
                "eventos": eventos.get(id_dest or 0, []),
            }
        )
    return saida


def detalhe_cobranca_admin(cur, id_fatura: int, *, id_tenant: int | None = None) -> dict:
    if id_fatura <= 0:
        raise ValueError("Fatura inválida.")
    cols = ", ".join(f"f.{c.strip()}" for c in _FATURA_COLS.split(","))
    sql = f"""
        SELECT {cols}, f.id_tenant, t.nome, t.plano, t.tipo_negocio
        FROM tbl_fatura f
        JOIN tbl_tenant t ON t.id = f.id_tenant
        WHERE f.id = %s
    """
    params: list[Any] = [id_fatura]
    if id_tenant:
        sql += " AND f.id_tenant = %s"
        params.append(int(id_tenant))
    cur.execute(sql, tuple(params))
    row = cur.fetchone()
    if not row:
        raise ValueError("Fatura não encontrada.")
    fat = fatura_dict(row)
    tid = int(row[23])
    from sistema.financeiro.assinaturas_painel import FORMA_LABEL, nome_plano_comercial
    from sistema.financeiro.cupom import PERIODOS

    periodo = (fat.get("periodicidade") or "mensal").strip().lower()
    st = (fat.get("status") or "").strip().lower()
    forma = (fat.get("forma_pagamento") or "").strip().lower()
    charge = _charge_id_numerico(fat.get("efi_charge_id"))
    txid = str(fat.get("efi_txid") or "").strip()
    lembretes: list[dict] = []
    try:
        cur.execute("SAVEPOINT sp_det_lemb")
        lembretes = _lembretes_da_fatura(cur, id_fatura, tid)
        cur.execute("RELEASE SAVEPOINT sp_det_lemb")
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT sp_det_lemb")
        except Exception:
            pass
        lembretes = []
    venc = fat.get("vencimento_em")
    venc_br = "—"
    if isinstance(venc, str) and len(venc) >= 10 and venc[4] == "-":
        y, m, d = venc[:10].split("-")
        venc_br = f"{d}/{m}/{y}"
    criado = fat.get("criado_em")
    criado_br = criado[:16].replace("T", " ") if isinstance(criado, str) else "—"
    pago = fat.get("pago_em")
    pago_br = pago[:16].replace("T", " ") if isinstance(pago, str) else ""
    return {
        "id_fatura": id_fatura,
        "id_tenant": tid,
        "nome": (row[24] or "").strip() or f"Tenant #{tid}",
        "plano_label": nome_plano_comercial(row[25], row[26]),
        "referencia": fat.get("referencia") or "",
        "status": st,
        "status_label": STATUS_LABEL.get(st, st or "—"),
        "valor": fat.get("valor_formatado") or "",
        "valor_cheio": (
            f"R$ {(int(fat['valor_cheio_centavos']) / 100):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            if fat.get("valor_cheio_centavos")
            else ""
        ),
        "desconto_periodo": (
            f"R$ {(int(fat.get('desconto_periodo_centavos') or 0) / 100):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            if int(fat.get("desconto_periodo_centavos") or 0) else ""
        ),
        "desconto_cupom": (
            f"R$ {(int(fat.get('desconto_cupom_centavos') or 0) / 100):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            if int(fat.get("desconto_cupom_centavos") or 0) else ""
        ),
        "cupom_codigo": fat.get("cupom_codigo") or "",
        "vencimento": venc_br,
        "criado_em": criado_br,
        "pago_em": pago_br,
        "forma_label": FORMA_LABEL.get(forma, forma or "—"),
        "periodicidade": PERIODOS.get(periodo, {}).get("rotulo", periodo),
        "efi": "Sim" if charge or txid else "Não",
        "link_boleto": fat.get("link_boleto") or "",
        "codigo_barras": fat.get("codigo_barras") or "",
        "pix_copia_cola": fat.get("pix_copia_cola") or "",
        "link_pagamento": fat.get("link_pagamento") or "",
        "lembretes": lembretes,
    }


def enviar_lembrete_fatura(
    cur,
    id_fatura: int,
    *,
    id_tenant: int | None = None,
    id_usuario: int | None = None,
) -> dict:
    if id_fatura <= 0:
        raise ValueError("Fatura inválida.")
    sql = f"SELECT {_FATURA_COLS}, id_tenant FROM tbl_fatura WHERE id = %s"
    params: list[Any] = [id_fatura]
    if id_tenant:
        sql += " AND id_tenant = %s"
        params.append(int(id_tenant))
    cur.execute(sql, tuple(params))
    row = cur.fetchone()
    if not row:
        raise ValueError("Fatura não encontrada.")
    fat = fatura_dict(row)
    tid = int(row[-1])
    st = (fat.get("status") or "").strip().lower()
    if st == "pago":
        raise ValueError("Fatura já está paga. Lembrete não enviado.")
    if st == "cancelado":
        raise ValueError("Fatura cancelada. Lembrete não enviado.")
    if st not in ("pendente", "vencido"):
        raise ValueError("Essa fatura não está em aberto.")

    ok, id_envio = _enviar_email_fatura(cur, tid, fat, tipo="lembrete", criado_por=id_usuario)
    if not ok:
        raise ValueError("O lembrete não foi enviado. Confira o e-mail de cobrança da conta.")

    try:
        garantir_tabela_lembrete(cur)
    except Exception as e:
        raise ValueError(
            "O e-mail saiu, mas o registro do lembrete falhou. "
            "Crie a tabela tbl_fatura_lembrete no banco."
        ) from e

    email_row = None
    if id_envio:
        cur.execute(
            """
            SELECT email FROM tbl_email_destinatario
            WHERE id_envio = %s
            ORDER BY id_destinatario DESC
            LIMIT 1
            """,
            (id_envio,),
        )
        email_row = cur.fetchone()
    email_dest = (email_row[0] if email_row else "") or ""
    if not email_dest:
        cli = _dados_cliente_cobranca(cur, tid)
        email_dest = (cli.get("email_cobranca") or "").strip().lower()
    if "@" not in email_dest:
        raise ValueError("O lembrete não foi registrado: a conta não tem e-mail de cobrança.")

    cur.execute(
        """
        INSERT INTO tbl_fatura_lembrete (id_fatura, id_tenant, id_envio, email_destino, id_usuario)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (id_fatura, tid, id_envio, email_dest[:255], id_usuario),
    )
    ref = fat.get("referencia") or str(id_fatura)
    return {
        "id_fatura": id_fatura,
        "id_tenant": tid,
        "message": (
            f"Lembrete da fatura {ref} enviado. "
            "A abertura aparece no detalhe quando o Brevo registrar."
        ),
    }


def regenerar_cobranca(
    cur,
    id_tenant: int,
    id_fatura: int,
    *,
    forma: str | None = None,
    payment_token: str | None = None,
    installments: int = 1,
) -> dict:
    fat = obter_fatura(cur, id_tenant, id_fatura)
    if not fat:
        raise ValueError("Fatura não encontrada.")
    if fat["status"] == "pago":
        raise ValueError("Fatura já está paga.")
    if fat["status"] == "cancelado":
        raise ValueError("Fatura cancelada. Assine novamente pelo Meu plano.")

    forma_n = (forma or fat.get("forma_pagamento") or "boleto").strip().lower()
    if forma_n == "pix":
        raise ValueError("PIX será liberado em breve. Use boleto ou cartão.")
    plano_slug = fat.get("plano_slug") or _dados_cliente_cobranca(cur, id_tenant).get("plano_slug_pendente")
    if not plano_slug:
        raise ValueError("Plano da fatura não identificado.")

    # cancela cobrança anterior na Efi (best-effort)
    if fat.get("efi_charge_id"):
        try:
            from api.efi.efi import cancelar_cobranca

            cancelar_cobranca(str(fat["efi_charge_id"]))
            registrar_efi_log(
                cur,
                id_tenant=id_tenant,
                id_fatura=id_fatura,
                direcao="out",
                operacao="cancelar_charge",
                ok=True,
                efi_charge_id=str(fat["efi_charge_id"]),
            )
        except Exception as e:
            registrar_efi_log(
                cur,
                id_tenant=id_tenant,
                id_fatura=id_fatura,
                direcao="out",
                operacao="cancelar_charge",
                ok=False,
                efi_charge_id=str(fat["efi_charge_id"]),
                response_resumo=str(e),
            )

    cli = _dados_cliente_cobranca(cur, id_tenant)
    if forma_n == "cartao":
        if not payment_token:
            raise ValueError("Token do cartão ausente. Preencha os dados do cartão novamente.")
        end = cli.get("endereco") or {}
        cep = "".join(c for c in (end.get("cep") or "") if c.isdigit())
        uf = (end.get("uf") or "").strip()
        if (
            len(cep) != 8
            or not (end.get("logradouro") or "").strip()
            or not (end.get("bairro") or "").strip()
            or not (end.get("cidade") or "").strip()
            or len(uf) != 2
        ):
            raise ValueError(
                "Para pagar com cartão, complete o endereço da empresa em Meu perfil → Empresa "
                "(CEP, rua, bairro, cidade e UF)."
            )
    plano = obter_plano_db(cur, plano_slug)
    if not plano:
        raise ValueError("Plano não encontrado.")
    venc = date.fromisoformat(fat["vencimento_em"]) if fat.get("vencimento_em") else proximo_vencimento(cli["dia_vencimento"])
    if venc < date.today():
        venc = proximo_vencimento(cli["dia_vencimento"])

    cob = _criar_cobranca_efi(
        cur,
        id_tenant=id_tenant,
        forma=forma_n,
        valor_centavos=int(fat["valor_centavos"]),
        descricao=f"DropNexo — {plano['nome']} ({fat['referencia']}) — 2ª via",
        vencimento=venc,
        nome_cliente=cli["nome_cliente"],
        documento=cli["documento"],
        email=cli["email_cobranca"],
        payment_token=payment_token,
        installments=installments,
        telefone=cli.get("telefone"),
        endereco=cli.get("endereco"),
        plano_slug=plano_slug,
        periodo=(fat.get("periodicidade") or "mensal"),
        nome_plano=plano["nome"],
    )
    status_ini = "pago" if forma_n == "cartao" and cob.get("pago") else "pendente"
    cur.execute(
        """
        UPDATE tbl_fatura SET
            status = %s,
            forma_pagamento = %s,
            efi_charge_id = %s,
            efi_txid = %s,
            link_boleto = %s,
            codigo_barras = %s,
            pix_copia_cola = %s,
            pix_qrcode = %s,
            link_pagamento = %s,
            vencimento_em = %s,
            pago_em = CASE WHEN %s = 'pago' THEN NOW() ELSE NULL END,
            atualizado_em = NOW()
        WHERE id = %s AND id_tenant = %s
        """,
        (
            status_ini,
            forma_n,
            cob.get("charge_id"),
            cob.get("txid"),
            cob.get("link_boleto"),
            cob.get("codigo_barras"),
            cob.get("pix_copia_cola"),
            cob.get("pix_qrcode"),
            cob.get("link_pagamento"),
            venc,
            status_ini,
            id_fatura,
            id_tenant,
        ),
    )
    if cob.get("subscription_id"):
        cur.execute(
            """
            UPDATE tbl_tenant_cobranca
            SET efi_subscription_id = %s, efi_plan_id = %s,
                assinatura_status = 'ativa', cancelado_em = NULL, atualizado_em = NOW()
            WHERE id_tenant = %s
            """,
            (str(cob["subscription_id"]), str(cob.get("plan_id") or ""), id_tenant),
        )
    if status_ini == "pago":
        aplicar_pagamento_fatura(cur, id_fatura, origem="cartao_imediato")
    fat2 = obter_fatura(cur, id_tenant, id_fatura)
    if fat2 and status_ini != "pago":
        _enviar_email_fatura(cur, id_tenant, fat2, tipo="emitida")
    return fat2 or {}


def _parse_dt_efi(raw_dt) -> datetime | None:
    if not raw_dt:
        return None
    s = str(raw_dt).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:26], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(raw_dt).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _parse_pago_em_efi(det: dict | None) -> datetime | None:
    """Extrai paid_at da resposta detail_charge (boleto/cartão)."""
    if not isinstance(det, dict):
        return None
    raw = det.get("raw") if isinstance(det.get("raw"), dict) else det
    if not isinstance(raw, dict):
        return None
    payment = raw.get("payment") if isinstance(raw.get("payment"), dict) else {}
    candidatos = [
        raw.get("paid_at"),
        payment.get("paid_at"),
    ]
    for bloco in (payment.get("banking_billet"), payment.get("credit_card"), payment.get("pix")):
        if isinstance(bloco, dict):
            candidatos.append(bloco.get("paid_at"))
    for raw_dt in candidatos:
        dt = _parse_dt_efi(raw_dt)
        if dt:
            return dt
    # Fallback: histórico "Cobrança paga" / "Pagamento"
    hist = raw.get("history") if isinstance(raw.get("history"), list) else []
    for h in reversed(hist):
        if not isinstance(h, dict):
            continue
        msg = str(h.get("message") or "").lower()
        if any(x in msg for x in ("paga", "pago", "pagamento", "paid", "liquid")):
            dt = _parse_dt_efi(h.get("created_at") or h.get("date") or h.get("time"))
            if dt:
                return dt
    return None


def aplicar_pagamento_fatura(
    cur,
    id_fatura: int,
    *,
    origem: str = "webhook",
    pago_em: datetime | date | None = None,
) -> dict:
    cur.execute(
        """
        SELECT id, referencia, valor_centavos, status, forma_pagamento, plano_slug,
               link_boleto, codigo_barras, pix_copia_cola, pix_qrcode, link_pagamento,
               vencimento_em, pago_em, criado_em, efi_charge_id, efi_txid, id_tenant
        FROM tbl_fatura WHERE id = %s
        """,
        (id_fatura,),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "message": "Fatura não encontrada."}
    id_tenant = int(row[16])
    fat = fatura_dict(row[:16])
    plano_slug = fat.get("plano_slug") or "professional"

    pago_dt = pago_em
    if isinstance(pago_dt, date) and not isinstance(pago_dt, datetime):
        pago_dt = datetime(pago_dt.year, pago_dt.month, pago_dt.day)

    cur.execute(
        """
        UPDATE tbl_fatura
        SET status = 'pago',
            pago_em = COALESCE(%s, pago_em, NOW()),
            atualizado_em = NOW()
        WHERE id = %s
        """,
        (pago_dt, id_fatura),
    )
    cur.execute(
        """
        UPDATE tbl_tenant SET plano = %s WHERE id = %s
        """,
        (plano_slug, id_tenant),
    )
    cur.execute(
        """
        UPDATE tbl_tenant_cobranca
        SET plano_slug = %s, plano_slug_pendente = NULL, atualizado_em = NOW()
        WHERE id_tenant = %s
        """,
        (plano_slug, id_tenant),
    )
    registrar_efi_log(
        cur,
        id_tenant=id_tenant,
        id_fatura=id_fatura,
        direcao="in",
        operacao=f"pagamento_{origem}",
        ok=True,
        efi_charge_id=fat.get("efi_charge_id"),
        response_resumo={"plano": plano_slug},
    )
    fat2 = obter_fatura(cur, id_tenant, id_fatura)
    if fat2:
        _enviar_email_fatura(cur, id_tenant, fat2, tipo="pago")
    cur.execute("SAVEPOINT comissao_fatura")
    try:
        from sistema.financeiro.comissao import registrar_comissao_fatura

        registrar_comissao_fatura(cur, id_fatura)
        cur.execute("RELEASE SAVEPOINT comissao_fatura")
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT comissao_fatura")
        log.exception("Comissão da fatura %s não gerada", id_fatura)
    return {"ok": True, "id_tenant": id_tenant, "plano": plano_slug, "fatura": fat2}


def _mapa_status_efi_local(status: str) -> str:
    s = (status or "").lower()
    return {
        "paid": "pago",
        "settled": "pago",
        "approved": "pago",
        "waiting": "pendente",
        "unpaid": "pendente",
        "pending": "pendente",
        "expired": "vencido",
        "canceled": "cancelado",
        "cancelled": "cancelado",
        "concluida": "pago",
        "ativa": "pendente",
    }.get(s, "pendente")


def _fatura_do_custom(cur, payload: dict):
    """Cobrança avulsa desta fatura usa custom_id fat-{id}."""
    custom = str(payload.get("custom_id") or "").strip()
    if not custom.startswith("fat-") or not custom[4:].isdigit():
        return None
    cur.execute(
        """
        SELECT id, id_tenant, status, efi_charge_id
        FROM tbl_fatura WHERE id = %s
        """,
        (int(custom[4:]),),
    )
    return cur.fetchone()


def _tenant_do_aviso(cur, payload: dict) -> int | None:
    custom = str(payload.get("custom_id") or "").strip()
    if custom.startswith("tn-") and custom[3:].isdigit():
        return int(custom[3:])
    sub = str(payload.get("subscription_id") or "").strip()
    if not sub:
        return None
    garantir_colunas_assinatura(cur)
    cur.execute(
        "SELECT id_tenant FROM tbl_tenant_cobranca WHERE efi_subscription_id = %s",
        (sub,),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _abrir_fatura_de_aviso(cur, id_tenant: int, charge_id: str) -> int | None:
    """Grava a cobrança que a Efí emitiu sozinha no ciclo seguinte."""
    cur.execute(
        """
        SELECT COALESCE(NULLIF(plano_slug, ''), 'professional'),
               COALESCE(NULLIF(forma_pagamento, ''), 'boleto'),
               COALESCE(NULLIF(periodicidade, ''), 'mensal')
        FROM tbl_tenant_cobranca
        WHERE id_tenant = %s
        """,
        (id_tenant,),
    )
    tc = cur.fetchone()
    if not tc:
        return None
    plano_slug, forma, periodo = tc[0], tc[1], tc[2]
    plano = obter_plano_db(cur, plano_slug) or {}
    valor = int(plano.get("valor_centavos") or 0)
    venc = date.today() if (forma or "").lower() == "cartao" else date.today() + timedelta(days=10)
    link = None
    try:
        from api.efi.efi import consultar_cobranca

        det = consultar_cobranca(charge_id)
        raw = det.get("raw") or {}
        payment = raw.get("payment") if isinstance(raw.get("payment"), dict) else {}
        billet = payment.get("banking_billet") if isinstance(payment.get("banking_billet"), dict) else {}
        exp = billet.get("expire_at") or raw.get("expire_at")
        if exp:
            venc = date.fromisoformat(str(exp)[:10])
        pdf = billet.get("pdf") if isinstance(billet.get("pdf"), dict) else {}
        link = billet.get("link") or billet.get("billet_link") or pdf.get("charge")
        total = raw.get("total") or raw.get("value")
        if total is not None and str(total).isdigit():
            valor = int(total)
    except Exception:
        log.exception("Detalhe da cobrança Efí %s indisponível", charge_id)
    ref = referencia_assinatura(periodo, venc)
    cur.execute(
        """
        INSERT INTO tbl_fatura (
            id_tenant, referencia, valor_centavos, status, forma_pagamento, plano_slug,
            efi_charge_id, link_boleto, vencimento_em, atualizado_em,
            periodicidade, meses_cobertos
        ) VALUES (
            %s, %s, %s, 'pendente', %s, %s,
            %s, %s, %s, NOW(),
            %s, %s
        )
        RETURNING id
        """,
        (
            id_tenant,
            ref,
            valor,
            forma,
            plano_slug,
            charge_id,
            link,
            venc,
            periodo,
            _intervalo_meses(periodo),
        ),
    )
    return int(cur.fetchone()[0])


def processar_webhook_efi(cur, payload: dict) -> dict:
    charge_id = str(
        payload.get("charge_id")
        or payload.get("id")
        or (payload.get("data") or {}).get("charge_id")
        or payload.get("txid")
        or ""
    ).strip()
    status_raw = (
        payload.get("status")
        or (payload.get("data") or {}).get("status")
        or ""
    )
    registrar_efi_log(
        cur,
        id_tenant=None,
        id_fatura=None,
        direcao="in",
        operacao="webhook",
        ok=bool(charge_id),
        efi_charge_id=charge_id or None,
        request_resumo=payload,
    )
    novo = _mapa_status_efi_local(str(status_raw))
    tipo_aviso = str(payload.get("tipo") or payload.get("type") or "").strip().lower()
    if not charge_id:
        if novo == "cancelado" and _tenant_do_aviso(cur, payload):
            id_tenant = _tenant_do_aviso(cur, payload)
            cur.execute(
                """
                UPDATE tbl_tenant_cobranca
                SET assinatura_status = 'cancelada',
                    cancelado_em = COALESCE(cancelado_em, NOW()),
                    atualizado_em = NOW()
                WHERE id_tenant = %s
                """,
                (id_tenant,),
            )
            return {"ok": True, "status": "cancelado", "id_tenant": id_tenant}
        return {"ok": False, "message": "charge_id ausente."}
    cur.execute(
        """
        SELECT id, id_tenant, status FROM tbl_fatura
        WHERE efi_charge_id = %s OR efi_txid = %s
        ORDER BY id DESC LIMIT 1
        """,
        (charge_id, charge_id),
    )
    row = cur.fetchone()
    if not row:
        presa = _fatura_do_custom(cur, payload)
        if presa:
            fid, _tid, _st, antiga = int(presa[0]), int(presa[1]), presa[2], presa[3]
            if str(antiga or "") != charge_id:
                cur.execute(
                    """
                    UPDATE tbl_fatura
                    SET efi_charge_id = %s,
                        forma_pagamento = 'cartao',
                        link_boleto = NULL,
                        codigo_barras = NULL,
                        atualizado_em = NOW()
                    WHERE id = %s AND status <> 'pago'
                    """,
                    (charge_id, fid),
                )
                if antiga and novo == "pago":
                    try:
                        from api.efi.efi import cancelar_cobranca

                        cancelar_cobranca(str(antiga))
                    except Exception:
                        log.exception("Boleto %s da fatura %s não cancelado", antiga, fid)
            cur.execute(
                "SELECT id, id_tenant, status FROM tbl_fatura WHERE id = %s",
                (fid,),
            )
            row = cur.fetchone()
    if not row:
        id_tenant_aviso = _tenant_do_aviso(cur, payload)
        if not id_tenant_aviso:
            return {"ok": True, "ignorado": True, "charge_id": charge_id}
        novo_id = _abrir_fatura_de_aviso(cur, id_tenant_aviso, charge_id)
        if not novo_id:
            return {"ok": True, "ignorado": True, "charge_id": charge_id}
        cur.execute(
            "SELECT id, id_tenant, status FROM tbl_fatura WHERE id = %s",
            (novo_id,),
        )
        row = cur.fetchone()

    id_fatura, id_tenant, st_atual = int(row[0]), int(row[1]), row[2]
    if novo == "cancelado" and tipo_aviso == "subscription":
        cur.execute(
            """
            UPDATE tbl_tenant_cobranca
            SET assinatura_status = 'cancelada',
                cancelado_em = COALESCE(cancelado_em, NOW()),
                atualizado_em = NOW()
            WHERE id_tenant = %s
              AND COALESCE(assinatura_status, '') <> 'cancelada'
            """,
            (id_tenant,),
        )
    registrar_efi_log(
        cur,
        id_tenant=id_tenant,
        id_fatura=id_fatura,
        direcao="in",
        operacao="webhook_match",
        ok=True,
        efi_charge_id=charge_id,
        response_resumo={"status": novo, "status_atual": st_atual},
    )

    if novo == "pago":
        # Não sobrescreve MED (pago bloqueado) — o sync de infrações gerencia isso.
        if st_atual in ("pago", "bloqueado"):
            return {"ok": True, "status": st_atual, "id_fatura": id_fatura}
        pago_dt = _parse_pago_em_efi(payload if isinstance(payload, dict) else None)
        if pago_dt is None:
            try:
                from api.efi.efi import consultar_cobranca

                pago_dt = _parse_pago_em_efi(consultar_cobranca(charge_id))
            except Exception:
                log.exception("paid_at Efí charge %s indisponível no webhook", charge_id)
        return aplicar_pagamento_fatura(cur, id_fatura, origem="webhook", pago_em=pago_dt)

    cur.execute(
        """
        UPDATE tbl_fatura SET status = %s, atualizado_em = NOW()
        WHERE id = %s AND status NOT IN ('pago', 'bloqueado')
        """,
        (novo, id_fatura),
    )
    return {"ok": True, "status": novo, "id_fatura": id_fatura}


def sincronizar_fatura_com_efi(cur, id_fatura: int) -> dict:
    """Reconsulta a charge na Efí e espelha status/pago_em na fatura local."""
    cur.execute(
        """
        SELECT id, id_tenant, status, efi_charge_id, efi_txid, valor_centavos
        FROM tbl_fatura WHERE id = %s
        """,
        (id_fatura,),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "message": "Fatura não encontrada."}
    fid, id_tenant, st_atual = int(row[0]), int(row[1]), (row[2] or "").strip().lower()
    charge = str(row[3] or "").strip()
    if not charge or not charge.isdigit():
        return {"ok": False, "message": "Fatura sem efi_charge_id numérico.", "id_fatura": fid}

    from api.efi.efi import consultar_cobranca

    try:
        det = consultar_cobranca(charge)
    except Exception as e:
        registrar_efi_log(
            cur,
            id_tenant=id_tenant,
            id_fatura=fid,
            direcao="out",
            operacao="sincronizar_charge",
            ok=False,
            efi_charge_id=charge,
            response_resumo=_texto_efi(e),
        )
        return {"ok": False, "message": f"Falha ao consultar Efí: {_texto_efi(e)}", "id_fatura": fid}

    status_local = (det.get("status") or "pendente").strip().lower()
    status_efi = (det.get("status_efi") or "").strip().lower()
    pago_dt = _parse_pago_em_efi(det)
    registrar_efi_log(
        cur,
        id_tenant=id_tenant,
        id_fatura=fid,
        direcao="out",
        operacao="sincronizar_charge",
        ok=True,
        efi_charge_id=charge,
        response_resumo={"status_efi": status_efi, "status_local": status_local, "pago_em": str(pago_dt or "")},
    )

    if status_local == "pago":
        if st_atual in ("pago", "bloqueado"):
            if pago_dt and st_atual == "pago":
                cur.execute(
                    """
                    UPDATE tbl_fatura
                    SET pago_em = COALESCE(pago_em, %s), atualizado_em = NOW()
                    WHERE id = %s
                    """,
                    (pago_dt, fid),
                )
            return {
                "ok": True,
                "id_fatura": fid,
                "status": st_atual,
                "status_efi": status_efi,
                "alterado": False,
            }
        out = aplicar_pagamento_fatura(cur, fid, origem="sync_efi", pago_em=pago_dt)
        out.update({"status_efi": status_efi, "alterado": True})
        return out

    if st_atual in ("pago", "bloqueado"):
        return {
            "ok": True,
            "id_fatura": fid,
            "status": st_atual,
            "status_efi": status_efi,
            "alterado": False,
            "message": "Fatura local já liquidada; Efí não está paid.",
        }

    cur.execute(
        """
        UPDATE tbl_fatura SET status = %s, atualizado_em = NOW()
        WHERE id = %s AND status NOT IN ('pago', 'bloqueado')
        """,
        (status_local, fid),
    )
    return {
        "ok": True,
        "id_fatura": fid,
        "status": status_local,
        "status_efi": status_efi,
        "alterado": st_atual != status_local,
    }


def sincronizar_cobrancas_efi_abertas(cur, *, limite: int = 80) -> dict:
    """ reconcilia faturas com charge Efí ainda não liquidadas (pendente/vencido)."""
    cur.execute(
        """
        SELECT id
        FROM tbl_fatura
        WHERE status IN ('pendente', 'vencido')
          AND NULLIF(TRIM(COALESCE(efi_charge_id, '')), '') IS NOT NULL
          AND efi_charge_id ~ '^[0-9]+$'
          AND COALESCE(valor_centavos, 0) > 0
        ORDER BY id DESC
        LIMIT %s
        """,
        (max(1, min(int(limite or 80), 200)),),
    )
    ids = [int(r[0]) for r in cur.fetchall()]
    alterados = 0
    pagos = 0
    erros = []
    for fid in ids:
        try:
            r = sincronizar_fatura_com_efi(cur, fid)
            if r.get("alterado"):
                alterados += 1
            if (r.get("status") or "") == "pago":
                pagos += 1
            if not r.get("ok"):
                erros.append({"id_fatura": fid, "message": r.get("message")})
        except Exception as e:
            erros.append({"id_fatura": fid, "message": str(e)})
            log.exception("sync Efí fatura %s", fid)
    return {
        "ok": True,
        "consultadas": len(ids),
        "alterados": alterados,
        "pagos": pagos,
        "erros": erros[:20],
    }


def rebaixar_tenant_starter(cur, id_tenant: int, *, id_fatura: int | None = None) -> None:
    cur.execute("UPDATE tbl_tenant SET plano = 'starter' WHERE id = %s", (id_tenant,))
    cur.execute(
        """
        UPDATE tbl_tenant_cobranca
        SET plano_slug = 'starter', plano_slug_pendente = NULL, atualizado_em = NOW()
        WHERE id_tenant = %s
        """,
        (id_tenant,),
    )
    if id_fatura:
        cur.execute(
            "UPDATE tbl_fatura SET rebaixado_em = NOW(), atualizado_em = NOW() WHERE id = %s",
            (id_fatura,),
        )
    fat = obter_fatura(cur, id_tenant, id_fatura) if id_fatura else None
    if fat:
        _enviar_email_fatura(cur, id_tenant, fat, tipo="rebaixado")


def job_financeiro_diario(cur) -> dict:
    """Marca vencidas, avisa atraso e, 30 dias após o vencimento, cancela a recorrência."""
    hoje = date.today()
    garantir_colunas_assinatura(cur)
    res = {"vencidas": 0, "avisos": 0, "rebaixados": 0, "renovacoes": 0, "erros": []}

    cur.execute(
        """
        UPDATE tbl_fatura
        SET status = 'vencido', atualizado_em = NOW()
        WHERE status = 'pendente' AND vencimento_em < %s
        RETURNING id
        """,
        (hoje,),
    )
    res["vencidas"] = len(cur.fetchall())

    # aviso 1x: boleto sem pagamento já no prazo de graça / vencido
    cur.execute(
        """
        SELECT id, id_tenant, forma_pagamento, criado_em, vencimento_em
        FROM tbl_fatura
        WHERE status IN ('pendente', 'vencido') AND avisado_em IS NULL
        """
    )
    for fid, tid, forma, criado, venc in cur.fetchall():
        avisar = False
        if (forma or "").lower() == "boleto":
            base = criado.date() if isinstance(criado, datetime) else criado
            if base:
                # avisa a partir de 2 dias úteis antes do fim da graça
                inicio_aviso = adicionar_dias_uteis(base, max(1, DIAS_UTEIS_GRACA_BOLETO - 2))
                avisar = hoje >= inicio_aviso
        elif venc and venc <= hoje:
            avisar = True
        if not avisar:
            continue
        fat = obter_fatura(cur, int(tid), int(fid))
        if fat:
            _enviar_email_fatura(cur, int(tid), fat, tipo="aviso")
            cur.execute("UPDATE tbl_fatura SET avisado_em = NOW() WHERE id = %s", (fid,))
            res["avisos"] += 1

    # 30 dias após o vencimento sem pagamento: plano gratuito e cancela a recorrência.
    limite = hoje - timedelta(days=DIAS_ATRASO_CANCELA)
    cur.execute(
        """
        SELECT f.id, f.id_tenant
        FROM tbl_fatura f
        JOIN tbl_tenant t ON t.id = f.id_tenant
        WHERE f.status IN ('pendente', 'vencido')
          AND f.rebaixado_em IS NULL
          AND f.vencimento_em IS NOT NULL
          AND f.vencimento_em <= %s
          AND t.plano IS DISTINCT FROM 'starter'
        ORDER BY f.id
        """,
        (limite,),
    )
    ja_rebaixou: set[int] = set()
    for fid, tid in cur.fetchall():
        tid_n = int(tid)
        if tid_n in ja_rebaixou:
            cur.execute(
                "UPDATE tbl_fatura SET rebaixado_em = NOW(), atualizado_em = NOW() WHERE id = %s",
                (int(fid),),
            )
            continue
        _encerrar_assinatura_efi(cur, tid_n)
        rebaixar_tenant_starter(cur, tid_n, id_fatura=int(fid))
        ja_rebaixou.add(tid_n)
        res["rebaixados"] += 1

    # Assinatura já cancelada: o período pago segue até o fim, depois volta ao gratuito.
    cur.execute(
        """
        SELECT tc.id_tenant
        FROM tbl_tenant_cobranca tc
        JOIN tbl_tenant t ON t.id = tc.id_tenant
        WHERE tc.assinatura_status = 'cancelada'
          AND t.plano IS DISTINCT FROM 'starter'
        """
    )
    for (tid,) in cur.fetchall():
        cur.execute(
            """
            SELECT COALESCE(pago_em, criado_em)::date, COALESCE(meses_cobertos, 1)
            FROM tbl_fatura
            WHERE id_tenant = %s AND status = 'pago'
            ORDER BY pago_em DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            (tid,),
        )
        ultimo = cur.fetchone()
        if ultimo and ultimo[0] and hoje < adicionar_meses(ultimo[0], max(1, int(ultimo[1] or 1))):
            continue
        rebaixar_tenant_starter(cur, int(tid))
        res["rebaixados"] += 1

    # renovação: no dia de vencimento, se a cobertura do ciclo anterior já acabou
    cur.execute(
        """
        SELECT tc.id_tenant, tc.dia_vencimento, tc.forma_pagamento, tc.plano_slug,
               COALESCE(NULLIF(tc.periodicidade, ''), 'mensal')
        FROM tbl_tenant_cobranca tc
        JOIN tbl_tenant t ON t.id = tc.id_tenant
        JOIN tbl_plano p ON p.slug = tc.plano_slug
        WHERE t.plano IN ('professional', 'scale', 'enterprise')
          AND p.valor_centavos > 0
          AND tc.dia_vencimento = %s
          AND COALESCE(tc.efi_subscription_id, '') = ''
          AND COALESCE(tc.assinatura_status, '') <> 'cancelada'
          AND NOT (
            COALESCE(t.eh_fornecedor_fundador, FALSE)
            AND COALESCE(t.fornecedor_fundador_ativo, FALSE)
          )
        """,
        (hoje.day,),
    )
    for tid, _dia, forma, slug, periodo in cur.fetchall():
        try:
            periodo = (periodo or "mensal").strip().lower()
            if periodo not in ("mensal", "semestral", "anual"):
                periodo = "mensal"
            cur.execute(
                """
                SELECT referencia, COALESCE(meses_cobertos, 1),
                       COALESCE(pago_em, criado_em)::date, status
                FROM tbl_fatura
                WHERE id_tenant = %s AND plano_slug = %s
                  AND status IN ('pendente', 'pago', 'vencido')
                ORDER BY id DESC
                LIMIT 1
                """,
                (tid, slug),
            )
            last = cur.fetchone()
            if last:
                meses = max(1, int(last[1] or 1))
                base = last[2]
                if base and hoje < adicionar_meses(base, meses):
                    continue
                ref = referencia_assinatura(periodo, hoje)
                if last[0] == ref and last[3] in ("pendente", "pago", "vencido"):
                    continue
            else:
                ref = referencia_assinatura(periodo, hoje)
            emitir_fatura(
                cur,
                int(tid),
                plano_slug=slug,
                forma=forma or "boleto",
                referencia=ref,
                periodicidade=periodo,
            )
            res["renovacoes"] += 1
        except Exception as e:
            res["erros"].append({"id_tenant": tid, "erro": str(e)})

    return res


def listar_efi_logs(cur, *, page: int = 1, por_pagina: int = 50, id_tenant: int | None = None) -> dict:
    page = max(1, page)
    por_pagina = min(100, max(10, por_pagina))
    where = "WHERE 1=1"
    params: list[Any] = []
    if id_tenant:
        where += " AND id_tenant = %s"
        params.append(id_tenant)
    cur.execute(f"SELECT COUNT(*) FROM tbl_efi_log {where}", params)
    total = int(cur.fetchone()[0] or 0)
    off = (page - 1) * por_pagina
    cur.execute(
        f"""
        SELECT id, id_tenant, id_fatura, direcao, operacao, http_status, efi_charge_id,
               request_resumo, response_resumo, ok, criado_em
        FROM tbl_efi_log {where}
        ORDER BY id DESC
        LIMIT %s OFFSET %s
        """,
        params + [por_pagina, off],
    )
    logs = []
    for r in cur.fetchall():
        logs.append(
            {
                "id": r[0],
                "id_tenant": r[1],
                "id_fatura": r[2],
                "direcao": r[3],
                "operacao": r[4],
                "http_status": r[5],
                "efi_charge_id": r[6],
                "request_resumo": r[7],
                "response_resumo": r[8],
                "ok": r[9],
                "criado_em": r[10].isoformat() if r[10] else None,
            }
        )
    return {
        "logs": logs,
        "total": total,
        "pagina": page,
        "total_paginas": max(1, (total + por_pagina - 1) // por_pagina),
    }


def conta_tem_assinatura_ativa(cur, id_tenant: int) -> bool:
    """Plano pago ou recorrência na Efí ainda não cancelada."""
    garantir_colunas_assinatura(cur)
    cur.execute(
        """
        SELECT COALESCE(t.plano, 'starter'),
               COALESCE(tc.assinatura_status, ''),
               COALESCE(tc.efi_subscription_id, '')
        FROM tbl_tenant t
        LEFT JOIN tbl_tenant_cobranca tc ON tc.id_tenant = t.id
        WHERE t.id = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return False
    plano = (row[0] or "starter").strip().lower()
    status = (row[1] or "").strip().lower()
    if status == "cancelada":
        return False
    if plano in PLANOS_PAGOS:
        return True
    return bool((row[2] or "").strip())


def _exigir_endereco_cartao(cli: dict) -> None:
    end = cli.get("endereco") or {}
    cep = "".join(c for c in (end.get("cep") or "") if c.isdigit())
    uf = (end.get("uf") or "").strip()
    if (
        len(cep) != 8
        or not (end.get("logradouro") or "").strip()
        or not (end.get("bairro") or "").strip()
        or not (end.get("cidade") or "").strip()
        or len(uf) != 2
    ):
        raise ValueError(
            "Para pagar com cartão, complete o endereço da empresa em Meu perfil → Empresa "
            "(CEP, rua, bairro, cidade e UF)."
        )


def trocar_forma_proximas_cobrancas(
    cur,
    id_tenant: int,
    forma: str,
    *,
    payment_token: str | None = None,
) -> dict:
    """A assinatura continua a mesma. A Efí passa a emitir os ciclos seguintes na forma nova."""
    garantir_cobranca_tenant(cur, id_tenant)
    forma_n = (forma or "").strip().lower()
    if forma_n not in ("boleto", "cartao"):
        raise ValueError("Escolha boleto ou cartão de crédito.")
    cur.execute(
        """
        SELECT efi_subscription_id, COALESCE(assinatura_status, '')
        FROM tbl_tenant_cobranca WHERE id_tenant = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    sub = (row[0] if row else "") or ""
    status = (row[1] if row else "").strip().lower()
    if not str(sub).strip() or status == "cancelada":
        raise ValueError(
            "Não há recorrência ativa para mudar as próximas cobranças. "
            "Dá para pagar a fatura em aberto no cartão, se houver uma."
        )
    cli = _dados_cliente_cobranca(cur, id_tenant)
    if forma_n == "cartao":
        _exigir_endereco_cartao(cli)
        if not (payment_token or "").strip():
            raise ValueError("Informe o cartão de crédito.")
    from api.efi.efi import definir_forma_assinatura

    definir_forma_assinatura(
        subscription_id=str(sub),
        forma=forma_n,
        nome_cliente=cli["nome_cliente"],
        documento=cli["documento"],
        email=cli["email_cobranca"],
        telefone=cli.get("telefone"),
        endereco=cli.get("endereco"),
        payment_token=payment_token,
        vencimento=proximo_vencimento(cli["dia_vencimento"]),
    )
    cur.execute(
        """
        UPDATE tbl_tenant_cobranca
        SET forma_pagamento = %s, atualizado_em = NOW()
        WHERE id_tenant = %s
        """,
        (forma_n, id_tenant),
    )
    registrar_efi_log(
        cur,
        id_tenant=id_tenant,
        id_fatura=None,
        direcao="out",
        operacao="trocar_forma_assinatura",
        ok=True,
        response_resumo={"forma": forma_n},
    )
    if forma_n == "cartao":
        texto = (
            "As próximas cobranças saem no cartão de crédito. "
            "A fatura que já está em aberto continua como está."
        )
    else:
        texto = (
            "As próximas cobranças saem no boleto. "
            "A fatura que já está em aberto continua como está."
        )
    return {"mensagem": texto, "forma": forma_n}


def pagar_fatura_aberta_no_cartao(
    cur,
    id_tenant: int,
    id_fatura: int,
    *,
    payment_token: str,
    installments: int = 1,
) -> dict:
    """Paga só esta fatura no cartão. A recorrência permanece no boleto."""
    fat = obter_fatura(cur, id_tenant, id_fatura)
    if not fat:
        raise ValueError("Fatura não encontrada.")
    if fat["status"] not in ("pendente", "vencido"):
        raise ValueError("Esta fatura não está em aberto.")
    if (fat.get("forma_pagamento") or "").strip().lower() != "boleto":
        raise ValueError("Esta opção vale para a fatura que está em boleto.")
    antiga = str(fat.get("efi_charge_id") or "").strip()
    if not antiga.isdigit():
        raise ValueError("Esta fatura não tem boleto na Efí para substituir.")
    cli = _dados_cliente_cobranca(cur, id_tenant)
    _exigir_endereco_cartao(cli)
    from api.efi.efi import cancelar_cobranca, consultar_cobranca, criar_cobranca_cartao

    det = consultar_cobranca(antiga)
    if det.get("status") == "pago":
        raise ValueError("Este boleto já foi pago.")
    plano = obter_plano_db(cur, fat.get("plano_slug") or "") or {}
    nome = plano.get("nome") or fat.get("plano_slug") or "Plano"
    cob = criar_cobranca_cartao(
        nome_cliente=cli["nome_cliente"],
        documento=cli["documento"],
        email=cli["email_cobranca"],
        valor_centavos=int(fat["valor_centavos"] or 0),
        descricao=f"DropNexo — {nome} ({fat.get('referencia') or id_fatura})",
        payment_token=payment_token,
        installments=installments,
        telefone=cli.get("telefone"),
        endereco=cli.get("endereco"),
        custom_id=f"fat-{id_fatura}",
    )
    if not cob.get("pago"):
        raise ValueError(
            "O cartão ainda não foi aprovado. O boleto desta fatura continua valendo."
        )
    cur.execute("SELECT status FROM tbl_fatura WHERE id = %s AND id_tenant = %s", (id_fatura, id_tenant))
    atual = cur.fetchone()
    if not atual or atual[0] != "pago":
        cur.execute(
            """
            UPDATE tbl_fatura
            SET efi_charge_id = %s,
                forma_pagamento = 'cartao',
                link_boleto = NULL,
                codigo_barras = NULL,
                pix_copia_cola = NULL,
                pix_qrcode = NULL,
                atualizado_em = NOW()
            WHERE id = %s AND id_tenant = %s
            """,
            (cob.get("charge_id"), id_fatura, id_tenant),
        )
        aplicar_pagamento_fatura(cur, id_fatura, origem="cartao_fatura")
    texto = "Esta fatura foi paga no cartão. As próximas cobranças continuam no boleto."
    try:
        cancelar_cobranca(antiga)
    except Exception:
        log.exception("Boleto %s da fatura %s ficou em aberto após o cartão", antiga, id_fatura)
        texto += " Se o boleto antigo ainda abrir, não pague: esta fatura já está paga no cartão."
    return {"mensagem": texto}


def resumo_assinatura_tenant(cur, id_tenant: int) -> dict:
    garantir_cobranca_tenant(cur, id_tenant)
    cur.execute(
        """
        SELECT t.plano, COALESCE(NULLIF(tc.plano_slug, ''), t.plano),
               COALESCE(NULLIF(tc.periodicidade, ''), 'mensal'),
               COALESCE(tc.forma_pagamento, ''),
               COALESCE(tc.assinatura_status, ''),
               tc.cancelado_em, tc.dia_vencimento, tc.efi_subscription_id,
               t.tipo_negocio
        FROM tbl_tenant t
        LEFT JOIN tbl_tenant_cobranca tc ON tc.id_tenant = t.id
        WHERE t.id = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return {}
    slug = (row[1] or row[0] or "starter").strip().lower()
    plano = obter_plano_db(cur, slug) or {}
    from sistema.financeiro.assinaturas_painel import nome_plano_comercial

    periodo = (row[2] or "mensal").strip().lower()
    status = (row[4] or "").strip().lower()
    cur.execute(
        """
        SELECT id, referencia, valor_centavos, vencimento_em
        FROM tbl_fatura
        WHERE id_tenant = %s
          AND status IN ('pendente', 'vencido')
          AND lower(COALESCE(forma_pagamento, '')) = 'boleto'
        ORDER BY id DESC
        LIMIT 1
        """,
        (id_tenant,),
    )
    aberta = cur.fetchone()
    fatura_aberta = None
    if aberta:
        centavos = int(aberta[2] or 0)
        fatura_aberta = {
            "id": int(aberta[0]),
            "referencia": aberta[1] or "",
            "valor_centavos": centavos,
            "valor_formatado": f"R$ {centavos / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "vencimento_em": aberta[3].isoformat() if aberta[3] else None,
        }
    return {
        "plano_slug": slug,
        "plano_nome": nome_plano_comercial(slug, row[8]),
        "periodicidade": periodo,
        "forma_pagamento": (row[3] or "").strip().lower(),
        "assinatura_status": status or ("ativa" if row[7] else ""),
        "cancelado_em": row[5].isoformat() if row[5] else None,
        "dia_vencimento": row[6],
        "recorrencia_efi": bool(row[7]),
        "valor_centavos": int(plano.get("valor_centavos") or 0),
        "valor_formatado": f"R$ {int(plano.get('valor_centavos') or 0) / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "pode_cancelar": slug != "starter" and status != "cancelada",
        "pode_trocar_proximas": bool(row[7]) and status != "cancelada",
        "fatura_aberta": fatura_aberta,
        "pode_pagar_esta": fatura_aberta is not None,
    }


def cancelar_plano_atual(cur, id_tenant: int) -> dict:
    """Encerra a recorrência na Efí. O período já pago segue até o fim."""
    garantir_cobranca_tenant(cur, id_tenant)
    _encerrar_assinatura_efi(cur, id_tenant)
    cur.execute(
        """
        UPDATE tbl_tenant_cobranca
        SET assinatura_status = 'cancelada',
            cancelado_em = COALESCE(cancelado_em, NOW()),
            atualizado_em = NOW()
        WHERE id_tenant = %s
        """,
        (id_tenant,),
    )
    return {
        "ok": True,
        "mensagem": (
            "Assinatura cancelada. Não haverá novas cobranças. "
            "O período já pago continua até o fim e, depois disso, a conta volta ao Explorar."
        ),
    }


def criar_assinatura_efi_admin(cur, id_tenant: int) -> dict:
    """
    Migra assinante legado (renovação DropNexo) para recorrência Efí.
    A 1ª cobrança na Efí vence no próximo ciclo — não re-cobra o período já pago.
    Cartão exige token do cliente; nesta ação admin só boleto.
    """
    from sistema.financeiro.cupom import (
        calcular_preco,
        normalizar_periodo,
        obter_cupom_beneficio_renovacao,
    )
    from sistema.planos.fornecedor_fundador import eh_fundador_ativo

    garantir_cobranca_tenant(cur, id_tenant)
    garantir_colunas_assinatura(cur)
    garantir_referencia_fatura(cur)

    if eh_fundador_ativo(cur, int(id_tenant)):
        raise ValueError("Fornecedor Fundador não gera assinatura na Efí.")

    cur.execute(
        """
        SELECT COALESCE(efi_subscription_id, ''), COALESCE(assinatura_status, ''),
               COALESCE(NULLIF(periodicidade, ''), 'mensal'), COALESCE(forma_pagamento, 'boleto'),
               COALESCE(NULLIF(plano_slug, ''), '')
        FROM tbl_tenant_cobranca WHERE id_tenant = %s
        """,
        (id_tenant,),
    )
    tc = cur.fetchone()
    if not tc:
        raise ValueError("Cobrança do tenant não encontrada.")
    sub_id, st_ass, periodo_raw, forma_raw, plano_tc = tc
    if str(sub_id or "").strip() and (st_ass or "") != "cancelada":
        raise ValueError("Este tenant já tem assinatura ativa na Efí.")

    cur.execute("SELECT plano, ativo FROM tbl_tenant WHERE id = %s", (id_tenant,))
    trow = cur.fetchone()
    if not trow or not trow[1]:
        raise ValueError("Tenant inválido ou inativo.")
    plano_slug = (plano_tc or trow[0] or "").strip().lower()
    if plano_slug not in PLANOS_PAGOS:
        raise ValueError("Só planos pagos podem ter assinatura na Efí.")

    forma = (forma_raw or "boleto").strip().lower()
    if forma == "cartao":
        raise ValueError(
            "Forma atual é cartão. Sem o token do cartão não dá para criar a recorrência aqui. "
            "Peça ao cliente para atualizar o pagamento no Financeiro, ou mude a forma para boleto."
        )
    # Pix avulso não gera recorrência Efí de assinatura — usa boleto
    forma_efi = "boleto"

    periodo = normalizar_periodo(periodo_raw)
    plano = obter_plano_db(cur, plano_slug)
    if not plano or int(plano.get("valor_centavos") or 0) <= 0:
        raise ValueError("Plano sem valor de cobrança.")

    cupom = obter_cupom_beneficio_renovacao(cur, int(id_tenant), periodo, plano_slug=plano_slug)
    preco = calcular_preco(int(plano["valor_centavos"]), periodo, cupom=cupom)
    valor_final = int(preco["valor_final_centavos"])
    if valor_final <= 0:
        raise ValueError("Valor final zerado (benefício). Não cria assinatura na Efí.")

    cli = _dados_cliente_cobranca(cur, id_tenant)
    doc = "".join(c for c in (cli.get("documento") or "") if c.isdigit())
    if len(doc) not in (11, 14):
        raise ValueError("Tenant sem CPF/CNPJ válido para a Efí.")
    email = (cli.get("email_cobranca") or "").strip()
    if not email or "@" not in email:
        raise ValueError("Tenant sem e-mail de cobrança.")

    cur.execute(
        """
        SELECT COALESCE(pago_em, criado_em)::date, COALESCE(meses_cobertos, 1)
        FROM tbl_fatura
        WHERE id_tenant = %s AND status IN ('pago', 'bloqueado')
        ORDER BY pago_em DESC NULLS LAST, id DESC
        LIMIT 1
        """,
        (id_tenant,),
    )
    ultimo = cur.fetchone()
    fim_cobertura = None
    if ultimo and ultimo[0]:
        fim_cobertura = adicionar_meses(ultimo[0], max(1, int(ultimo[1] or 1)))

    dia = int(cli.get("dia_vencimento") or 15)
    venc = proximo_vencimento(dia)
    if fim_cobertura and venc < fim_cobertura:
        venc = proximo_vencimento(dia, fim_cobertura)

    ref = referencia_assinatura(periodo, venc)
    cur.execute(
        """
        SELECT id, status FROM tbl_fatura
        WHERE id_tenant = %s AND referencia = %s AND plano_slug = %s
        ORDER BY id DESC LIMIT 1
        """,
        (id_tenant, ref, plano_slug),
    )
    ex = cur.fetchone()
    if ex and ex[1] == "pago":
        # próximo ciclo depois dessa referência
        venc = proximo_vencimento(dia, adicionar_meses(venc, max(1, int(preco.get("meses_cobertos") or 1))))
        ref = referencia_assinatura(periodo, venc)
        ex = None

    from api.efi.efi import efi_disponivel

    if not efi_disponivel():
        raise RuntimeError("Efi não configurada no servidor (.env).")

    descricao = f"DropNexo — {plano['nome']} · {preco['periodo_rotulo']} ({ref})"
    cob = _criar_cobranca_efi(
        cur,
        id_tenant=id_tenant,
        forma=forma_efi,
        valor_centavos=valor_final,
        descricao=descricao,
        vencimento=venc,
        nome_cliente=cli["nome_cliente"],
        documento=cli["documento"],
        email=email,
        telefone=cli.get("telefone"),
        endereco=cli.get("endereco"),
        plano_slug=plano_slug,
        periodo=periodo,
        nome_plano=plano["nome"],
    )
    if not cob.get("subscription_id"):
        raise RuntimeError("A Efí não devolveu o ID da assinatura.")

    if ex and ex[1] in ("pendente", "vencido"):
        fid = int(ex[0])
        cur.execute(
            """
            UPDATE tbl_fatura
            SET valor_centavos = %s, forma_pagamento = %s, efi_charge_id = %s,
                link_boleto = %s, codigo_barras = %s, vencimento_em = %s,
                periodicidade = %s, meses_cobertos = %s,
                valor_cheio_centavos = %s, desconto_periodo_centavos = %s,
                desconto_cupom_centavos = %s, atualizado_em = NOW()
            WHERE id = %s
            """,
            (
                valor_final,
                forma_efi,
                cob.get("charge_id"),
                cob.get("link_boleto"),
                cob.get("codigo_barras"),
                venc,
                periodo,
                int(preco["meses_cobertos"]),
                int(preco["valor_cheio_centavos"]),
                int(preco["desconto_periodo_centavos"]),
                int(preco["desconto_cupom_centavos"]),
                fid,
            ),
        )
    else:
        cur.execute(
            """
            INSERT INTO tbl_fatura (
                id_tenant, referencia, valor_centavos, status, forma_pagamento, plano_slug,
                efi_charge_id, link_boleto, codigo_barras, vencimento_em, atualizado_em,
                periodicidade, meses_cobertos, valor_cheio_centavos,
                desconto_periodo_centavos, desconto_cupom_centavos
            ) VALUES (
                %s,%s,%s,'pendente',%s,%s,%s,%s,%s,%s,NOW(),%s,%s,%s,%s,%s
            ) RETURNING id
            """,
            (
                id_tenant,
                ref,
                valor_final,
                forma_efi,
                plano_slug,
                cob.get("charge_id"),
                cob.get("link_boleto"),
                cob.get("codigo_barras"),
                venc,
                periodo,
                int(preco["meses_cobertos"]),
                int(preco["valor_cheio_centavos"]),
                int(preco["desconto_periodo_centavos"]),
                int(preco["desconto_cupom_centavos"]),
            ),
        )
        fid = int(cur.fetchone()[0])

    cur.execute(
        """
        UPDATE tbl_tenant_cobranca
        SET efi_subscription_id = %s, efi_plan_id = %s,
            assinatura_status = 'ativa', cancelado_em = NULL,
            forma_pagamento = %s, periodicidade = %s, plano_slug = %s,
            atualizado_em = NOW()
        WHERE id_tenant = %s
        """,
        (
            str(cob["subscription_id"]),
            str(cob.get("plan_id") or ""),
            forma_efi,
            periodo,
            plano_slug,
            id_tenant,
        ),
    )

    return {
        "ok": True,
        "id_tenant": id_tenant,
        "id_fatura": fid,
        "efi_subscription_id": str(cob["subscription_id"]),
        "referencia": ref,
        "vencimento": venc.isoformat(),
        "valor_centavos": valor_final,
        "mensagem": (
            f"Assinatura criada na Efí. A 1ª cobrança ({ref}) vence em "
            f"{venc.strftime('%d/%m/%Y')} — o período já pago não foi re-cobrado."
        ),
    }


def detalhe_assinatura_admin(cur, id_tenant: int) -> dict:
    """Resumo da assinatura ativa para o painel do dono."""
    from sistema.financeiro.assinaturas_painel import (
        FORMA_LABEL,
        PERIODO_LABEL,
        _fmt_data_br,
        _fmt_reais,
        _proxima_cobranca_estimada,
        nome_plano_comercial,
    )

    garantir_cobranca_tenant(cur, id_tenant)
    garantir_colunas_assinatura(cur)
    cur.execute(
        """
        SELECT t.id, t.nome, t.slug, t.plano, t.tipo_negocio, t.ativo,
               COALESCE(NULLIF(tc.periodicidade, ''), 'mensal'),
               tc.dia_vencimento, tc.forma_pagamento, tc.inicio_cobranca,
               COALESCE(tc.efi_subscription_id, ''), COALESCE(tc.efi_plan_id, ''),
               COALESCE(tc.assinatura_status, ''), tc.cancelado_em,
               tc.email_cobranca
        FROM tbl_tenant t
        LEFT JOIN tbl_tenant_cobranca tc ON tc.id_tenant = t.id
        WHERE t.id = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Tenant não encontrado.")
    periodo = (row[6] or "mensal").strip().lower()
    forma = (row[8] or "").strip().lower()
    sub = str(row[10] or "").strip()
    st = str(row[12] or "").strip()
    prox = _proxima_cobranca_estimada(row[7])
    cur.execute(
        """
        SELECT id, referencia, status, valor_centavos, vencimento_em, pago_em, forma_pagamento
        FROM tbl_fatura WHERE id_tenant = %s
        ORDER BY id DESC LIMIT 1
        """,
        (id_tenant,),
    )
    fat = cur.fetchone()
    ultima = None
    if fat:
        ultima = {
            "id_fatura": int(fat[0]),
            "referencia": fat[1] or "",
            "status": fat[2] or "",
            "status_label": STATUS_LABEL.get(fat[2] or "", fat[2] or "—"),
            "valor": _fmt_reais(fat[3]),
            "vencimento_br": _fmt_data_br(fat[4]),
            "pago_br": _fmt_data_br(fat[5]),
            "forma_label": FORMA_LABEL.get((fat[6] or "").strip().lower(), fat[6] or "—"),
        }
    return {
        "id_tenant": int(row[0]),
        "nome": (row[1] or "").strip() or f"Tenant #{row[0]}",
        "slug": row[2] or "",
        "plano": row[3] or "",
        "plano_label": nome_plano_comercial(row[3], row[4]),
        "tipo_negocio": row[4] or "",
        "ativo": bool(row[5]),
        "periodicidade": periodo,
        "periodicidade_label": PERIODO_LABEL.get(periodo, periodo),
        "dia_vencimento": int(row[7]) if row[7] else None,
        "forma_pagamento": forma,
        "forma_label": FORMA_LABEL.get(forma, forma or "—"),
        "inicio_cobranca_br": _fmt_data_br(row[9]),
        "efi_subscription_id": sub or "",
        "efi_plan_id": str(row[11] or ""),
        "recorrencia_efi": bool(sub) and st != "cancelada",
        "assinatura_status": st or ("ativa" if sub else "sem_efi"),
        "assinatura_status_label": (
            "Ativa na Efí" if sub and st != "cancelada"
            else ("Cancelada" if st == "cancelada" else "Sem recorrência Efí (legado)")
        ),
        "cancelado_br": _fmt_data_br(row[13]),
        "email_cobranca": row[14] or "",
        "proxima_cobranca_br": _fmt_data_br(prox),
        "pode_criar_efi": (not sub or st == "cancelada") and str(row[3] or "").lower() in PLANOS_PAGOS,
        "pode_cancelar": str(row[3] or "").lower() in PLANOS_PAGOS and st != "cancelada",
        "ultima_fatura": ultima,
    }


def tenant_pode_usar_integracao(cur, id_tenant: int) -> bool:
    """Plano pago = integrações ativas (tokens permanecem; sync/UI bloqueados no free)."""
    cur.execute("SELECT plano, tipo_negocio FROM tbl_tenant WHERE id = %s", (id_tenant,))
    row = cur.fetchone()
    if not row:
        return False
    tipo = (row[1] or "vendedor").strip().lower()
    papel = "fornecedor" if tipo == "fornecedor" else "vendedor"
    if tipo == "hibrido":
        papel = "fornecedor"
    lim = limites_plano_tenant(cur, id_tenant, papel)
    return bool(lim.get("integracao"))
