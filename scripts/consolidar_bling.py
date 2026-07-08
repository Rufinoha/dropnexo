# scripts/consolidar_bling.py — merge api/bling modules (one-time refactor helper)
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLING = ROOT / "api" / "bling"


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
    return "\n".join(lines[start:]).rstrip() + "\n"


def merge(target: str, title: str, sources: list[str]) -> None:
    parts = [
        f"# api/bling/{target} — {title}",
        "from __future__ import annotations",
        "",
    ]
    for i, src in enumerate(sources):
        name = Path(src).stem
        parts.append(f"# ── {name} {'─' * max(10, 50 - len(name))}")
        parts.append("")
        parts.append(_body(BLING / src))
        if i < len(sources) - 1:
            parts.append("")
    (BLING / target).write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    print("wrote", target)


REPLACEMENTS = [
    ("from api.bling.campos_produto import", "from api.bling.campos import"),
    ("from api.bling.campos_pedido import", "from api.bling.campos import"),
    ("from api.bling.sync_pedidos import", "from api.bling.pedidos import"),
    ("from api.bling.sync_pedido_status import", "from api.bling.pedidos import"),
    ("from api.bling.export_pedidos import", "from api.bling.pedidos import"),
    ("from api.bling.webhook_pedidos import", "from api.bling.webhooks import"),
    ("from api.bling.webhook_estoque import", "from api.bling.webhooks import"),
    ("from api.bling.importacao_progresso import", "from api.bling.sync_progresso import"),
    ("from api.bling.estoque_sync_progresso import", "from api.bling.sync_progresso import"),
    ("from api.bling.categorias_sync_progresso import", "from api.bling.sync_progresso import"),
    ("from api.bling.config_padrao import", "from api.bling.config import"),
    ("from api.bling.conta_empresa import", "from api.bling.config import"),
    ("from api.bling.eco_estoque import", "from api.bling.config import"),
    ("from api.bling.sync_produtos import", "from api.bling.produtos import"),
    ("from api.bling.export_produtos import", "from api.bling.produtos import"),
    ("from api.bling.imagens import", "from api.bling.produtos import"),
]

DELETE = [
    "campos_produto.py",
    "campos_pedido.py",
    "sync_pedidos.py",
    "sync_pedido_status.py",
    "export_pedidos.py",
    "webhook_pedidos.py",
    "webhook_estoque.py",
    "importacao_progresso.py",
    "estoque_sync_progresso.py",
    "categorias_sync_progresso.py",
    "config_padrao.py",
    "conta_empresa.py",
    "eco_estoque.py",
    "sync_produtos.py",
    "export_produtos.py",
    "imagens.py",
]


def main() -> None:
    merge(
        "campos.py",
        "normalização de payloads Bling (produto e pedido)",
        ["campos_produto.py", "campos_pedido.py"],
    )
    merge(
        "pedidos.py",
        "importação, exportação e status de pedidos Bling",
        ["sync_pedidos.py", "sync_pedido_status.py", "export_pedidos.py"],
    )
    merge(
        "webhooks.py",
        "webhooks Bling (estoque e pedidos)",
        ["webhook_estoque.py", "webhook_pedidos.py"],
    )
    merge(
        "sync_progresso.py",
        "jobs assíncronos com progresso (produtos, estoque, categorias)",
        ["importacao_progresso.py", "estoque_sync_progresso.py", "categorias_sync_progresso.py"],
    )
    merge(
        "config.py",
        "configuração padrão, conta empresa e eco de estoque",
        ["config_padrao.py", "eco_estoque.py", "conta_empresa.py"],
    )
    merge(
        "produtos.py",
        "importação, exportação e imagens de produtos Bling",
        ["imagens.py", "sync_produtos.py", "export_produtos.py"],
    )

    for name in [
        "campos.py",
        "pedidos.py",
        "webhooks.py",
        "sync_progresso.py",
        "config.py",
        "produtos.py",
    ]:
        path = BLING / name
        text = path.read_text(encoding="utf-8")
        for old, new in REPLACEMENTS:
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")

    skip = {f"api/bling/{d}" for d in DELETE} | {
        "api/bling/campos.py",
        "api/bling/pedidos.py",
        "api/bling/webhooks.py",
        "api/bling/sync_progresso.py",
        "api/bling/config.py",
        "api/bling/produtos.py",
    }
    changed = 0
    for path in ROOT.rglob("*.py"):
        if any(p in path.parts for p in ("__pycache__", ".venv", "venv")):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel in skip or rel == "scripts/consolidar_bling.py":
            continue
        text = path.read_text(encoding="utf-8")
        orig = text
        for old, new in REPLACEMENTS:
            text = text.replace(old, new)
        if text != orig:
            path.write_text(text, encoding="utf-8")
            changed += 1
    print("updated imports in", changed, "files")

    for name in DELETE:
        p = BLING / name
        if p.exists():
            p.unlink()
            print("deleted", name)


if __name__ == "__main__":
    main()
