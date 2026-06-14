#!/usr/bin/env python3
"""Gera SQL de sync tbl_menu do banco DEV (via .env)."""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from global_utils import Var_ConectarBanco


def esc(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        return str(v)
    s = str(v).replace("'", "''")
    return f"'{s}'"


def main() -> None:
    conn = Var_ConectarBanco()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.id, m.nome_menu, m.descricao, m.data_page, m.icone, m.tipo_abrir, m.ordem,
               m.parent_id, p.nav_codigo AS parent_nav, m.pai, m.status, m.obs, m.id_modulo,
               mm.modulo AS modulo_nome, m.nav_codigo, m.contexto_modulo
        FROM tbl_menu m
        LEFT JOIN tbl_menu p ON p.id = m.parent_id
        LEFT JOIN tbl_menu_modulo mm ON mm.id = m.id_modulo
        ORDER BY m.pai DESC, m.ordem NULLS LAST, m.id
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    print("-- DropNexo — sync tbl_menu DEV -> PROD")
    print(f"-- Registros: {len(rows)}")
    print("-- Requer tbl_menu_modulo já existente (003_menu_sistema.sql)")
    print()
    print("BEGIN;")
    print()

    for r in rows:
        (
            id_,
            nome,
            desc,
            page,
            ico,
            tipo,
            ordem,
            _parent_id,
            parent_nav,
            pai,
            status,
            obs,
            _id_mod,
            mod_nome,
            nav,
            ctx,
        ) = r
        mod_sql = esc(mod_nome) if mod_nome else "NULL"
        parent_sql = (
            f"(SELECT id FROM tbl_menu WHERE nav_codigo = {esc(parent_nav)} LIMIT 1)"
            if parent_nav
            else "NULL"
        )
        ordem_sql = esc(ordem) if ordem is not None else "NULL"

        print(f"-- dev id={id_} | nav_codigo={nav}")
        print(
            f"""INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT {esc(nome)}, {esc(desc)}, {esc(page)}, {esc(ico)}, {esc(tipo)}, {ordem_sql},
       {parent_sql},
       {esc(pai)}, {esc(status)}, {esc(obs)},
       (SELECT id FROM tbl_menu_modulo WHERE modulo = {mod_sql} LIMIT 1),
       {esc(nav)}, {esc(ctx)}
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = {esc(nav)});"""
        )
        print(
            f"""UPDATE tbl_menu SET
    nome_menu = {esc(nome)},
    descricao = {esc(desc)},
    data_page = {esc(page)},
    icone = {esc(ico)},
    tipo_abrir = {esc(tipo)},
    ordem = {ordem_sql},
    parent_id = {parent_sql},
    pai = {esc(pai)},
    status = {esc(status)},
    obs = {esc(obs)},
    id_modulo = (SELECT id FROM tbl_menu_modulo WHERE modulo = {mod_sql} LIMIT 1),
    contexto_modulo = {esc(ctx)}
WHERE nav_codigo = {esc(nav)};"""
        )
        print()

    print("COMMIT;")


if __name__ == "__main__":
    main()
