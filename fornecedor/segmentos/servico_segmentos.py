# fornecedor/segmentos/servico_segmentos.py — segmentos marketplace (master data)
from __future__ import annotations

import json
from typing import Any


def _meta_dict(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {}


def segmento_para_dict(row, *, selecionado: bool = False) -> dict[str, Any]:
    """Converte linha tbl_segmento (+ opcional selecionado) para API/UI."""
    meta = _meta_dict(row[6] if len(row) > 6 else None)
    return {
        "id": row[0],
        "nome": row[1],
        "slug": row[2] or "",
        "descricao": row[3] or "",
        "icone": row[4] or "layers",
        "cor": row[5] or "#021F81",
        "meta": meta,
        "exemplos_categorias": meta.get("exemplos_categorias") or [],
        "exemplos_fornecedores": meta.get("exemplos_fornecedores") or [],
        "aplicacao": meta.get("aplicacao") or "",
        "observacao": meta.get("observacao") or "",
        "selecionado": selecionado,
    }


def _row_cols_select() -> str:
    return """
        s.id, s.nome, s.slug, s.descricao, s.icone, s.cor, s.meta
    """


def listar_segmentos_plataforma(cur, id_tenant: int | None = None) -> list[dict[str, Any]]:
    if id_tenant:
        cur.execute(
            f"""
            SELECT {_row_cols_select()},
                   EXISTS (
                       SELECT 1 FROM tbl_fornecedor_segmento fs
                       WHERE fs.id_tenant = %s AND fs.id_segmento = s.id
                   )
            FROM tbl_segmento s
            WHERE s.id_tenant IS NULL AND s.ativo = TRUE
            ORDER BY s.ordem, s.nome
            """,
            (id_tenant,),
        )
        return [segmento_para_dict(r[:7], selecionado=bool(r[7])) for r in cur.fetchall()]

    cur.execute(
        f"""
        SELECT {_row_cols_select()}
        FROM tbl_segmento s
        WHERE s.id_tenant IS NULL AND s.ativo = TRUE
        ORDER BY s.ordem, s.nome
        """
    )
    return [segmento_para_dict(r) for r in cur.fetchall()]


def ids_segmentos_fornecedor(cur, id_tenant: int) -> list[int]:
    cur.execute(
        "SELECT id_segmento FROM tbl_fornecedor_segmento WHERE id_tenant = %s ORDER BY id_segmento",
        (id_tenant,),
    )
    return [int(r[0]) for r in cur.fetchall()]


def _validar_ids_segmentos(cur, ids: list[int]) -> list[int]:
    if not ids:
        return []
    cur.execute(
        """
        SELECT id FROM tbl_segmento
        WHERE id = ANY(%s) AND id_tenant IS NULL AND ativo = TRUE
        """,
        (ids,),
    )
    validos = {int(r[0]) for r in cur.fetchall()}
    return [i for i in ids if i in validos]


def salvar_segmentos_fornecedor(
    cur,
    id_tenant: int,
    ids_segmentos: list[int],
    *,
    exigir_minimo: bool = True,
) -> None:
    ids = _validar_ids_segmentos(cur, list(dict.fromkeys(int(i) for i in ids_segmentos if i)))
    if exigir_minimo and not ids:
        raise ValueError("Selecione ao menos um segmento (nicho) em que sua empresa atua.")

    cur.execute("DELETE FROM tbl_fornecedor_segmento WHERE id_tenant = %s", (id_tenant,))
    for sid in ids:
        cur.execute(
            """
            INSERT INTO tbl_fornecedor_segmento (id_tenant, id_segmento)
            VALUES (%s, %s) ON CONFLICT DO NOTHING
            """,
            (id_tenant, sid),
        )


def tenant_exige_segmentos_nichos(tipo_negocio: str | None) -> bool:
    return (tipo_negocio or "").strip().lower() in ("fornecedor", "hibrido")
