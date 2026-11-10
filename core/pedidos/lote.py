"""Ações em lote de pedidos (fornecedor / armazém)."""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

from core.pedidos.servico import (
    MSG_ETIQUETA_SEM_PAGAMENTO,
    listar_anexos_pedido,
    marcar_em_expedicao,
    marcar_entregue,
    obter_pedido,
    pedido_pago_pelo_vendedor,
)


def _ids_limpos(raw: Any) -> list[int]:
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[int] = []
    seen: set[int] = set()
    for x in raw:
        try:
            i = int(x)
        except (TypeError, ValueError):
            continue
        if i > 0 and i not in seen:
            seen.add(i)
            out.append(i)
    return out[:100]


def lote_expedir(
    cur,
    ids: list[int],
    *,
    id_fornecedor: int,
    id_usuario: int | None = None,
    exigir_fiscal: bool = True,
) -> dict[str, Any]:
    ok: list[int] = []
    erros: list[dict[str, Any]] = []
    for id_pedido in ids:
        try:
            marcar_em_expedicao(
                cur,
                id_pedido,
                id_fornecedor=id_fornecedor,
                id_usuario=id_usuario,
                exigir_fiscal=exigir_fiscal,
            )
            ok.append(id_pedido)
        except ValueError as e:
            erros.append({"id": id_pedido, "message": str(e)})
    return {"ok": ok, "erros": erros, "qtd_ok": len(ok), "qtd_erro": len(erros)}


def lote_entregue(
    cur,
    ids: list[int],
    *,
    id_fornecedor: int,
    id_usuario: int | None = None,
) -> dict[str, Any]:
    ok: list[int] = []
    erros: list[dict[str, Any]] = []
    for id_pedido in ids:
        try:
            marcar_entregue(
                cur,
                id_pedido,
                id_fornecedor=id_fornecedor,
                id_usuario=id_usuario,
            )
            ok.append(id_pedido)
        except ValueError as e:
            erros.append({"id": id_pedido, "message": str(e)})
    return {"ok": ok, "erros": erros, "qtd_ok": len(ok), "qtd_erro": len(erros)}


def _tipos_pdf(modo: str) -> set[str]:
    m = (modo or "etiquetas").strip().lower()
    if m in ("etiquetas_nf", "etiquetas+nf", "completo", "docs"):
        return {"etiqueta", "nf", "declaracao"}
    return {"etiqueta"}


def montar_pdf_lote(
    cur,
    ids: list[int],
    *,
    id_fornecedor: int,
    raiz: Path,
    modo: str = "etiquetas",
) -> tuple[bytes, str, list[dict[str, Any]], list[int]]:
    """Mescla anexos PDF dos pedidos.

    Retorna (bytes, filename, avisos, ids_com_etiqueta) — ids em que a
    etiqueta entrou no PDF (candidatos a marcar em expedição).
    """
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError as e:
        raise ValueError(
            "Biblioteca pypdf não instalada. Rode: pip install pypdf"
        ) from e

    tipos = _tipos_pdf(modo)
    writer = PdfWriter()
    avisos: list[dict[str, Any]] = []
    ids_com_etiqueta: list[int] = []
    paginas = 0

    for id_pedido in ids:
        ped = obter_pedido(cur, id_pedido, id_fornecedor=id_fornecedor)
        if not ped:
            avisos.append({"id": id_pedido, "message": "Pedido não encontrado."})
            continue
        numero = ped.get("numero") or str(id_pedido)
        if not pedido_pago_pelo_vendedor(ped):
            avisos.append(
                {
                    "id": id_pedido,
                    "message": f"Pedido {numero}: {MSG_ETIQUETA_SEM_PAGAMENTO}",
                }
            )
            continue
        anexos = listar_anexos_pedido(cur, id_pedido, id_fornecedor=id_fornecedor)
        # Ordem: etiqueta → NF/declaração
        escolhidos: list[dict] = []
        tem_etiqueta_pdf = False
        if "etiqueta" in tipos:
            etq = next((a for a in anexos if (a.get("tipo") or "") == "etiqueta"), None)
            if etq:
                escolhidos.append(etq)
            else:
                avisos.append({"id": id_pedido, "message": "Sem etiqueta."})
        if tipos & {"nf", "declaracao"}:
            fiscal = next(
                (a for a in anexos if (a.get("tipo") or "") in ("nf", "declaracao")),
                None,
            )
            if fiscal:
                escolhidos.append(fiscal)
            else:
                avisos.append({"id": id_pedido, "message": "Sem NF/declaração."})
        for an in escolhidos:
            caminho = (an.get("caminho") or "").strip().replace("\\", "/")
            if not caminho or ".." in caminho.split("/"):
                avisos.append({"id": id_pedido, "message": f"Caminho inválido ({numero})."})
                continue
            if not caminho.lower().startswith("upload/tenant"):
                avisos.append({"id": id_pedido, "message": f"Arquivo não permitido ({numero})."})
                continue
            arquivo = raiz / caminho.replace("/", os.sep)
            if not arquivo.is_file():
                avisos.append({"id": id_pedido, "message": f"Arquivo ausente ({numero})."})
                continue
            if arquivo.suffix.lower() != ".pdf":
                avisos.append(
                    {
                        "id": id_pedido,
                        "message": f"Anexo não é PDF ({an.get('tipo')}, {numero}).",
                    }
                )
                continue
            try:
                reader = PdfReader(str(arquivo))
                pages_before = paginas
                for page in reader.pages:
                    writer.add_page(page)
                    paginas += 1
                if (an.get("tipo") or "") == "etiqueta" and paginas > pages_before:
                    tem_etiqueta_pdf = True
            except Exception:
                avisos.append({"id": id_pedido, "message": f"Falha ao ler PDF ({numero})."})
        if tem_etiqueta_pdf and id_pedido not in ids_com_etiqueta:
            ids_com_etiqueta.append(id_pedido)

    if paginas <= 0:
        if avisos and all("ainda não pagou" in (a.get("message") or "") for a in avisos):
            raise ValueError(MSG_ETIQUETA_SEM_PAGAMENTO)
        raise ValueError("Nenhum PDF encontrado nos pedidos selecionados.")

    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    nome = "etiquetas.pdf" if tipos == {"etiqueta"} else "etiquetas_e_notas.pdf"
    return buf.getvalue(), nome, avisos, ids_com_etiqueta


def mensagem_expedicao_lote(res: dict[str, Any]) -> str:
    """Texto curto para UI após gerar etiqueta / expedir em lote."""
    qtd_ok = int(res.get("qtd_ok") or 0)
    qtd_erro = int(res.get("qtd_erro") or 0)
    if qtd_ok and not qtd_erro:
        return f"{qtd_ok} pedido(s) marcado(s) em expedição."
    if qtd_ok and qtd_erro:
        msgs = "; ".join(
            f"#{e.get('id')}: {e.get('message')}" for e in (res.get("erros") or [])[:5]
        )
        extra = f" {msgs}" if msgs else ""
        return f"{qtd_ok} em expedição; {qtd_erro} sem alteração.{extra}"
    if qtd_erro:
        msgs = "; ".join(
            f"#{e.get('id')}: {e.get('message')}" for e in (res.get("erros") or [])[:5]
        )
        return msgs or "Nenhum pedido pôde ser marcado em expedição."
    return "Nenhum pedido para marcar em expedição."


def parse_ids_body(body: dict | None) -> list[int]:
    body = body or {}
    return _ids_limpos(body.get("ids") or body.get("pedidos") or [])
