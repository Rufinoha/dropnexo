# scripts/consolidar_fase2.py — merge módulos relacionados (fase 2)
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = 0
    if lines and lines[0].startswith("#"):
        start = 1
    while start < len(lines) and lines[start].strip() == "":
        start += 1
    if start < len(lines) and "from __future__" in lines[start]:
        start += 1
    while start < len(lines) and lines[start].strip() == "":
        start += 1
    body_lines = []
    for line in lines[start:]:
        if line.strip() == "from __future__ import annotations":
            continue
        body_lines.append(line)
    return "\n".join(body_lines).rstrip() + "\n"


def merge(base: Path, target: str, title: str, sources: list[str]) -> Path:
    rel = base.relative_to(ROOT).as_posix()
    parts = [
        f"# {rel}/{target} — {title}",
        "from __future__ import annotations",
        "",
    ]
    for i, src in enumerate(sources):
        name = Path(src).stem
        parts.append(f"# ── {name} {'─' * max(10, 50 - len(name))}")
        parts.append("")
        parts.append(_body(base / src))
        if i < len(sources) - 1:
            parts.append("")
    out = base / target
    out.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    print("wrote", out.relative_to(ROOT).as_posix())
    return out


def patch_file(path: Path, patches: list[tuple[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    orig = text
    for old, new in patches:
        text = text.replace(old, new)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        print("patched", path.relative_to(ROOT).as_posix())


def replace_imports(replacements: list[tuple[str, str]], *, skip: set[str]) -> int:
    changed = 0
    for path in ROOT.rglob("*.py"):
        if any(p in path.parts for p in ("__pycache__", ".venv", "venv")):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel in skip or rel == "scripts/consolidar_fase2.py":
            continue
        text = path.read_text(encoding="utf-8")
        orig = text
        for old, new in replacements:
            text = text.replace(old, new)
        if text != orig:
            path.write_text(text, encoding="utf-8")
            changed += 1
    return changed


def delete_files(base: Path, names: list[str]) -> None:
    for name in names:
        p = base / name
        if p.exists():
            p.unlink()
            print("deleted", p.relative_to(ROOT).as_posix())


def _remove_multiline_import(text: str, module: str) -> str:
  """Remove 'from module import (...)' including parenthesized blocks."""
  pattern = rf"^[ \t]*from {re.escape(module)} import \([\s\S]*?\)\n"
  return re.sub(pattern, "", text, flags=re.MULTILINE)


def bling_estoque() -> None:
    base = ROOT / "api" / "bling"
    merge(
        base,
        "estoque.py",
        "depósitos Bling e sincronização de estoque",
        ["depositos.py", "sync_estoque.py"],
    )
    patch_file(
        base / "estoque.py",
        [
            (
                "from api.bling.depositos import resolver_deposito_dropnexo, sincronizar_depositos_bling_api\n",
                "",
            ),
            ("    from api.bling.sync_estoque import sincronizar_depositos_tenant\n", ""),
        ],
    )
    reps = [
        ("from api.bling.depositos import", "from api.bling.estoque import"),
        ("from api.bling.sync_estoque import", "from api.bling.estoque import"),
    ]
    skip = {"api/bling/depositos.py", "api/bling/sync_estoque.py", "api/bling/estoque.py"}
    print("bling estoque: updated", replace_imports(reps, skip=skip), "files")
    delete_files(base, ["depositos.py", "sync_estoque.py"])


def bling_categorias() -> None:
    base = ROOT / "api" / "bling"
    merge(
        base,
        "categorias_bling.py",
        "sincronização e mapeamento de categorias Bling",
        ["sync_categorias.py", "mapeamento_categorias.py"],
    )
    path = base / "categorias_bling.py"
    text = path.read_text(encoding="utf-8")
    text = _remove_multiline_import(text, "api.bling.sync_categorias")
    text = text.replace("from api.bling.sync_estoque import", "from api.bling.estoque import")
    text = text.replace(
        "    from api.bling.sync_categorias import obter_cache_categorias_bling_enriquecido\n",
        "",
    )
    text = text.replace(
        "    from api.bling.sync_categorias import criar_categoria_bling_com_arvore\n",
        "",
    )
    text = text.replace(
        "    from api.bling.sync_categorias import obter_estado_mapeamento_categoria\n",
        "",
    )
    path.write_text(text, encoding="utf-8")
    print("patched", path.relative_to(ROOT).as_posix())

    reps = [
        ("from api.bling.sync_categorias import", "from api.bling.categorias_bling import"),
        ("from api.bling.mapeamento_categorias import", "from api.bling.categorias_bling import"),
    ]
    skip = {
        "api/bling/sync_categorias.py",
        "api/bling/mapeamento_categorias.py",
        "api/bling/categorias_bling.py",
    }
    print("bling categorias: updated", replace_imports(reps, skip=skip), "files")
    delete_files(base, ["sync_categorias.py", "mapeamento_categorias.py"])


def pix_manual() -> None:
    base = ROOT / "api" / "pix_manual"
    merge(
        base,
        "pix_manual.py",
        "configuração, payload BR Code e pedidos PIX manual",
        ["cliente.py", "payload.py", "pedido.py"],
    )
    patch_file(
        base / "pix_manual.py",
        [
            ("from api.pix_manual.cliente import carregar_config_pix_manual, pix_manual_ativo\n", ""),
            ("from api.pix_manual.payload import gerar_payload_pix, normalizar_txid\n", ""),
        ],
    )
    reps = [
        ("from api.pix_manual.cliente import", "from api.pix_manual.pix_manual import"),
        ("from api.pix_manual.payload import", "from api.pix_manual.pix_manual import"),
        ("from api.pix_manual.pedido import", "from api.pix_manual.pix_manual import"),
    ]
    skip = {
        "api/pix_manual/cliente.py",
        "api/pix_manual/payload.py",
        "api/pix_manual/pedido.py",
        "api/pix_manual/pix_manual.py",
    }
    print("pix_manual: updated", replace_imports(reps, skip=skip), "files")
    delete_files(base, ["cliente.py", "payload.py", "pedido.py"])


def mercado_livre() -> None:
    base = ROOT / "api" / "mercado_livre"
    cliente = base / "cliente.py"
    sync = base / "sync_pedidos.py"
    if not sync.exists():
        print("skip mercado_livre (sync_pedidos.py ausente)")
        return
    body = _body(sync)
    body = body.replace(
        "from api.mercado_livre.cliente import api_request, carregar_config_ml\n",
        "",
    )
    text = cliente.read_text(encoding="utf-8").rstrip() + "\n\n"
    text += "# ── sync_pedidos " + "─" * 34 + "\n\n"
    text += body
    cliente.write_text(text, encoding="utf-8")
    print("patched", cliente.relative_to(ROOT).as_posix())

    reps = [
        (
            "from api.mercado_livre.sync_pedidos import importar_pedidos_mercado_livre",
            "from api.mercado_livre.cliente import importar_pedidos_mercado_livre",
        ),
    ]
    skip = {"api/mercado_livre/sync_pedidos.py"}
    print("mercado_livre: updated", replace_imports(reps, skip=skip), "files")
    delete_files(base, ["sync_pedidos.py"])


def vendedor_meus_produtos() -> None:
    base = ROOT / "vendedor" / "meus_produtos"
    merge(
        base,
        "servico_meus_produtos.py",
        "serviços de catálogo próprio do vendedor",
        [
            "servico_categoria_vendedor.py",
            "servico_fornecedor_apoio.py",
            "servico_deposito_vendedor.py",
            "servico_listagem_proprio.py",
            "servico_vitrine_vendedor.py",
        ],
    )
    patch_file(
        base / "servico_meus_produtos.py",
        [
            (
                "from vendedor.meus_produtos.servico_categoria_vendedor import sql_filtro_categoria_proprio\n",
                "",
            ),
        ],
    )
    reps = [
        (
            "from vendedor.meus_produtos.servico_categoria_vendedor import",
            "from vendedor.meus_produtos.servico_meus_produtos import",
        ),
        (
            "from vendedor.meus_produtos.servico_fornecedor_apoio import",
            "from vendedor.meus_produtos.servico_meus_produtos import",
        ),
        (
            "from vendedor.meus_produtos.servico_listagem_proprio import",
            "from vendedor.meus_produtos.servico_meus_produtos import",
        ),
        (
            "from vendedor.meus_produtos.servico_vitrine_vendedor import",
            "from vendedor.meus_produtos.servico_meus_produtos import",
        ),
        (
            "from vendedor.meus_produtos.servico_deposito_vendedor import",
            "from vendedor.meus_produtos.servico_meus_produtos import",
        ),
    ]
    skip = {
        "vendedor/meus_produtos/servico_categoria_vendedor.py",
        "vendedor/meus_produtos/servico_fornecedor_apoio.py",
        "vendedor/meus_produtos/servico_deposito_vendedor.py",
        "vendedor/meus_produtos/servico_listagem_proprio.py",
        "vendedor/meus_produtos/servico_vitrine_vendedor.py",
        "vendedor/meus_produtos/servico_meus_produtos.py",
    }
    print("vendedor meus_produtos: updated", replace_imports(reps, skip=skip), "files")
    delete_files(
        base,
        [
            "servico_categoria_vendedor.py",
            "servico_fornecedor_apoio.py",
            "servico_deposito_vendedor.py",
            "servico_listagem_proprio.py",
            "servico_vitrine_vendedor.py",
        ],
    )


def main() -> None:
    bling_estoque()
    bling_categorias()
    pix_manual()
    mercado_livre()
    vendedor_meus_produtos()
    print("done")


def fornecedor_importacao() -> None:
    base = ROOT / "fornecedor" / "importacao"
    merge(
        base,
        "servico_importacao.py",
        "motor de lotes e tradução de erros de importação",
        ["erro_traducao.py", "servico_importacao.py"],
    )
    patch_file(
        base / "servico_importacao.py",
        [
            (
                "from fornecedor.importacao.erro_traducao import (\n"
                "    enriquecer_erro,\n"
                "    traduzir_mensagem_erro,\n"
                ")\n",
                "",
            ),
        ],
    )
    reps = [
        ("from fornecedor.importacao.erro_traducao import", "from fornecedor.importacao.servico_importacao import"),
    ]
    skip = {
        "fornecedor/importacao/erro_traducao.py",
        "fornecedor/importacao/servico_importacao.py",
    }
    print("fornecedor importacao: updated", replace_imports(reps, skip=skip), "files")
    delete_files(base, ["erro_traducao.py"])


def mercadopago() -> None:
    base = ROOT / "api" / "mercadopago"
    merge(
        base,
        "mercadopago.py",
        "cliente OAuth Mercado Pago e checkout de pedidos",
        ["cliente.py", "pedido.py"],
    )
    text = (base / "mercadopago.py").read_text(encoding="utf-8")
    # remove bloco de import do cliente na seção pedido
    text = _remove_multiline_import(text, "api.mercadopago.cliente")
    (base / "mercadopago.py").write_text(text, encoding="utf-8")
    reps = [
        ("from api.mercadopago.cliente import", "from api.mercadopago.mercadopago import"),
        ("from api.mercadopago.pedido import", "from api.mercadopago.mercadopago import"),
    ]
    skip = {
        "api/mercadopago/cliente.py",
        "api/mercadopago/pedido.py",
        "api/mercadopago/mercadopago.py",
    }
    print("mercadopago: updated", replace_imports(reps, skip=skip), "files")
    delete_files(base, ["cliente.py", "pedido.py"])


def bling_manual() -> None:
    base = ROOT / "api" / "bling"
    merge(
        base,
        "homologacao.py",
        "homologação Bling e conteúdo do manual público",
        ["homologacao.py", "manual_conteudo.py"],
    )
    reps = [
        ("from api.bling.manual_conteudo import", "from api.bling.homologacao import"),
    ]
    skip = {"api/bling/manual_conteudo.py", "api/bling/homologacao.py"}
    print("bling manual: updated", replace_imports(reps, skip=skip), "files")
    delete_files(base, ["manual_conteudo.py"])


def marktplace() -> None:
    base = ROOT / "sistema" / "marktplace"
    merge(
        base,
        "srotas_marktplace.py",
        "catálogo Marktplace e rotas HTTP",
        ["servico_marktplace.py", "srotas_marktplace.py"],
    )
    text = (base / "srotas_marktplace.py").read_text(encoding="utf-8")
    text = _remove_multiline_import(text, "sistema.marktplace.servico_marktplace")
    (base / "srotas_marktplace.py").write_text(text, encoding="utf-8")
    reps = [
        ("from sistema.marktplace.servico_marktplace import", "from sistema.marktplace.srotas_marktplace import"),
    ]
    skip = {
        "sistema/marktplace/servico_marktplace.py",
        "sistema/marktplace/srotas_marktplace.py",
    }
    print("marktplace: updated", replace_imports(reps, skip=skip), "files")
    delete_files(base, ["servico_marktplace.py"])


def main_fase3() -> None:
    fornecedor_importacao()
    mercadopago()
    bling_manual()
    marktplace()
    print("fase3 done")


def melhor_envio() -> None:
    base = ROOT / "api" / "melhor_envio"
    merge(
        base,
        "melhor_envio.py",
        "cliente OAuth Melhor Envio e frete nos pedidos",
        ["cliente.py", "pedido.py"],
    )
    text = (base / "melhor_envio.py").read_text(encoding="utf-8")
    text = _remove_multiline_import(text, "api.melhor_envio.cliente")
    (base / "melhor_envio.py").write_text(text, encoding="utf-8")
    reps = [
        ("from api.melhor_envio.cliente import", "from api.melhor_envio.melhor_envio import"),
        ("from api.melhor_envio.pedido import", "from api.melhor_envio.melhor_envio import"),
    ]
    skip = {
        "api/melhor_envio/cliente.py",
        "api/melhor_envio/pedido.py",
        "api/melhor_envio/melhor_envio.py",
    }
    print("melhor_envio: updated", replace_imports(reps, skip=skip), "files")
    delete_files(base, ["cliente.py", "pedido.py"])


def core_tokens() -> None:
    src = ROOT / "api" / "bling" / "tokens.py"
    dst = ROOT / "core" / "tokens.py"
    body = _body(src)
    dst.write_text(
        "# core/tokens.py — criptografia reversível de tokens OAuth (derivada de SECRET_KEY)\n"
        "from __future__ import annotations\n\n"
        + body,
        encoding="utf-8",
    )
    print("wrote", dst.relative_to(ROOT).as_posix())
    reps = [("from api.bling.tokens import", "from core.tokens import")]
    skip = {"api/bling/tokens.py", "core/tokens.py"}
    print("core tokens: updated", replace_imports(reps, skip=skip), "files")
    delete_files(ROOT / "api" / "bling", ["tokens.py"])


def vendedor_precificacao() -> None:
    base = ROOT / "vendedor" / "precificacao"
    merge(
        base,
        "srotas_precificacao.py",
        "regras de preço do vendedor e rotas HTTP",
        ["servico_precificacao_vendedor.py", "srotas_precificacao.py"],
    )
    text = (base / "srotas_precificacao.py").read_text(encoding="utf-8")
    text = _remove_multiline_import(text, "vendedor.precificacao.servico_precificacao_vendedor")
    (base / "srotas_precificacao.py").write_text(text, encoding="utf-8")
    reps = [
        (
            "from vendedor.precificacao.servico_precificacao_vendedor import",
            "from vendedor.precificacao.srotas_precificacao import",
        ),
    ]
    skip = {
        "vendedor/precificacao/servico_precificacao_vendedor.py",
        "vendedor/precificacao/srotas_precificacao.py",
    }
    print("vendedor precificacao: updated", replace_imports(reps, skip=skip), "files")
    delete_files(base, ["servico_precificacao_vendedor.py"])


def main_fase4() -> None:
    melhor_envio()
    core_tokens()
    vendedor_precificacao()
    print("fase4 done")


def mercado_livre_modulo() -> None:
    base = ROOT / "api" / "mercado_livre"
    src = base / "cliente.py"
    dst = base / "mercado_livre.py"
    text = src.read_text(encoding="utf-8")
    text = text.replace(
        "# api/mercado_livre/cliente.py — OAuth e cliente HTTP Mercado Livre",
        "# api/mercado_livre/mercado_livre.py — OAuth, API e sync de pedidos ML",
    )
    dst.write_text(text, encoding="utf-8")
    print("wrote", dst.relative_to(ROOT).as_posix())
    reps = [("from api.mercado_livre.cliente import", "from api.mercado_livre.mercado_livre import")]
    skip = {"api/mercado_livre/cliente.py", "api/mercado_livre/mercado_livre.py"}
    print("mercado_livre: updated", replace_imports(reps, skip=skip), "files")
    delete_files(base, ["cliente.py"])


def fornecedor_segmentos() -> None:
    base = ROOT / "fornecedor" / "segmentos"
    src = base / "servico_segmentos.py"
    dst = base / "segmentos.py"
    text = src.read_text(encoding="utf-8")
    text = text.replace(
        "# fornecedor/segmentos/servico_segmentos.py",
        "# fornecedor/segmentos/segmentos.py — nichos e segmentos do fornecedor",
    )
    dst.write_text(text, encoding="utf-8")
    print("wrote", dst.relative_to(ROOT).as_posix())
    reps = [
        ("from fornecedor.segmentos.servico_segmentos import", "from fornecedor.segmentos.segmentos import"),
    ]
    skip = {
        "fornecedor/segmentos/servico_segmentos.py",
        "fornecedor/segmentos/segmentos.py",
    }
    print("fornecedor segmentos: updated", replace_imports(reps, skip=skip), "files")
    delete_files(base, ["servico_segmentos.py"])


def main_fase5() -> None:
    mercado_livre_modulo()
    fornecedor_segmentos()
    print("fase5 done")


def vendedor_fornecedores() -> None:
    base = ROOT / "vendedor" / "fornecedores"
    merge(
        base,
        "srotas_fornecedores.py",
        "vínculos com fornecedores e desconexão",
        ["servico_desvincular_fornecedor.py", "srotas_fornecedores.py"],
    )
    patch_file(
        base / "srotas_fornecedores.py",
        [
            (
                "from vendedor.fornecedores.servico_desvincular_fornecedor import desconectar_fornecedor\n",
                "",
            ),
        ],
    )
    delete_files(base, ["servico_desvincular_fornecedor.py"])


def fornecedor_precificacao() -> None:
    base = ROOT / "fornecedor" / "parametros"
    src = base / "servico_precificacao.py"
    dst = base / "precificacao.py"
    text = src.read_text(encoding="utf-8")
    text = text.replace(
        "# fornecedor/parametros/servico_precificacao.py — regras de preço Drop (fornecedor → vendedor)",
        "# fornecedor/parametros/precificacao.py — regras de preço Drop (fornecedor → vendedor)",
    )
    dst.write_text(text, encoding="utf-8")
    print("wrote", dst.relative_to(ROOT).as_posix())
    reps = [
        ("from fornecedor.parametros.servico_precificacao import", "from fornecedor.parametros.precificacao import"),
    ]
    skip = {
        "fornecedor/parametros/servico_precificacao.py",
        "fornecedor/parametros/precificacao.py",
    }
    print("fornecedor precificacao: updated", replace_imports(reps, skip=skip), "files")
    delete_files(base, ["servico_precificacao.py"])


def fornecedor_catalogo() -> None:
    base = ROOT / "fornecedor" / "catalogo"
    merge(
        base,
        "catalogo.py",
        "imagens, estoque por depósito e promoção de variantes",
        [
            "servico_promocao_variante.py",
            "servico_imagens.py",
            "servico_estoque_deposito.py",
        ],
    )
    patch_file(
        base / "catalogo.py",
        [
            (
                "    from fornecedor.catalogo.servico_promocao_variante import reagir_estoque_promocao\n",
                "",
            ),
        ],
    )
    reps = [
        ("from fornecedor.catalogo.servico_promocao_variante import", "from fornecedor.catalogo.catalogo import"),
        ("from fornecedor.catalogo.servico_imagens import", "from fornecedor.catalogo.catalogo import"),
        ("from fornecedor.catalogo.servico_estoque_deposito import", "from fornecedor.catalogo.catalogo import"),
    ]
    skip = {
        "fornecedor/catalogo/servico_promocao_variante.py",
        "fornecedor/catalogo/servico_imagens.py",
        "fornecedor/catalogo/servico_estoque_deposito.py",
        "fornecedor/catalogo/catalogo.py",
    }
    print("fornecedor catalogo: updated", replace_imports(reps, skip=skip), "files")
    delete_files(
        base,
        ["servico_promocao_variante.py", "servico_imagens.py", "servico_estoque_deposito.py"],
    )


def fornecedor_requisitos() -> None:
    src = ROOT / "fornecedor" / "requisitos_vendedor.py"
    dst = ROOT / "fornecedor" / "parametros" / "requisitos.py"
    text = src.read_text(encoding="utf-8")
    if text.startswith('"""'):
        end = text.find('"""', 3)
        doc = text[: end + 3] if end >= 0 else ""
        rest = text[end + 3 :].lstrip("\n") if end >= 0 else text
        text = (
            "# fornecedor/parametros/requisitos.py — requisitos para vínculo com vendedores\n"
            + doc
            + "\n\n"
            + rest
        )
    else:
        text = (
            "# fornecedor/parametros/requisitos.py — requisitos para vínculo com vendedores\n" + text
        )
    dst.write_text(text, encoding="utf-8")
    print("wrote", dst.relative_to(ROOT).as_posix())
    reps = [
        ("from fornecedor.requisitos_vendedor import", "from fornecedor.parametros.requisitos import"),
    ]
    skip = {"fornecedor/requisitos_vendedor.py", "fornecedor/parametros/requisitos.py"}
    print("fornecedor requisitos: updated", replace_imports(reps, skip=skip), "files")
    if src.exists():
        src.unlink()
        print("deleted", src.relative_to(ROOT).as_posix())


def main_fase6() -> None:
    vendedor_fornecedores()
    fornecedor_precificacao()
    fornecedor_catalogo()
    fornecedor_requisitos()
    print("fase6 done")


def sistema_integracoes() -> None:
    base = ROOT / "sistema" / "integracoes"
    merge(
        base,
        "srotas_integracoes.py",
        "catálogo e rotas do hub de integrações",
        ["catalogo.py", "srotas_integracoes.py"],
    )
    patch_file(
        base / "srotas_integracoes.py",
        [
            (
                "from sistema.integracoes.catalogo import catalogo_integracoes_modulo, render_pagina_integracoes, url_icone_integracao\n",
                "",
            ),
        ],
    )
    reps = [
        ("from sistema.integracoes.catalogo import", "from sistema.integracoes.srotas_integracoes import"),
    ]
    skip = {
        "sistema/integracoes/catalogo.py",
        "sistema/integracoes/srotas_integracoes.py",
    }
    print("sistema integracoes: updated", replace_imports(reps, skip=skip), "files")
    delete_files(base, ["catalogo.py"])


def api_efi() -> None:
    base = ROOT / "api" / "efi"
    src = base / "cliente.py"
    dst = base / "efi.py"
    text = src.read_text(encoding="utf-8")
    text = text.replace(
        "# api/efi/cliente.py — cliente Efi Pay (cobranças / boleto)",
        "# api/efi/efi.py — cliente Efi Pay (cobranças / boleto)",
    )
    dst.write_text(text, encoding="utf-8")
    print("wrote", dst.relative_to(ROOT).as_posix())
    reps = [("from api.efi.cliente import", "from api.efi.efi import")]
    skip = {"api/efi/cliente.py", "api/efi/efi.py"}
    print("api efi: updated", replace_imports(reps, skip=skip), "files")
    delete_files(base, ["cliente.py"])


def core_pedidos() -> None:
    base = ROOT / "core" / "pedidos"
    servico = base / "servico.py"
    text = servico.read_text(encoding="utf-8")
    text = text.replace(
        "from core.pedidos.estoque_reserva import (\n"
        "    baixar_itens_pedido,\n"
        "    liberar_itens_pedido,\n"
        "    reservar_itens_pedido,\n"
        ")\n",
        "",
    )
    for name in ("estoque_reserva.py", "meios_pagamento.py"):
        stem = Path(name).stem
        text += f"\n\n# ── {stem} {'─' * max(10, 50 - len(stem))}\n\n"
        text += _body(base / name)
    servico.write_text(text, encoding="utf-8")
    print("patched", servico.relative_to(ROOT).as_posix())
    reps = [
        ("from core.pedidos.estoque_reserva import", "from core.pedidos.servico import"),
        ("from core.pedidos.meios_pagamento import", "from core.pedidos.servico import"),
    ]
    skip = {
        "core/pedidos/estoque_reserva.py",
        "core/pedidos/meios_pagamento.py",
        "core/pedidos/servico.py",
    }
    print("core pedidos: updated", replace_imports(reps, skip=skip), "files")
    delete_files(base, ["estoque_reserva.py", "meios_pagamento.py"])


def main_fase7() -> None:
    sistema_integracoes()
    api_efi()
    core_pedidos()
    print("fase7 done")


def core_dominio() -> None:
    base = ROOT / "core"
    merge(
        base,
        "dominio.py",
        "categorias, CNPJ e vínculos vendedor×fornecedor",
        ["categorias.py", "cnpj.py", "vinculos.py"],
    )
    reps = [
        ("from core.categorias import", "from core.dominio import"),
        ("from core.cnpj import", "from core.dominio import"),
        ("from core.vinculos import", "from core.dominio import"),
    ]
    skip = {
        "core/categorias.py",
        "core/cnpj.py",
        "core/vinculos.py",
        "core/dominio.py",
    }
    print("core dominio: updated", replace_imports(reps, skip=skip), "files")
    delete_files(base, ["categorias.py", "cnpj.py", "vinculos.py"])


def main_fase8() -> None:
    core_dominio()
    print("fase8 done")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "fase3":
        main_fase3()
    elif len(sys.argv) > 1 and sys.argv[1] == "fase4":
        main_fase4()
    elif len(sys.argv) > 1 and sys.argv[1] == "fase5":
        main_fase5()
    elif len(sys.argv) > 1 and sys.argv[1] == "fase6":
        main_fase6()
    elif len(sys.argv) > 1 and sys.argv[1] == "fase7":
        main_fase7()
    elif len(sys.argv) > 1 and sys.argv[1] == "fase8":
        main_fase8()
    else:
        main()
