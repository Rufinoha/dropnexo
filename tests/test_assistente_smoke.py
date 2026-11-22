"""Smoke da API do Assistente contra o banco DEV.

Pula automaticamente se DB_PASSWORD_DEV (ou conexão DEV) não estiver disponível.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("psycopg2")

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:
    pass

# Sinal explícito do prompt: sem senha DEV, não roda.
if not (os.getenv("DB_PASSWORD_DEV") or "").strip():
    pytest.skip("DB_PASSWORD_DEV não definido — smoke do Assistente pulado.", allow_module_level=True)


@pytest.fixture(scope="module")
def app_client():
    from app import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(scope="module")
def conn():
    from global_utils import Var_ConectarBanco

    c = Var_ConectarBanco()
    try:
        yield c
    finally:
        try:
            c.close()
        except Exception:
            pass


@pytest.fixture(scope="module")
def token_plain(conn):
    from api.assistente import servico

    cur = conn.cursor()
    # Garante tabelas (migração 24) — se faltar, o teste falha de forma clara.
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
         WHERE table_name = 'tbl_assistente_token' LIMIT 1
        """
    )
    if not cur.fetchone():
        pytest.skip("tbl_assistente_token ausente — rode sql/24_assistente_token.sql")
    cfg, token = servico.gerar_token(conn, id_usuario=None, nome="SmokeTest")
    conn.commit()
    assert token.startswith("dn_assist_")
    assert cfg.get("token_hint")
    yield token
    # revoga ao final
    servico.revogar_token(conn, id_usuario=None)
    conn.commit()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _fundador_sem_pedidos(conn) -> int | None:
    cur = conn.cursor()
    from core.pedidos.servico import col_status_vendedor

    col_st = col_status_vendedor(cur)
    cur.execute(
        f"""
        SELECT t.id
          FROM tbl_tenant t
         WHERE COALESCE(t.eh_fornecedor_fundador, FALSE) = TRUE
           AND t.tipo_negocio IN ('fornecedor', 'hibrido')
           AND NOT EXISTS (
             SELECT 1 FROM tbl_pedido ped
              WHERE ped.id_tenant_fornecedor = t.id
                AND COALESCE(ped.{col_st}, '') NOT IN ('rascunho', 'cancelado')
           )
         ORDER BY t.id
         LIMIT 1
        """
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def test_smoke_endpoints_trova_e_fundador(app_client, conn, token_plain):
    headers = _auth(token_plain)
    endpoints = [
        "/api/v1/assistente/resumo",
        "/api/v1/assistente/fornecedores?per_page=5",
        "/api/v1/assistente/fornecedores/1",
        "/api/v1/assistente/fornecedores/1/produtos?per_page=5",
        "/api/v1/assistente/fornecedores/1/pedidos?per_page=5",
    ]
    fund = _fundador_sem_pedidos(conn)
    if fund and fund != 1:
        endpoints.extend(
            [
                f"/api/v1/assistente/fornecedores/{fund}",
                f"/api/v1/assistente/fornecedores/{fund}/produtos?per_page=5",
                f"/api/v1/assistente/fornecedores/{fund}/pedidos?per_page=5",
            ]
        )

    for path in endpoints:
        r = app_client.get(path, headers=headers)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.get_data(as_text=True)[:200]}"
        j = r.get_json()
        assert j and j.get("success") is True, path
        if path.rstrip("/").endswith("/resumo"):
            assert "por_fase" in j and "fundadores" in j
            assert "pedidos_atrasados_total" in j
            assert "fornecedores_com_atraso" in j
        if path.rstrip("/").endswith("/fornecedores/1"):
            assert "cadastro" in j and "resumo" in j
            assert "avisos" in j
            if j.get("pedidos") and j["pedidos"].get("atrasados"):
                item = j["pedidos"]["atrasados"][0]
                assert "valor_total" in item
                assert "cidade" in item and "uf" in item


def test_smoke_contato_indicado_403_e_nao_indicado_ok(app_client, conn, token_plain):
    from api.assistente import servico

    headers = _auth(token_plain)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT i.id_tenant_indicado
          FROM tbl_comissao_indicacao i
          JOIN tbl_tenant t ON t.id = i.id_tenant_indicado
         WHERE t.tipo_negocio IN ('fornecedor', 'hibrido')
         LIMIT 1
        """
    )
    row = cur.fetchone()
    if row:
        tid_ind = int(row[0])
        r = app_client.post(
            f"/api/v1/assistente/fornecedores/{tid_ind}/contato",
            headers=headers,
            json={
                "canal": "outro",
                "direcao": "enviado",
                "resumo": "Smoke — não deve gravar em indicado",
            },
        )
        assert r.status_code == 403
        assert "indicado" in (r.get_json() or {}).get("message", "").lower()

    # Não indicado: grava e rollback
    cur.execute(
        """
        SELECT t.id FROM tbl_tenant t
         WHERE t.tipo_negocio IN ('fornecedor', 'hibrido')
           AND NOT EXISTS (
             SELECT 1 FROM tbl_comissao_indicacao i WHERE i.id_tenant_indicado = t.id
           )
         ORDER BY t.id
         LIMIT 1
        """
    )
    row2 = cur.fetchone()
    if not row2:
        pytest.skip("Sem fornecedor não indicado para testar POST contato")
    tid = int(row2[0])
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
         WHERE table_name = 'tbl_fornecedor_contato' LIMIT 1
        """
    )
    if not cur.fetchone():
        pytest.skip("tbl_fornecedor_contato ausente — rode sql/23")

    conn.commit()
    r = app_client.post(
        f"/api/v1/assistente/fornecedores/{tid}/contato",
        headers=headers,
        json={
            "canal": "outro",
            "direcao": "enviado",
            "resumo": "Smoke teste assistente — apagar",
            "aprovado_por": "Smoke",
        },
    )
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    j = r.get_json()
    assert j.get("success")
    cid = (j.get("contato") or {}).get("id")
    assert cid

    # confere no histórico
    r2 = app_client.get(f"/api/v1/assistente/fornecedores/{tid}", headers=headers)
    assert r2.status_code == 200
    contatos = ((r2.get_json() or {}).get("acompanhamento") or {}).get("contatos") or []
    assert any(c.get("id") == cid for c in contatos)

    # rollback / limpeza do contato de smoke
    cur = conn.cursor()
    cur.execute("DELETE FROM tbl_fornecedor_contato WHERE id = %s", (cid,))
    conn.commit()


def test_smoke_token_invalido_401(app_client):
    r = app_client.get(
        "/api/v1/assistente/resumo",
        headers={"Authorization": "Bearer dn_assist_invalido_xyzxyzxyzxyz"},
    )
    assert r.status_code == 401
