# core/pedidos/erp_export.py — envia o pedido ao ERP gravado no produto
from __future__ import annotations

import html
import logging

_log = logging.getLogger(__name__)

DEV_EMAIL_ERP = "hazael@h74.com.br"

_STATUS_ENVIO = frozenset(
    {
        "aguardando_confirmacao",
        "pago",
        "em_expedicao",
        "entregue",
    }
)


def garantir_colunas_export_erp(cur) -> None:
    from core.pedidos.servico import _pedido_colunas

    cols = _pedido_colunas(cur)
    if "erp_export_pendente" in cols and "erp_export_erro" in cols:
        return
    cur.execute(
        """
        ALTER TABLE tbl_pedido
          ADD COLUMN IF NOT EXISTS erp_export_pendente BOOLEAN NOT NULL DEFAULT FALSE,
          ADD COLUMN IF NOT EXISTS erp_export_erro TEXT
        """
    )
    import core.pedidos.servico as servico

    servico._PEDIDO_COL_CACHE = None


def _vinculos_itens(cur, id_fornecedor: int, itens: list[dict]) -> tuple[list[str], set[str]]:
    faltando: list[str] = []
    provedores: set[str] = set()
    for item in itens:
        id_prod = item.get("id_produto")
        sku = (item.get("sku") or "").strip() or "?"
        if not id_prod:
            faltando.append(sku)
            continue
        cur.execute(
            """
            SELECT provedor FROM tbl_integracao_map
            WHERE id_tenant = %s AND contexto = 'fornecedor' AND entidade = 'produto'
              AND id_dropnexo = %s AND COALESCE(TRIM(id_bling), '') <> ''
            LIMIT 1
            """,
            (int(id_fornecedor), int(id_prod)),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            faltando.append(sku)
            continue
        provedores.add(str(row[0]).strip().lower())
    return faltando, provedores


def _marcar_pendente(cur, id_pedido: int, erro: str) -> None:
    garantir_colunas_export_erp(cur)
    from global_utils import agora_utc

    cur.execute(
        """
        UPDATE tbl_pedido SET
            erp_export_pendente = TRUE,
            erp_export_erro = %s,
            atualizado_em = %s
        WHERE id = %s
        """,
        (erro[:2000], agora_utc(), int(id_pedido)),
    )


def _limpar_pendente(cur, id_pedido: int) -> None:
    garantir_colunas_export_erp(cur)
    from global_utils import agora_utc

    cur.execute(
        """
        UPDATE tbl_pedido SET
            erp_export_pendente = FALSE,
            erp_export_erro = NULL,
            atualizado_em = %s
        WHERE id = %s
        """,
        (agora_utc(), int(id_pedido)),
    )


def _email_dev(numero: str, id_pedido: int, id_fornecedor: int, erro: str) -> None:
    from api.brevo.srotas_brevo import enviar_email

    corpo = (
        "<p>Falha ao criar o pedido no ERP do fornecedor.</p>"
        f"<p>Pedido <strong>{html.escape(numero)}</strong> "
        f"(id {int(id_pedido)}), fornecedor {int(id_fornecedor)}.</p>"
        "<pre style=\"white-space:pre-wrap;font-family:Consolas,monospace;\">"
        f"{html.escape(erro)}"
        "</pre>"
    )
    enviar_email(
        [DEV_EMAIL_ERP],
        f"DropNexo — falha ao exportar pedido {numero}",
        corpo,
        tag="dropnexo_erp_pedido",
    )


def pedido_export_pendente(cur, id_pedido: int) -> bool:
    garantir_colunas_export_erp(cur)
    cur.execute(
        "SELECT COALESCE(erp_export_pendente, FALSE) FROM tbl_pedido WHERE id = %s",
        (int(id_pedido),),
    )
    row = cur.fetchone()
    return bool(row and row[0])


def exportar_pedido_para_erp_do_produto(cur, id_pedido: int) -> str:
    """Cria o pedido no ERP do produto.

    Retorna: ok | ja | somente_dropnexo | pendente.
    Sem vínculo, o pedido fica só no DropNexo. Erro de API marca pendente e avisa o dev.
    """
    from api.bling.pedidos import (
        _pedido_ja_exportado,
        _registrar_log,
        exportar_pedido_fornecedor_bling,
    )
    from core.pedidos.servico import listar_itens_pedido, obter_pedido

    ped = obter_pedido(cur, int(id_pedido))
    if not ped:
        return "somente_dropnexo"
    id_forn = int(ped["id_tenant_fornecedor"])
    numero = str(ped.get("numero") or id_pedido)
    if _pedido_ja_exportado(cur, id_forn, int(id_pedido)):
        _limpar_pendente(cur, int(id_pedido))
        return "ja"

    itens = listar_itens_pedido(cur, int(id_pedido))
    faltando, provedores = _vinculos_itens(cur, id_forn, itens)
    if faltando or provedores != {"bling"}:
        _limpar_pendente(cur, int(id_pedido))
        return "somente_dropnexo"

    try:
        res = exportar_pedido_fornecedor_bling(cur, int(id_pedido), por_produto=True)
    except Exception as e:
        from api.bling.cliente import detalhe_excecao_bling, resumo_diagnostico_bling

        try:
            conta = resumo_diagnostico_bling(cur, id_forn)
        except Exception:
            conta = "Conta Bling: não foi possível ler o diagnóstico."
        erro_curto = str(e)[:500]
        erro_email = f"{detalhe_excecao_bling(e)}\n\n{conta}"[:1800]
        _marcar_pendente(cur, int(id_pedido), erro_curto)
        try:
            _registrar_log(cur, id_forn, "fornecedor", "aviso", f"Pedido #{numero}", erro_curto)
        except Exception:
            _log.warning("log export erp pedido %s", id_pedido)
        try:
            _email_dev(numero, int(id_pedido), id_forn, erro_email)
        except Exception:
            _log.warning("e-mail export erp pedido %s", id_pedido)
        return "pendente"

    if res.get("exportados"):
        _limpar_pendente(cur, int(id_pedido))
        return "ok"
    _limpar_pendente(cur, int(id_pedido))
    return "ja"


def retentar_exportacao_se_pendente(cur, id_pedido: int) -> None:
    if not pedido_export_pendente(cur, int(id_pedido)):
        return
    exportar_pedido_para_erp_do_produto(cur, int(id_pedido))
