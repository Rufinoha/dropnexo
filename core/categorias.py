# core/categorias.py — árvore e combos de categorias (compartilhado)
from __future__ import annotations

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
