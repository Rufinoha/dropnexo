"""Testes da API do Assistente e da triagem de cadastro."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
SERVICO_SRC = ROOT / "api" / "assistente" / "servico.py"

MSG_INDICADO = "Fornecedor indicado por parceiro: contato não permitido pelo assistente"


# ── helpers ────────────────────────────────────────────────────────────
@pytest.fixture()
def client():
    from api.assistente import srotas_assistente

    app = Flask(__name__)
    app.register_blueprint(srotas_assistente.assistente_bp)
    return app.test_client()


@pytest.fixture()
def conn_mock():
    """Conexão fake usada pelas rotas (auth e auditoria passam por ela)."""
    conn = MagicMock()
    with patch("api.assistente.srotas_assistente.Var_ConectarBanco", return_value=conn):
        yield conn


def _autorizar():
    return patch(
        "api.assistente.servico.autenticar",
        return_value=({"id": 1, "hint": "dn_a…wxyz"}, None),
    )


# ── autenticação ───────────────────────────────────────────────────────
def test_token_invalido_retorna_401_servico():
    from api.assistente import servico

    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = None
    row, err = servico.autenticar(conn, "Bearer dn_assist_invalido_xyz_123456789")
    assert row is None
    assert err


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer abc"},
        {"Authorization": "Bearer dn_assist_token_que_nao_existe_000000"},
        {"Authorization": "Basic dn_assist_x"},
    ],
)
def test_token_invalido_retorna_401_http(client, conn_mock, headers):
    conn_mock.cursor.return_value.fetchone.return_value = None
    for rota in ("/api/v1/assistente/resumo", "/api/v1/assistente/fornecedores"):
        r = client.get(rota, headers=headers)
        assert r.status_code == 401
        body = r.get_json()
        assert body["success"] is False
        assert "Traceback" not in r.get_data(as_text=True)


def test_token_revogado_retorna_401(client, conn_mock):
    # (id, hint, ativo=False, revogado_em)
    conn_mock.cursor.return_value.fetchone.return_value = (1, "dn_a…wxyz", False, None)
    r = client.get(
        "/api/v1/assistente/resumo",
        headers={"Authorization": "Bearer dn_assist_" + "a" * 43},
    )
    assert r.status_code == 401


def test_token_hash_e_hint():
    import hashlib

    from api.assistente import servico

    tok = "dn_assist_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"
    assert servico._hash_token(tok) == hashlib.sha256(tok.encode()).hexdigest()
    assert servico._hint(tok) == f"{tok[:4]}…{tok[-4:]}"


def test_gerar_token_guarda_so_hash():
    from api.assistente import servico

    conn = MagicMock()
    cur = conn.cursor.return_value
    cur.fetchone.return_value = (5, "x", "Assistente", None)
    cfg, token = servico.gerar_token(conn, id_usuario=1)
    assert token.startswith("dn_assist_")
    insert_params = [c.args[1] for c in cur.execute.call_args_list if "INSERT" in c.args[0]][0]
    assert servico._hash_token(token) == insert_params[0]
    assert token not in insert_params
    assert "token" not in cfg


def test_rate_limit_60_por_minuto():
    from api.assistente import servico

    servico._rate.clear()
    ok = [servico._rate_ok("dn_a…rate") for _ in range(servico.RATE_LIMIT_POR_MIN + 5)]
    assert ok[: servico.RATE_LIMIT_POR_MIN] == [True] * servico.RATE_LIMIT_POR_MIN
    assert not any(ok[servico.RATE_LIMIT_POR_MIN :])
    servico._rate.clear()


# ── escrita em fornecedor indicado ─────────────────────────────────────
@pytest.mark.parametrize("rota,body", [
    ("contato", {"canal": "whatsapp", "direcao": "enviado", "resumo": "oi"}),
    ("fase", {"fase": "lembrete", "motivo": "teste"}),
])
def test_escrita_indicado_retorna_403_http(client, conn_mock, rota, body):
    with _autorizar(), patch("api.assistente.servico._eh_fornecedor", return_value=True), patch(
        "api.assistente.servico.eh_indicado", return_value=True
    ), patch("api.assistente.servico.registrar_contato") as rc, patch(
        "api.assistente.servico.definir_fase"
    ) as df:
        r = client.post(f"/api/v1/assistente/fornecedores/10/{rota}", json=body)
    assert r.status_code == 403
    assert r.get_json()["message"] == MSG_INDICADO
    rc.assert_not_called()
    df.assert_not_called()


def test_escrita_indicado_403_servico():
    from api.assistente import servico

    with patch.object(servico, "_eh_fornecedor", return_value=True), patch.object(
        servico, "eh_indicado", return_value=True
    ):
        with pytest.raises(PermissionError) as exc:
            servico.post_contato(MagicMock(), 1, {"canal": "whatsapp", "direcao": "enviado", "resumo": "oi"})
    assert str(exc.value) == MSG_INDICADO


def test_escrita_nao_indicado_usa_servicos_de_acompanhamento():
    from api.assistente import servico

    with patch.object(servico, "_eh_fornecedor", return_value=True), patch.object(
        servico, "eh_indicado", return_value=False
    ), patch.object(servico, "registrar_contato", return_value={"id": 1}) as rc, patch.object(
        servico, "definir_fase", return_value={"id": 1, "fase": "ativo"}
    ) as df:
        servico.post_contato(
            MagicMock(), 1, {"canal": "email", "direcao": "enviado", "resumo": "x"}, aprovado_por="Hazael"
        )
        servico.post_fase(MagicMock(), 1, {"fase": "ativo", "motivo": "ok"})
    assert rc.call_args.kwargs["autor"] == "Assistente (aprovado por Hazael)"
    assert df.call_args.kwargs["autor"] == "Assistente"


def test_leitura_indicado_nao_e_bloqueada():
    """Indicado só bloqueia escrita; detalhe usa apenas leitura."""
    src = SERVICO_SRC.read_text(encoding="utf-8")
    corpo = src[src.index("def detalhe_fornecedor") : src.index("def _bloco_pedidos")]
    assert "eh_indicado(cur, tid)" in corpo  # exposto só como booleano
    assert "PermissionError" not in corpo


# ── privacidade do vendedor ────────────────────────────────────────────
CAMPOS_PESSOAIS = {
    "email", "whatsapp", "telefone", "documento", "nome", "cliente_nome", "cliente_email",
    "cliente_telefone", "cliente_documento", "entrega_cidade", "id_tenant_vendedor", "vendedor",
}


def _chaves(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _chaves(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _chaves(v)


def test_item_pedido_sem_dados_pessoais():
    from datetime import datetime, timezone

    from api.assistente import servico

    agora = datetime.now(timezone.utc)
    item = servico._item_pedido((1, "P-1", agora, "pago", "pago", 10.5, agora, None, None, True, agora))
    assert not (set(item) & CAMPOS_PESSOAIS)
    assert item["valor_centavos"] == 1050


def test_rede_somente_contagens():
    from api.assistente import servico

    cur = MagicMock()
    cur.fetchone.side_effect = [(2, 1, None), (3,)]
    with patch("core.pedidos.servico.col_status_vendedor", return_value="status_vendedor"):
        rede = servico._bloco_rede(cur, 7)
    assert set(rede) == {
        "vendedores_conectados",
        "vendedores_aguardando",
        "aguardando_mais_antigo_dias",
        "vendedores_com_pedido_30d",
    }
    assert all(isinstance(v, (int, type(None))) for v in rede.values())
    assert not (set(_chaves(rede)) & CAMPOS_PESSOAIS)


def test_servico_nao_seleciona_dados_de_vendedor():
    src = SERVICO_SRC.read_text(encoding="utf-8")
    for pat in (r"v\.email", r"cliente_nome", r"cliente_email", r"cliente_telefone",
                r"cliente_documento", r"snapshot_vendedor", r"entrega_cidade", r"entrega_logradouro"):
        assert not re.search(pat, src), f"Padrão suspeito na API: {pat}"


def test_escopo_somente_fornecedores():
    src = SERVICO_SRC.read_text(encoding="utf-8")
    assert "tipo_negocio IN ('fornecedor', 'hibrido')" in src


# ── não altera produto / pedido ────────────────────────────────────────
def test_api_nao_altera_produto_pedido_plano_fundador():
    src = SERVICO_SRC.read_text(encoding="utf-8") + (
        ROOT / "api" / "assistente" / "srotas_assistente.py"
    ).read_text(encoding="utf-8")
    assert "registrar_contato" in src and "definir_fase" in src
    proibidos = (
        r"UPDATE\s+tbl_produto\w*", r"UPDATE\s+tbl_pedido\w*", r"INSERT\s+INTO\s+tbl_produto\w*",
        r"INSERT\s+INTO\s+tbl_pedido\w*", r"DELETE\s+FROM\s+tbl_(produto|pedido)\w*",
        r"UPDATE\s+tbl_tenant\b", r"fornecedor_fundador_ativo\s*=\s*%s", r"SET\s+plano",
    )
    for pat in proibidos:
        assert not re.search(pat, src, re.I), f"Escrita proibida: {pat}"


def test_api_nao_faz_ddl_em_requisicao():
    src = SERVICO_SRC.read_text(encoding="utf-8")
    assert not re.search(r"\b(CREATE|ALTER|DROP)\s+(TABLE|INDEX|COLUMN)\b", src, re.I)
    assert "garantir_colunas" not in src
    assert "status_programa" not in src  # status_programa executa DDL defensivo


def test_erros_genericos_sem_stack(client, conn_mock):
    with _autorizar(), patch("api.assistente.servico.painel_resumo", side_effect=RuntimeError("SELECT secreto")):
        r = client.get("/api/v1/assistente/resumo")
    assert r.status_code == 500
    txt = r.get_data(as_text=True)
    assert "secreto" not in txt and "Traceback" not in txt


def test_auditoria_registra_chamada(client, conn_mock):
    with _autorizar(), patch("api.assistente.servico.painel_resumo", return_value={}), patch(
        "api.assistente.servico.auditar"
    ) as aud:
        r = client.get("/api/v1/assistente/resumo", headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 200
    kw = aud.call_args.kwargs
    assert kw["rota"] == "/api/v1/assistente/resumo"
    assert kw["ip"] == "1.2.3.4"
    assert kw["token_hint"] == "dn_a…wxyz"
    assert kw["http_status"] == 200


def test_migracoes_identicas():
    a = (ROOT / "sql" / "24_assistente_token.sql").read_text(encoding="utf-8")
    b = (ROOT / "__doc" / "sql" / "065_assistente_token.sql").read_text(encoding="utf-8")
    for tabela in ("tbl_assistente_token", "tbl_assistente_auditoria"):
        assert f"CREATE TABLE IF NOT EXISTS {tabela}" in a
        assert f"CREATE TABLE IF NOT EXISTS {tabela}" in b


# ── triagem: "Não" na Q1 leva ao cadastro de vendedor ──────────────────
def test_triagem_nao_leva_para_vendedor():
    html = (ROOT / "templates" / "frm_cadastro.html").read_text(encoding="utf-8")
    assert "triagem-fornecedor" in html
    assert "Criar conta de vendedor" in html
    assert "url_cadastro_vendedor" in html or "tipo=vendedor" in html
    js = (ROOT / "static" / "script" / "Scadastro.js").read_text(encoding="utf-8")
    assert "triagem_fabrica" in js or "triagemState" in js
    assert "mesmo_assim_fornecedor" in js


def test_servico_sintaxe():
    ast.parse(SERVICO_SRC.read_text(encoding="utf-8"))
    ast.parse((ROOT / "api" / "assistente" / "srotas_assistente.py").read_text(encoding="utf-8"))
