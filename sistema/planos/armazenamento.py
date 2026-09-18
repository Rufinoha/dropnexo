# sistema/planos/armazenamento.py — medição e cota de espaço por tenant
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sistema.planos.limites import (
    formatar_bytes,
    limites_plano_tenant,
    mensagem_limite_armazenamento,
)

# Estimativa de dados em tabela (bytes por registro) — transparente na UI.
_EST_PRODUTO = 2048
_EST_VARIANTE = 1024
_EST_PEDIDO = 4096
_EST_PEDIDO_ITEM = 1024
_EST_ESTOQUE = 512


def _raiz() -> Path:
    return Path(__file__).resolve().parents[2]


def _bytes_pasta(pasta: Path) -> int:
    if not pasta.is_dir():
        return 0
    total = 0
    try:
        for root, _dirs, files in os.walk(pasta):
            for nome in files:
                try:
                    total += (Path(root) / nome).stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _bytes_imagens_produtos(cur, id_tenant: int) -> int:
    try:
        from fornecedor.catalogo.catalogo import obter_bytes_imagens_tenant

        return int(obter_bytes_imagens_tenant(cur, int(id_tenant)) or 0)
    except Exception:
        return 0


def _bytes_anexos_pedidos(cur, id_tenant: int) -> int:
    tid = int(id_tenant)
    cur.execute(
        """
        SELECT COALESCE(SUM(a.tamanho_bytes), 0)::bigint
        FROM tbl_pedido_anexo a
        JOIN tbl_pedido p ON p.id = a.id_pedido
        WHERE p.id_tenant_vendedor = %s OR p.id_tenant_fornecedor = %s
        """,
        (tid, tid),
    )
    row = cur.fetchone()
    return int(row[0] or 0)


def _bytes_upload_tenant_exceto_pedidos(id_tenant: int) -> tuple[int, int]:
    """Retorna (logos_e_marca, outros) sob upload/tenant{N}/."""
    base = _raiz() / "upload" / f"tenant{int(id_tenant)}"
    if not base.is_dir():
        return 0, 0
    logos = 0
    outros = 0
    pedidos = base / "pedidos"
    try:
        for root, _dirs, files in os.walk(base):
            root_p = Path(root)
            # Anexos de pedido já entram por tbl_pedido_anexo
            try:
                root_p.relative_to(pedidos)
                continue
            except ValueError:
                pass
            for nome in files:
                fp = root_p / nome
                try:
                    sz = fp.stat().st_size
                except OSError:
                    continue
                low = nome.lower()
                if "logo" in low or "marca" in low or "favicon" in low:
                    logos += sz
                else:
                    outros += sz
    except OSError:
        pass
    return logos, outros


def _bytes_fotos_usuarios(cur, id_tenant: int) -> int:
    cur.execute(
        """
        SELECT u.id
        FROM tbl_usuario_tenant ut
        JOIN tbl_usuario u ON u.id = ut.id_usuario
        WHERE ut.id_tenant = %s
        """,
        (int(id_tenant),),
    )
    total = 0
    base = _raiz() / "static" / "imge" / "imguser"
    for (uid,) in cur.fetchall():
        total += _bytes_pasta(base / str(uid))
    return total


def _estimativa_dados(cur, id_tenant: int) -> int:
    tid = int(id_tenant)
    cur.execute("SELECT COUNT(*)::int FROM tbl_produto WHERE id_tenant = %s", (tid,))
    n_prod = int(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT COUNT(*)::int
        FROM tbl_produto_variante v
        JOIN tbl_produto p ON p.id = v.id_produto
        WHERE p.id_tenant = %s
        """,
        (tid,),
    )
    n_var = int(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT COUNT(*)::int FROM tbl_pedido
        WHERE id_tenant_vendedor = %s OR id_tenant_fornecedor = %s
        """,
        (tid, tid),
    )
    n_ped = int(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT COUNT(*)::int
        FROM tbl_pedido_item i
        JOIN tbl_pedido p ON p.id = i.id_pedido
        WHERE p.id_tenant_vendedor = %s OR p.id_tenant_fornecedor = %s
        """,
        (tid, tid),
    )
    n_item = int(cur.fetchone()[0] or 0)

    n_est = 0
    try:
        cur.execute(
            """
            SELECT COUNT(*)::int
            FROM tbl_produto_estoque_deposito e
            JOIN tbl_produto_variante v ON v.id = e.id_variante
            JOIN tbl_produto p ON p.id = v.id_produto
            WHERE p.id_tenant = %s
            """,
            (tid,),
        )
        n_est = int(cur.fetchone()[0] or 0)
    except Exception:
        try:
            cur.connection.rollback()
        except Exception:
            pass

    return (
        n_prod * _EST_PRODUTO
        + n_var * _EST_VARIANTE
        + n_ped * _EST_PEDIDO
        + n_item * _EST_PEDIDO_ITEM
        + n_est * _EST_ESTOQUE
    )


def medir_armazenamento_tenant(cur, id_tenant: int) -> dict[str, Any]:
    """Detalha uso de espaço (arquivos + estimativa de dados)."""
    tid = int(id_tenant)
    imagens = _bytes_imagens_produtos(cur, tid)
    anexos = _bytes_anexos_pedidos(cur, tid)
    logos_upload, outros_upload = _bytes_upload_tenant_exceto_pedidos(tid)
    fotos = _bytes_fotos_usuarios(cur, tid)
    logos = logos_upload + fotos
    dados = _estimativa_dados(cur, tid)

    itens = [
        {
            "codigo": "imagens_produtos",
            "rotulo": "Imagens de produtos",
            "bytes": imagens,
            "hint": "Arquivos em disco (catálogo)",
        },
        {
            "codigo": "anexos_pedidos",
            "rotulo": "Anexos de pedidos",
            "bytes": anexos,
            "hint": "NF, etiquetas, comprovantes",
        },
        {
            "codigo": "logos_marca",
            "rotulo": "Logos e fotos de perfil",
            "bytes": logos,
            "hint": "Marca da conta e avatares",
        },
        {
            "codigo": "outros_arquivos",
            "rotulo": "Outros arquivos",
            "bytes": outros_upload,
            "hint": "Uploads diversos do tenant",
        },
        {
            "codigo": "dados_sistema",
            "rotulo": "Dados do sistema (estimativa)",
            "bytes": dados,
            "hint": "Produtos, pedidos, estoque etc.",
        },
    ]
    for it in itens:
        it["rotulo_bytes"] = formatar_bytes(it["bytes"])

    total = sum(int(i["bytes"]) for i in itens)
    return {
        "itens": itens,
        "bytes_total": total,
        "rotulo_total": formatar_bytes(total),
    }


def _papel_ou_padrao(papel: str | None) -> str | None:
    if papel is None:
        return None
    tipo = str(papel).strip().lower()
    if tipo in ("vendedor", "fornecedor"):
        return tipo
    return None


def _limite_armazenamento_efetivo(cur, id_tenant: int, papel: str | None = None) -> int | None:
    """Cota do papel pedido; se omitido, usa o maior limite dos papéis do tenant."""
    p = _papel_ou_padrao(papel)
    if p:
        lim = limites_plano_tenant(cur, int(id_tenant), p).get("armazenamento_bytes")
        return int(lim) if lim is not None else None

    cur.execute("SELECT tipo_negocio FROM tbl_tenant WHERE id = %s", (int(id_tenant),))
    row = cur.fetchone()
    tipo = ((row[0] if row else None) or "vendedor").strip().lower()
    papeis: list[str] = []
    if tipo in ("vendedor", "hibrido"):
        papeis.append("vendedor")
    if tipo in ("fornecedor", "hibrido"):
        papeis.append("fornecedor")
    if not papeis:
        papeis = ["vendedor"]

    valores: list[int] = []
    for papel_i in papeis:
        lim = limites_plano_tenant(cur, int(id_tenant), papel_i).get("armazenamento_bytes")
        if lim is None:
            return None
        valores.append(int(lim))
    return max(valores) if valores else None


def uso_armazenamento_vs_plano(cur, id_tenant: int, papel: str | None = None) -> dict[str, Any]:
    med = medir_armazenamento_tenant(cur, id_tenant)
    tipo = _papel_ou_padrao(papel) or "vendedor"
    lim = limites_plano_tenant(cur, int(id_tenant), tipo)
    limite = lim.get("armazenamento_bytes")
    usado = int(med["bytes_total"] or 0)
    lim_i = int(limite) if limite is not None else None
    pct = 0
    if lim_i and lim_i > 0:
        pct = min(100, int((usado * 100) // lim_i))
    return {
        **med,
        "limite_bytes": lim_i,
        "rotulo_limite": formatar_bytes(lim_i) if lim_i is not None else "Ilimitado",
        "usado_bytes": usado,
        "percentual": pct,
        "esgotado": lim_i is not None and usado >= lim_i,
        "aviso": lim_i is not None and pct >= 80,
    }


def verificar_capacidade_armazenamento(
    cur,
    id_tenant: int,
    *,
    bytes_novos: int,
    papel: str | None = None,
) -> tuple[bool, str]:
    """Retorna (ok, mensagem). bytes_novos = tamanho a gravar."""
    extra = max(0, int(bytes_novos or 0))
    lim = _limite_armazenamento_efetivo(cur, int(id_tenant), papel)
    if lim is None:
        return True, ""
    med = medir_armazenamento_tenant(cur, int(id_tenant))
    usado = int(med.get("bytes_total") or 0)
    if usado + extra > int(lim):
        return False, mensagem_limite_armazenamento(limite=int(lim), usado=usado)
    return True, ""


def exigir_capacidade_armazenamento(
    cur,
    id_tenant: int,
    *,
    bytes_novos: int,
    papel: str | None = None,
) -> None:
    ok, msg = verificar_capacidade_armazenamento(
        cur, id_tenant, bytes_novos=bytes_novos, papel=papel
    )
    if not ok:
        raise ValueError(msg)
