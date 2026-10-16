# api/mercado_livre/ressalvas.py — avisos de anúncio criado/atualizado com um pedaço de fora
from __future__ import annotations

from global_utils import agora_utc

_PROVEDOR = "mercado_livre"


def garantir_tabela_ressalva(cur) -> None:
    """Cria a tabela só se ela ainda não existe.

    Em produção o dono é o postgres, que rodou o SQL. O usuário da aplicação
    não pode executar CREATE INDEX nessa tabela, mesmo com o índice já criado.
    """
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_name = 'tbl_produto_vendedor_ressalva'
        """
    )
    if cur.fetchone():
        return
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_produto_vendedor_ressalva (
            id BIGSERIAL PRIMARY KEY,
            id_tenant_vendedor INTEGER NOT NULL,
            id_produto INTEGER NOT NULL,
            id_variante INTEGER NOT NULL DEFAULT 0,
            provedor VARCHAR(40) NOT NULL DEFAULT 'mercado_livre',
            codigo VARCHAR(60) NOT NULL,
            mensagem TEXT NOT NULL,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_produto_vendedor_ressalva
                UNIQUE (id_tenant_vendedor, id_produto, id_variante, provedor, codigo)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pvr_tenant_produto
            ON tbl_produto_vendedor_ressalva (id_tenant_vendedor, id_produto)
        """
    )


def aplicar_ressalvas_ml(
    cur,
    id_tenant: int,
    id_produto: int,
    id_variantes: list[int],
    novas: list[dict],
    resolvidas: set[str],
) -> None:
    """Grava o que ficou de fora e apaga o que esta integração conseguiu enviar."""
    garantir_tabela_ressalva(cur)
    vids: list[int] = []
    for bruto in id_variantes:
        try:
            vid = int(bruto)
        except (TypeError, ValueError):
            continue
        if vid > 0 and vid not in vids:
            vids.append(vid)
    if not vids:
        return

    itens: list[tuple[str, str]] = []
    cod_novas: list[str] = []
    for item in novas:
        cod = str((item or {}).get("codigo") or "").strip()
        msg = str((item or {}).get("mensagem") or "").strip()
        if not cod or not msg or cod in cod_novas:
            continue
        cod_novas.append(cod)
        itens.append((cod, msg))

    limpar = [c for c in resolvidas if c and c not in cod_novas]
    if limpar:
        cur.execute(
            """
            DELETE FROM tbl_produto_vendedor_ressalva
            WHERE id_tenant_vendedor = %s AND id_produto = %s
              AND id_variante = ANY(%s) AND provedor = %s
              AND codigo = ANY(%s)
            """,
            (int(id_tenant), int(id_produto), vids, _PROVEDOR, limpar),
        )

    agora = agora_utc()
    for vid in vids:
        for cod, msg in itens:
            cur.execute(
                """
                INSERT INTO tbl_produto_vendedor_ressalva (
                    id_tenant_vendedor, id_produto, id_variante, provedor,
                    codigo, mensagem, atualizado_em
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id_tenant_vendedor, id_produto, id_variante, provedor, codigo)
                DO UPDATE SET
                    mensagem = EXCLUDED.mensagem,
                    atualizado_em = EXCLUDED.atualizado_em
                """,
                (int(id_tenant), int(id_produto), vid, _PROVEDOR, cod, msg, agora),
            )


def anexar_ressalvas_linhas(cur, id_tenant: int, linhas: list[dict]) -> None:
    """Coloca ressalvas em cada linha da lista de Meus produtos."""
    if not linhas:
        return
    garantir_tabela_ressalva(cur)
    ids: list[int] = []
    for linha in linhas:
        if linha.get("tipo") == "kit":
            linha["ressalvas"] = []
            continue
        if linha.get("tipo") == "variante":
            pid = linha.get("id_produto")
        else:
            pid = linha.get("id")
        try:
            pid_i = int(pid or 0)
        except (TypeError, ValueError):
            pid_i = 0
        if pid_i > 0 and pid_i not in ids:
            ids.append(pid_i)
    por_prod: dict[int, list[dict]] = {}
    por_var: dict[tuple[int, int], list[dict]] = {}
    if ids:
        cur.execute(
            """
            SELECT id_produto, id_variante, codigo, mensagem
            FROM tbl_produto_vendedor_ressalva
            WHERE id_tenant_vendedor = %s AND provedor = %s
              AND id_produto = ANY(%s)
            ORDER BY id_produto, id_variante, codigo
            """,
            (int(id_tenant), _PROVEDOR, ids),
        )
        for pid, vid, cod, msg in cur.fetchall():
            item = {"codigo": cod or "", "mensagem": msg or ""}
            por_prod.setdefault(int(pid), []).append(item)
            por_var.setdefault((int(pid), int(vid)), []).append(item)

    for linha in linhas:
        if linha.get("tipo") == "kit":
            continue
        if linha.get("tipo") == "variante":
            try:
                chave = (int(linha.get("id_produto") or 0), int(linha.get("id") or 0))
            except (TypeError, ValueError):
                chave = (0, 0)
            linha["ressalvas"] = por_var.get(chave, [])
            continue
        try:
            pid_i = int(linha.get("id") or 0)
        except (TypeError, ValueError):
            pid_i = 0
        vistos: list[dict] = []
        ja: set[str] = set()
        for item in por_prod.get(pid_i, []):
            texto = item.get("mensagem") or ""
            if not texto or texto in ja:
                continue
            ja.add(texto)
            vistos.append(item)
        linha["ressalvas"] = vistos
