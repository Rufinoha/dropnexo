"""Testes da API do Assistente e da triagem de cadastro."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_token_invalido_retorna_401():
    from api.assistente import servico

    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = None
    row, err = servico.autenticar(conn, "Bearer dn_assist_invalido_xyz")
    assert row is None
    assert err
    assert "Token" in err or "inválido" in err.lower()


def test_listar_nao_expoe_dados_pessoais_vendedor():
    """Contrato: rede/desempenho não trazem campos pessoais de vendedor."""
    src = (ROOT / "api" / "assistente" / "servico.py").read_text(encoding="utf-8")
    # bloco rede só com contagens
    assert "vendedores_conectados" in src
    assert "vendedores_aguardando" in src
    # não deve selecionar email/whatsapp de vendedor na rede
    assert "id_tenant_vendedor" in src or "vendedores_com_pedido_30d" in src
    forbidden_patterns = [
        r"v\.email",
        r"vendedor_email",
        r"telefone_vendedor",
        r"documento_vendedor",
    ]
    for pat in forbidden_patterns:
        assert not re.search(pat, src), f"Padrão suspeito na API: {pat}"


def test_escrita_indicado_403():
    from api.assistente import servico

    cur = MagicMock()
    # eh fornecedor
    cur.fetchone.side_effect = [(1,), (1,)]  # fornecedor ok, depois indicado
    with pytest.raises(PermissionError) as exc:
        # force eh_indicado True via patch
        with patch.object(servico, "_eh_fornecedor", return_value=True), patch.object(
            servico, "eh_indicado", return_value=True
        ):
            servico.post_contato(cur, 1, {"canal": "whatsapp", "direcao": "enviado", "resumo": "oi"})
    assert "indicado" in str(exc.value).lower()


def test_api_nao_altera_produto_pedido():
    src = (ROOT / "api" / "assistente" / "servico.py").read_text(encoding="utf-8")
    # escritas permitidas
    assert "registrar_contato" in src
    assert "definir_fase" in src
    # não deve fazer UPDATE/INSERT em produto/pedido
    assert not re.search(r"UPDATE\s+tbl_produto\b", src, re.I)
    assert not re.search(r"UPDATE\s+tbl_pedido\b", src, re.I)
    assert not re.search(r"INSERT\s+INTO\s+tbl_produto\b", src, re.I)
    assert not re.search(r"INSERT\s+INTO\s+tbl_pedido\b", src, re.I)


def test_triagem_nao_leva_para_vendedor():
    html = (ROOT / "templates" / "frm_cadastro.html").read_text(encoding="utf-8")
    assert "triagem-fornecedor" in html
    assert "Criar conta de vendedor" in html
    assert "url_cadastro_vendedor" in html or "tipo=vendedor" in html or "{{ url_cadastro_vendedor }}" in html
    js = (ROOT / "static" / "script" / "Scadastro.js").read_text(encoding="utf-8")
    assert "triagem_fabrica" in js or "triagemState" in js
    assert "mesmo_assim_fornecedor" in js


def test_servico_sintaxe():
    ast.parse((ROOT / "api" / "assistente" / "servico.py").read_text(encoding="utf-8"))
    ast.parse((ROOT / "api" / "assistente" / "srotas_assistente.py").read_text(encoding="utf-8"))
