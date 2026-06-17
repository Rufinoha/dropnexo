#!/usr/bin/env python3
"""
Cria o banco bd_dropnexo, aplica schema, seeds RBAC e usuário DEV.

Uso (na raiz do projeto):
  python scripts/bootstrap_db.py

Variáveis (.env):
  DB_*_DEV, DEV_SEED_EMAIL, DEV_SEED_SENHA, DEV_SEED_NOME
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import bcrypt
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def _cfg():
    user = os.getenv("DB_USER_DEV", "postgres")
    pwd = os.getenv("DB_PASSWORD_DEV", "")
    host = os.getenv("DB_HOST_DEV", "127.0.0.1")
    port = os.getenv("DB_PORT_DEV", "5432")
    dbname = os.getenv("DB_NAME_DEV", "bd_dropnexo")
    return user, pwd, host, port, dbname


def _connect(dbname: str):
    user, pwd, host, port, _ = _cfg()
    return psycopg2.connect(
        dbname=dbname,
        user=user,
        password=pwd,
        host=host,
        port=port,
    )


def criar_banco():
    _, _, _, _, target = _cfg()
    conn = _connect("postgres")
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target,))
    if cur.fetchone():
        print(f"Banco '{target}' já existe.")
    else:
        cur.execute(f'CREATE DATABASE "{target}" ENCODING \'UTF8\' TEMPLATE template0')
        print(f"Banco '{target}' criado.")
    cur.close()
    conn.close()


def executar_sql_arquivo(conn, path: Path):
    sql = path.read_text(encoding="utf-8")
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()
    cur.close()
    print(f"OK: {path.name}")


def seed_usuario_dev(conn):
    email = (os.getenv("DEV_SEED_EMAIL") or "dev@dropnexo.local").strip().lower()
    senha = os.getenv("DEV_SEED_SENHA") or "Dev@DropNexo2026"
    nome = os.getenv("DEV_SEED_NOME") or "Desenvolvedor DropNexo"
    senha_hash = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

    cur = conn.cursor()

    cur.execute("SELECT id FROM tbl_perfil WHERE codigo = 'dono' LIMIT 1")
    row_perfil = cur.fetchone()
    if not row_perfil:
        raise RuntimeError("Perfil 'dono' não encontrado. Execute 002_seed_perfis_permissoes.sql.")
    id_perfil_dono = row_perfil[0]

    cur.execute("SELECT id FROM tbl_usuario WHERE email = %s", (email,))
    row_u = cur.fetchone()

    if row_u:
        id_usuario = row_u[0]
        cur.execute(
            """
            UPDATE tbl_usuario
            SET nome = %s, senha_hash = %s, ativo = TRUE, eh_desenvolvedor = TRUE,
                token_ativacao = NULL, token_expira_em = NULL
            WHERE id = %s
            """,
            (nome, senha_hash, id_usuario),
        )
        print(f"Usuário DEV atualizado: {email} (id={id_usuario})")
    else:
        cur.execute(
            """
            INSERT INTO tbl_usuario (nome, email, whatsapp, senha_hash, ativo, eh_desenvolvedor)
            VALUES (%s, %s, NULL, %s, TRUE, TRUE)
            RETURNING id
            """,
            (nome, email, senha_hash),
        )
        id_usuario = cur.fetchone()[0]
        print(f"Usuário DEV criado: {email} (id={id_usuario})")

    cur.execute("SELECT id FROM tbl_tenant WHERE slug = 'dropnexo-dev' LIMIT 1")
    row_t = cur.fetchone()
    if row_t:
        id_tenant = row_t[0]
        cur.execute("UPDATE tbl_tenant SET ativo = TRUE WHERE id = %s", (id_tenant,))
    else:
        cur.execute(
            """
            INSERT INTO tbl_tenant (
                tipo_pessoa, tipo_negocio, documento, nome_completo, nome, slug, plano, ativo,
                cep, logradouro, numero, bairro, cidade, uf
            )
            VALUES ('J', 'hibrido', '00000000000000', 'DropNexo DEV Ltda', 'DropNexo DEV',
                    'dropnexo-dev', 'enterprise', TRUE,
                    '01310100', 'Av. Paulista', '1000', 'Bela Vista', 'São Paulo', 'SP')
            RETURNING id
            """,
        )
        id_tenant = cur.fetchone()[0]
        print(f"Tenant DEV criado (id={id_tenant})")

    cur.execute(
        """
        SELECT id FROM tbl_usuario_tenant
        WHERE id_usuario = %s AND id_tenant = %s
        """,
        (id_usuario, id_tenant),
    )
    if cur.fetchone():
        cur.execute(
            """
            UPDATE tbl_usuario_tenant
            SET id_perfil = %s, ativo = TRUE
            WHERE id_usuario = %s AND id_tenant = %s
            """,
            (id_perfil_dono, id_usuario, id_tenant),
        )
    else:
        cur.execute(
            """
            INSERT INTO tbl_usuario_tenant (id_usuario, id_tenant, id_perfil, ativo)
            VALUES (%s, %s, %s, TRUE)
            """,
            (id_usuario, id_tenant, id_perfil_dono),
        )

    conn.commit()
    cur.close()
    print(f"Login DEV: {email} / senha definida em DEV_SEED_SENHA (.env)")
    print("eh_desenvolvedor=TRUE: acesso 100% (bypass RBAC).")


def main():
    sql_dir = ROOT / "__doc" / "sql"
    criar_banco()
    conn = _connect(_cfg()[4])
    try:
        for nome in (
            "001_schema_inicial.sql",
            "002_seed_perfis_permissoes.sql",
            "003_menu_sistema.sql",
            "004_config_complemento.sql",
            "005_mvp_catalogo.sql",
            "006_seed_fornecedor_demo.sql",
            "007_mvp_produtos_favorito.sql",
            "008_catalogo_completo.sql",
            "009_kit_vendedor.sql",
            "010_fornecedor_deposito_regras.sql",
            "011_v2_arquitetura.sql",
            "012_segmento_plataforma.sql",
            "013_categoria_arvore.sql",
            "014_produto_variacao_campos.sql",
            "015_variacao_preset.sql",
            "016_fn_usuarios.sql",
            "017_fn_integracoes.sql",
            "018_vendedor_usuarios_integracoes.sql",
            "019_dashboard_label.sql",
            "019_tenant_empresa_completo.sql",
            "020_planos_cobranca_faturas.sql",
            "021_integracao_bling.sql",
            "023_integracao_bling_categoria_map.sql",
            "024_segmentos_marketplace.sql",
            "025_segmentos_textos_utf8.sql",
            "026_remover_menu_segmentos.sql",
            "027_importacao_lote.sql",
            "028_ocultar_menu_importacao.sql",
            "029_bling_config_opcoes.sql",
            "030_parametros_precificacao.sql",
            "031_estoque_deposito.sql",
            "032_valor_drop_manual.sql",
            "033_precificacao_modo.sql",
            "034_imagens_galeria_variante.sql",
        ):
            executar_sql_arquivo(conn, sql_dir / nome)
        seed_usuario_dev(conn)
    finally:
        conn.close()
    print("Bootstrap concluído.")


if __name__ == "__main__":
    main()
