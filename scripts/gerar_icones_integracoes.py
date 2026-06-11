#!/usr/bin/env python3
"""Gera SVGs placeholder em sistema/integracoes/static/imge/integracoes/."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sistema" / "integracoes" / "static" / "imge" / "integracoes"

ITEMS = [
    ("mercado-livre", "ML", "#FFE600", "#2D3277"),
    ("amazon", "AZ", "#FF9900", "#111827"),
    ("magazine-luiza", "MG", "#0086FF", "#FFFFFF"),
    ("shopee", "SH", "#EE4D2D", "#FFFFFF"),
    ("americanas", "AM", "#E60014", "#FFFFFF"),
    ("casas-bahia", "CB", "#0033A0", "#FFFFFF"),
    ("tray", "TR", "#7B2CFF", "#FFFFFF"),
    ("loja-integrada", "LI", "#00AEEF", "#FFFFFF"),
    ("nuvemshop", "NV", "#2C3E50", "#FFFFFF"),
    ("beezoo", "BZ", "#F5A623", "#111827"),
    ("bagy", "BG", "#111827", "#FFFFFF"),
    ("melhor-envio", "ME", "#00B2A9", "#FFFFFF"),
    ("correios", "CR", "#FFD100", "#003F7F"),
    ("frenet", "FR", "#0057A8", "#FFFFFF"),
    ("bling", "BL", "#28A745", "#FFFFFF"),
    ("olist", "OL", "#6C2EB9", "#FFFFFF"),
    ("conta-azul", "CA", "#0080FF", "#FFFFFF"),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for slug, ini, bg, fg in ITEMS:
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64" role="img" aria-label="{slug}">
  <rect width="64" height="64" rx="10" fill="{bg}"/>
  <text x="32" y="38" text-anchor="middle" font-family="Segoe UI,Arial,sans-serif" font-weight="700" font-size="17" fill="{fg}">{ini}</text>
</svg>"""
        (OUT / f"{slug}.svg").write_text(svg, encoding="utf-8")
    print(f"OK: {len(ITEMS)} SVGs em {OUT}")


if __name__ == "__main__":
    main()
