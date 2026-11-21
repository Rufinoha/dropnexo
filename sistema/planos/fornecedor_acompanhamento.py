# sistema/planos/fornecedor_acompanhamento.py — fase e histórico de contato
from __future__ import annotations

from typing import Any

FASES = (
    "cadastrado",
    "boas_vindas",
    "cadastrando",
    "lembrete",
    "ativo",
    "eh_vendedor",
    "sem_resposta",
    "desistiu",
)

FASE_ROTULO = {
    "cadastrado": "Cadastrado",
    "boas_vindas": "Boas-vindas",
    "cadastrando": "Cadastrando",
    "lembrete": "Lembrete",
    "ativo": "Ativo",
    "eh_vendedor": "É vendedor",
    "sem_resposta": "Sem resposta",
    "desistiu": "Desistiu",
}

CANAIS = ("whatsapp", "email", "telefone", "outro")
DIRECOES = ("enviado", "recebido")


def _tem_coluna_tenant(cur, coluna: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema IN (current_schema(), 'public')
          AND table_name = 'tbl_tenant'
          AND column_name = %s
        LIMIT 1
        """,
        (coluna,),
    )
    return bool(cur.fetchone())


def _tem_tabela_contato(cur) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema IN (current_schema(), 'public')
          AND table_name = 'tbl_fornecedor_contato'
        LIMIT 1
        """
    )
    return bool(cur.fetchone())


def fase_ok(fase: str | None) -> bool:
    if fase is None or fase == "":
        return True
    return fase in FASES


def validar_fase(fase: str | None) -> str | None:
    if fase is None or str(fase).strip() == "":
        return None
    f = str(fase).strip().lower()
    if f not in FASES:
        raise ValueError(f"Fase inválida: {fase}")
    return f


def definir_fase(
    cur,
    id_tenant: int,
    fase: str | None,
    *,
    autor: str = "",
    motivo: str | None = None,
    registrar_historico: bool = True,
) -> dict[str, Any]:
    """Atualiza fornecedor_fase. Opcionalmente grava linha no histórico."""
    if not _tem_coluna_tenant(cur, "fornecedor_fase"):
        raise ValueError("Migração de fase ainda não aplicada (sql/23).")
    fase_n = validar_fase(fase)
    tid = int(id_tenant)
    cur.execute(
        """
        UPDATE tbl_tenant
           SET fornecedor_fase = %s,
               fornecedor_fase_em = CASE
                 WHEN %s IS NULL THEN NULL
                 ELSE NOW()
               END
         WHERE id = %s
           AND tipo_negocio IN ('fornecedor', 'hibrido')
        RETURNING id, fornecedor_fase, fornecedor_fase_em
        """,
        (fase_n, fase_n, tid),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Fornecedor não encontrado.")
    if registrar_historico and _tem_tabela_contato(cur):
        resumo = (motivo or "").strip() or (
            f"Fase alterada para {FASE_ROTULO.get(fase_n or '', fase_n or '—')}."
        )
        registrar_contato(
            cur,
            tid,
            canal="outro",
            direcao="enviado",
            resumo=resumo[:500],
            fase_apos=fase_n,
            autor=autor or "Sistema",
            aplicar_fase=False,
        )
    return {
        "id": int(row[0]),
        "fase": row[1],
        "fase_em": row[2].isoformat() if row[2] else None,
    }


def registrar_contato(
    cur,
    id_tenant: int,
    *,
    canal: str,
    direcao: str,
    resumo: str,
    fase_apos: str | None = None,
    autor: str = "",
    aplicar_fase: bool = True,
) -> dict[str, Any]:
    if not _tem_tabela_contato(cur):
        raise ValueError("Migração de contato ainda não aplicada (sql/23).")
    canal_n = (canal or "").strip().lower()
    direcao_n = (direcao or "").strip().lower()
    if canal_n not in CANAIS:
        raise ValueError("Canal inválido.")
    if direcao_n not in DIRECOES:
        raise ValueError("Direção inválida.")
    texto = (resumo or "").strip()
    if not texto:
        raise ValueError("Informe um resumo do contato.")
    if len(texto) > 500:
        raise ValueError("Resumo com no máximo 500 caracteres.")
    fase_n = validar_fase(fase_apos)
    tid = int(id_tenant)
    cur.execute(
        """
        SELECT 1 FROM tbl_tenant
         WHERE id = %s AND tipo_negocio IN ('fornecedor', 'hibrido')
        """,
        (tid,),
    )
    if not cur.fetchone():
        raise ValueError("Fornecedor não encontrado.")

    if aplicar_fase and fase_n is not None and _tem_coluna_tenant(cur, "fornecedor_fase"):
        cur.execute(
            """
            UPDATE tbl_tenant
               SET fornecedor_fase = %s, fornecedor_fase_em = NOW()
             WHERE id = %s
            """,
            (fase_n, tid),
        )

    cur.execute(
        """
        INSERT INTO tbl_fornecedor_contato
          (id_tenant, canal, direcao, resumo, fase_apos, autor)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, criado_em, canal, direcao, resumo, fase_apos, autor
        """,
        (tid, canal_n, direcao_n, texto, fase_n, (autor or "").strip()[:120]),
    )
    row = cur.fetchone()
    return {
        "id": int(row[0]),
        "criado_em": row[1].isoformat() if row[1] else None,
        "canal": row[2],
        "direcao": row[3],
        "resumo": row[4],
        "fase_apos": row[5],
        "autor": row[6] or "",
    }


def listar_contatos(cur, id_tenant: int, *, limite: int = 100) -> list[dict[str, Any]]:
    if not _tem_tabela_contato(cur):
        return []
    lim = max(1, min(int(limite or 100), 500))
    cur.execute(
        """
        SELECT id, criado_em, canal, direcao, resumo, fase_apos, autor
          FROM tbl_fornecedor_contato
         WHERE id_tenant = %s
         ORDER BY criado_em DESC, id DESC
         LIMIT %s
        """,
        (int(id_tenant), lim),
    )
    out = []
    for r in cur.fetchall():
        out.append(
            {
                "id": int(r[0]),
                "criado_em": r[1].isoformat() if r[1] else None,
                "canal": r[2],
                "direcao": r[3],
                "resumo": r[4] or "",
                "fase_apos": r[5],
                "fase_apos_rotulo": FASE_ROTULO.get(r[5] or "", r[5] or ""),
                "autor": r[6] or "",
            }
        )
    return out


def ultimo_contato(cur, id_tenant: int) -> dict[str, Any] | None:
    itens = listar_contatos(cur, id_tenant, limite=1)
    return itens[0] if itens else None


def normalizar_triagem(dados: dict | None) -> dict[str, Any] | None:
    """Valida e normaliza respostas da triagem pré-cadastro."""
    if not isinstance(dados, dict):
        return None
    fabrica = str(dados.get("fabrica") or dados.get("estoque_proprio") or "").strip().lower()
    skus = str(dados.get("skus") or dados.get("qtd_skus") or "").strip().lower()
    revende = str(dados.get("revende") or dados.get("vende_revendedores") or "").strip().lower()
    mapa_sim = {"sim": "sim", "s": "sim", "true": "sim", "1": "sim"}
    mapa_nao = {"nao": "nao", "não": "nao", "n": "nao", "false": "nao", "0": "nao"}
    if fabrica in mapa_sim:
        fabrica = "sim"
    elif fabrica in mapa_nao:
        fabrica = "nao"
    else:
        fabrica = ""
    skus_norm = {
        "ate_10": "ate_10",
        "ate10": "ate_10",
        "até_10": "ate_10",
        "11_50": "11_50",
        "11-50": "11_50",
        "51_200": "51_200",
        "51-200": "51_200",
        "mais_200": "mais_200",
        "mais200": "mais_200",
        ">200": "mais_200",
    }.get(skus, "")
    if revende in mapa_sim:
        revende = "sim"
    elif revende in mapa_nao:
        revende = "nao"
    else:
        revende = ""
    if not fabrica or not skus_norm or not revende:
        return None
    if skus_norm not in ("ate_10", "11_50", "51_200", "mais_200"):
        return None
    return {
        "fabrica": fabrica,
        "skus": skus_norm,
        "revende": revende,
        "mesmo_assim_fornecedor": bool(dados.get("mesmo_assim_fornecedor")),
    }


def triagem_rotulo(triagem: dict | None) -> str:
    if not triagem:
        return ""
    skus_lbl = {
        "ate_10": "até 10",
        "11_50": "11–50",
        "51_200": "51–200",
        "mais_200": "mais de 200",
    }
    partes = [
        f"fabrica/estoque: {triagem.get('fabrica') or '—'}",
        f"SKUs: {skus_lbl.get(triagem.get('skus') or '', triagem.get('skus') or '—')}",
        f"revende: {triagem.get('revende') or '—'}",
    ]
    if triagem.get("mesmo_assim_fornecedor"):
        partes.append("insistiu fornecedor")
    return " · ".join(partes)


def salvar_triagem_e_fase_cadastro(
    cur,
    id_tenant: int,
    triagem: dict | None,
) -> None:
    """Grava triagem (se houver), define fase cadastrado e registra contato automático."""
    tid = int(id_tenant)
    tri = normalizar_triagem(triagem) if triagem else None
    if _tem_coluna_tenant(cur, "fornecedor_triagem") and tri is not None:
        import json

        cur.execute(
            "UPDATE tbl_tenant SET fornecedor_triagem = %s::jsonb WHERE id = %s",
            (json.dumps(tri, ensure_ascii=False), tid),
        )
    if _tem_tabela_contato(cur):
        registrar_contato(
            cur,
            tid,
            canal="outro",
            direcao="enviado",
            resumo="Cadastro concluído",
            fase_apos="cadastrado",
            autor="Sistema",
            aplicar_fase=True,
        )
    elif _tem_coluna_tenant(cur, "fornecedor_fase"):
        definir_fase(
            cur,
            tid,
            "cadastrado",
            autor="Sistema",
            motivo="Cadastro concluído",
            registrar_historico=False,
        )


def enriquecer_fundadores_com_acompanhamento(cur, itens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Anexa fase / último contato aos itens de listar_fundadores()."""
    if not itens:
        return itens
    tem_fase = _tem_coluna_tenant(cur, "fornecedor_fase")
    tem_contato = _tem_tabela_contato(cur)
    tem_triagem = _tem_coluna_tenant(cur, "fornecedor_triagem")
    if not tem_fase and not tem_contato and not tem_triagem:
        for it in itens:
            it.setdefault("fase", None)
            it.setdefault("fase_em", None)
            it.setdefault("fase_rotulo", "")
            it.setdefault("ultimo_contato", None)
            it.setdefault("triagem", None)
            it.setdefault("triagem_rotulo", "")
        return itens

    ids = [int(i["id"]) for i in itens if i.get("id")]
    fase_map: dict[int, tuple[str | None, Any]] = {}
    triagem_map: dict[int, Any] = {}
    if (tem_fase or tem_triagem) and ids:
        cols = ["id"]
        if tem_fase:
            cols.extend(["fornecedor_fase", "fornecedor_fase_em"])
        if tem_triagem:
            cols.append("fornecedor_triagem")
        cur.execute(
            f"SELECT {', '.join(cols)} FROM tbl_tenant WHERE id = ANY(%s)",
            (ids,),
        )
        for r in cur.fetchall():
            tid = int(r[0])
            idx = 1
            if tem_fase:
                fase_map[tid] = (r[idx], r[idx + 1])
                idx += 2
            if tem_triagem:
                triagem_map[tid] = r[idx]

    contato_map: dict[int, dict[str, Any]] = {}
    if tem_contato and ids:
        cur.execute(
            """
            SELECT DISTINCT ON (id_tenant)
                   id_tenant, id, criado_em, canal, direcao, resumo, fase_apos, autor
              FROM tbl_fornecedor_contato
             WHERE id_tenant = ANY(%s)
             ORDER BY id_tenant, criado_em DESC, id DESC
            """,
            (ids,),
        )
        for r in cur.fetchall():
            contato_map[int(r[0])] = {
                "id": int(r[1]),
                "criado_em": r[2].isoformat() if r[2] else None,
                "canal": r[3],
                "direcao": r[4],
                "resumo": r[5] or "",
                "fase_apos": r[6],
                "autor": r[7] or "",
            }

    for it in itens:
        tid = int(it["id"])
        fase, fase_em = fase_map.get(tid, (None, None))
        it["fase"] = fase
        it["fase_em"] = fase_em.isoformat() if fase_em else None
        it["fase_rotulo"] = FASE_ROTULO.get(fase or "", "") if fase else ""
        it["ultimo_contato"] = contato_map.get(tid)
        raw_tri = triagem_map.get(tid)
        if isinstance(raw_tri, dict):
            it["triagem"] = raw_tri
        elif raw_tri:
            it["triagem"] = raw_tri
        else:
            it["triagem"] = None
        it["triagem_rotulo"] = triagem_rotulo(it["triagem"] if isinstance(it["triagem"], dict) else None)
    return itens
