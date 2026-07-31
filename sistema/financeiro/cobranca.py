# sistema/financeiro/cobranca.py — assinatura, faturas Efi, inadimplência 15 dias
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

DIAS_GRACA_INADIMPLENCIA = 15
PLANOS_PAGOS = ("professional", "scale", "enterprise")
FORMAS = ("boleto", "pix", "cartao")

STATUS_LABEL = {
    "pendente": "Emitida",
    "pago": "Paga",
    "vencido": "Vencida",
    "cancelado": "Cancelada",
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


def garantir_cobranca_tenant(cur, id_tenant: int) -> None:
    cur.execute("SELECT 1 FROM tbl_tenant_cobranca WHERE id_tenant = %s", (id_tenant,))
    if cur.fetchone():
        return
    cur.execute("SELECT plano, email_comercial FROM tbl_tenant WHERE id = %s", (id_tenant,))
    row = cur.fetchone()
    plano = (row[0] if row else None) or "starter"
    email = row[1] if row else None
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
    return {
        "dia_vencimento": int(row[0] or 15),
        "email_cobranca": (row[1] or "").strip(),
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


def fatura_dict(row) -> dict:
    # id, referencia, valor, status, forma, plano, link_boleto, codigo, pix, qr, link_pag,
    # venc, pago, criado, efi_charge, efi_txid
    st = row[3] or "pendente"
    return {
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
    }


_FATURA_COLS = """
    id, referencia, valor_centavos, status, forma_pagamento, plano_slug,
    link_boleto, codigo_barras, pix_copia_cola, pix_qrcode, link_pagamento,
    vencimento_em, pago_em, criado_em, efi_charge_id, efi_txid
"""


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


def _enviar_email_fatura(cur, id_tenant: int, fatura: dict, *, tipo: str) -> None:
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
    if not email:
        return
    base = obter_base_url().rstrip("/")
    assuntos = {
        "emitida": f"Fatura {fatura['referencia']} emitida • DropNexo",
        "aviso": f"Fatura {fatura['referencia']} em atraso • DropNexo",
        "rebaixado": "Plano rebaixado para Explorar • DropNexo",
        "pago": f"Pagamento confirmado — fatura {fatura['referencia']} • DropNexo",
    }
    mensagens = {
        "emitida": "Sua fatura foi emitida. Pague até o vencimento para manter o plano ativo.",
        "aviso": (
            f"Sua fatura está em atraso. Se permanecer sem pagamento por {DIAS_GRACA_INADIMPLENCIA} dias "
            "após o vencimento, o plano volta ao gratuito (Explorar) e as integrações ficam bloqueadas "
            "(a conexão não é removida)."
        ),
        "rebaixado": (
            "Sua conta voltou ao plano Explorar por inadimplência. "
            "Integrações permanecem conectadas, mas o acesso e as atualizações ficam bloqueados até assinar novamente."
        ),
        "pago": "Recebemos o pagamento. Seu plano permanece ativo.",
    }
    try:
        html = render_template(
            "financeiro/emails/fatura.html",
            titulo_email=assuntos.get(tipo, "Fatura • DropNexo"),
            nome_destinatario=cli["nome_cliente"],
            mensagem_principal=mensagens.get(tipo, ""),
            fatura=fatura,
            link_financeiro=f"{base}/financeiro",
            dias_graca=DIAS_GRACA_INADIMPLENCIA,
            **_email_links(),
        )
        enviar_email([email], assuntos.get(tipo, "Fatura • DropNexo"), html, tag="dropnexo_financeiro")
    except Exception:
        log.exception("E-mail financeiro falhou tenant=%s tipo=%s", id_tenant, tipo)


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
) -> dict:
    from api.efi import efi as efi_mod

    if forma == "pix":
        raise ValueError("PIX será liberado em breve. Use boleto ou cartão.")
    if forma == "cartao":
        if not payment_token:
            raise ValueError("Token do cartão ausente. Preencha os dados do cartão novamente.")
        cob = efi_mod.criar_cobranca_cartao(
            nome_cliente=nome_cliente,
            documento=documento,
            email=email,
            valor_centavos=valor_centavos,
            descricao=descricao,
            payment_token=payment_token,
            installments=installments,
            telefone=telefone,
            endereco=endereco,
        )
    else:
        cob = efi_mod.criar_cobranca_boleto(
            nome_cliente=nome_cliente,
            documento=documento,
            email=email,
            valor_centavos=valor_centavos,
            descricao=descricao,
            vencimento=vencimento,
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
) -> dict:
    """Emite fatura do plano (assinatura ou renovação)."""
    forma = (forma or "boleto").strip().lower()
    if forma not in FORMAS:
        raise ValueError("Forma de pagamento inválida.")
    plano = obter_plano_db(cur, plano_slug)
    if not plano:
        raise ValueError("Plano não encontrado.")
    if int(plano["valor_centavos"] or 0) <= 0:
        raise ValueError("Plano gratuito não gera cobrança.")

    cli = _dados_cliente_cobranca(cur, id_tenant)
    ref = referencia or referencia_mes()
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
                raise ValueError("Já existe fatura paga para este mês/plano.")
            fat = obter_fatura(cur, id_tenant, int(ex[0]))
            if fat:
                return fat

    from api.efi.efi import efi_disponivel

    if not efi_disponivel():
        raise RuntimeError("Efi não configurada no servidor (.env).")

    email = cli["email_cobranca"] or ""
    venc = proximo_vencimento(cli["dia_vencimento"])
    descricao = f"DropNexo — {plano['nome']} ({ref})"
    cob = _criar_cobranca_efi(
        cur,
        id_tenant=id_tenant,
        forma=forma,
        valor_centavos=int(plano["valor_centavos"]),
        descricao=descricao,
        vencimento=venc,
        nome_cliente=cli["nome_cliente"],
        documento=cli["documento"],
        email=email,
        payment_token=payment_token,
        installments=installments,
        telefone=cli.get("telefone"),
        endereco=cli.get("endereco"),
    )

    status_ini = "pago" if forma == "cartao" and cob.get("pago") else "pendente"
    cur.execute(
        """
        INSERT INTO tbl_fatura (
            id_tenant, referencia, valor_centavos, status, forma_pagamento, plano_slug,
            efi_charge_id, efi_txid, link_boleto, codigo_barras, pix_copia_cola, pix_qrcode,
            link_pagamento, vencimento_em, pago_em, atualizado_em
        ) VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
            CASE WHEN %s = 'pago' THEN NOW() ELSE NULL END, NOW()
        ) RETURNING id
        """,
        (
            id_tenant,
            ref,
            int(plano["valor_centavos"]),
            status_ini,
            forma,
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
        response_resumo={"id_fatura": fid, "status": status_ini},
    )

    if status_ini == "pago":
        aplicar_pagamento_fatura(cur, fid, origem="cartao_imediato")
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
) -> dict:
    slug = (plano_slug or "").strip().lower()
    if slug not in PLANOS_PAGOS:
        raise ValueError("Selecione um plano pago válido.")
    forma = (forma or "boleto").strip().lower()
    if forma == "pix":
        raise ValueError("PIX será liberado em breve. Use boleto ou cartão.")
    cli = _dados_cliente_cobranca(cur, id_tenant)
    doc = "".join(c for c in (cli["documento"] or "") if c.isdigit())
    if len(doc) not in (11, 14):
        raise ValueError("Cadastre CPF/CNPJ da empresa em Meu perfil antes de assinar.")
    if not (cli["email_cobranca"] or "").strip():
        raise ValueError("Informe o e-mail de cobrança em Meu perfil → Forma de pagamento.")
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
    )
    return {
        "fatura": fatura,
        "message": (
            "Pagamento confirmado. Plano liberado."
            if fatura.get("status") == "pago"
            else "Fatura emitida. O plano será liberado após a confirmação do pagamento."
        ),
        "liberado": fatura.get("status") == "pago",
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
    if status_ini == "pago":
        aplicar_pagamento_fatura(cur, id_fatura, origem="cartao_imediato")
    fat2 = obter_fatura(cur, id_tenant, id_fatura)
    if fat2 and status_ini != "pago":
        _enviar_email_fatura(cur, id_tenant, fat2, tipo="emitida")
    return fat2 or {}


def aplicar_pagamento_fatura(cur, id_fatura: int, *, origem: str = "webhook") -> dict:
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

    cur.execute(
        """
        UPDATE tbl_fatura
        SET status = 'pago', pago_em = COALESCE(pago_em, NOW()), atualizado_em = NOW()
        WHERE id = %s
        """,
        (id_fatura,),
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
    if not charge_id:
        return {"ok": False, "message": "charge_id ausente."}

    novo = _mapa_status_efi_local(str(status_raw))
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
        return {"ok": False, "message": "Fatura não encontrada para charge.", "charge_id": charge_id}

    id_fatura, id_tenant, st_atual = int(row[0]), int(row[1]), row[2]
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
        return aplicar_pagamento_fatura(cur, id_fatura, origem="webhook")

    cur.execute(
        """
        UPDATE tbl_fatura SET status = %s, atualizado_em = NOW()
        WHERE id = %s AND status <> 'pago'
        """,
        (novo, id_fatura),
    )
    return {"ok": True, "status": novo, "id_fatura": id_fatura}


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
    """Marca vencidas, avisa atraso, rebaixa após 15 dias, emite renovações do dia."""
    hoje = date.today()
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

    # aviso 1x após vencimento
    cur.execute(
        f"""
        SELECT id, id_tenant FROM tbl_fatura
        WHERE status = 'vencido' AND avisado_em IS NULL
          AND vencimento_em <= %s
        """,
        (hoje,),
    )
    for fid, tid in cur.fetchall():
        fat = obter_fatura(cur, int(tid), int(fid))
        if fat:
            _enviar_email_fatura(cur, int(tid), fat, tipo="aviso")
            cur.execute("UPDATE tbl_fatura SET avisado_em = NOW() WHERE id = %s", (fid,))
            res["avisos"] += 1

    limite = hoje - timedelta(days=DIAS_GRACA_INADIMPLENCIA)
    cur.execute(
        """
        SELECT f.id, f.id_tenant, t.plano
        FROM tbl_fatura f
        JOIN tbl_tenant t ON t.id = f.id_tenant
        WHERE f.status = 'vencido'
          AND f.rebaixado_em IS NULL
          AND f.vencimento_em <= %s
          AND t.plano IS DISTINCT FROM 'starter'
        """,
        (limite,),
    )
    for fid, tid, _plano in cur.fetchall():
        rebaixar_tenant_starter(cur, int(tid), id_fatura=int(fid))
        res["rebaixados"] += 1

    # renovação: tenants pagos no dia de vencimento sem fatura do mês
    ref = referencia_mes(hoje)
    cur.execute(
        """
        SELECT tc.id_tenant, tc.dia_vencimento, tc.forma_pagamento, tc.plano_slug
        FROM tbl_tenant_cobranca tc
        JOIN tbl_tenant t ON t.id = tc.id_tenant
        JOIN tbl_plano p ON p.slug = tc.plano_slug
        WHERE t.plano IN ('professional', 'scale', 'enterprise')
          AND p.valor_centavos > 0
          AND tc.dia_vencimento = %s
        """,
        (hoje.day,),
    )
    for tid, _dia, forma, slug in cur.fetchall():
        try:
            cur.execute(
                """
                SELECT 1 FROM tbl_fatura
                WHERE id_tenant = %s AND referencia = %s AND status IN ('pendente','pago','vencido')
                LIMIT 1
                """,
                (tid, ref),
            )
            if cur.fetchone():
                continue
            emitir_fatura(cur, int(tid), plano_slug=slug, forma=forma or "boleto", referencia=ref)
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
