"""Documentação e prompt exibidos no card da API Externa."""
from __future__ import annotations


def documentacao_markdown() -> str:
    return """# API Externa DropNexo — guia do parceiro

O DropNexo **consulta a API de vocês** para importar/atualizar produtos e estoque.
Opcionalmente, o DropNexo **envia eventos** (pedidos/status) para o webhook de vocês.

## Autenticação
- Preferencial: `Authorization: Bearer <TOKEN>`
- Alternativa: header `X-Api-Key: <TOKEN>`
- HTTPS obrigatório

## Endpoints que o DropNexo chama (na sua API)

### `GET /v1/products`
Query: `cursor`, `updated_since`, `limit`

```json
{
  "data": [
    {
      "sku": "ABC-001",
      "external_id": "123",
      "nome": "Produto Exemplo",
      "descricao": "Texto",
      "preco": 29.90,
      "preco_promocional": null,
      "preco_custo": 15.00,
      "quantidade": 100,
      "unidade": "UN",
      "gtin": "789...",
      "ncm": "12345678",
      "origem_fiscal": "0",
      "marca": "Marca",
      "categoria": "Cat > Sub",
      "peso_bruto_kg": 0.5,
      "altura_cm": 10,
      "largura_cm": 10,
      "profundidade_cm": 10,
      "publicado": true,
      "imagens": ["https://cdn.../1.jpg"],
      "atributos": {"Cor": "Azul"},
      "warehouses": [{"code": "SP1", "quantidade": 80}],
      "updated_at": "2026-11-12T15:30:00Z"
    }
  ],
  "next_cursor": null
}
```

### `GET /v1/products/{sku}`
Retorna um produto no mesmo formato do item acima.

### `GET /v1/stock`
Query: `cursor`, `updated_since`, `sku`

```json
{
  "data": [
    {
      "sku": "ABC-001",
      "quantidade": 100,
      "warehouses": [{"code": "SP1", "quantidade": 80}],
      "updated_at": "2026-11-12T16:00:00Z"
    }
  ],
  "next_cursor": null
}
```

### `GET /v1/warehouses`
```json
{
  "data": [
    {"code": "SP1", "nome": "CD São Paulo"}
  ]
}
```

## Regras
- **SKU** é a chave estável (não pode mudar).
- Variação: informe `sku_pai` + `atributos`.
- Paginação com `next_cursor`.
- Use `updated_since` para sync incremental.
- Imagens em URL pública HTTPS.

## Capacidades no DropNexo
No card da integração o fornecedor liga/desliga:
- Produtos: cadastrar / atualizar
- Estoque: atualizar
- Pedidos: enviar ao ERP / troca de status *(em expansão)*

## Webhook do parceiro (DropNexo → vocês)
Informe a URL no card. Eventos previstos:
- `order.created`
- `order.status_changed`
- `order.canceled`

Assinatura: header `X-DropNexo-Signature: sha256=<hmac>` com o segredo do webhook.

## Token DropNexo (vocês → DropNexo)
Gerado no card (mostrar uma vez). Use para endpoints inbound futuros / confirmações.

## Boas práticas
1. Ambiente de homologação antes de produção
2. Rate limit razoável e respostas JSON UTF-8
3. Logs no seu lado com o SKU/pedido
"""


def prompt_para_ai() -> str:
    return """Você vai construir uma API REST para integrar o ERP/sistema do fornecedor com o DropNexo.

Objetivo: o DropNexo consome (GET) produtos e estoque da nossa API; depois pode enviar pedidos/status via webhook nosso.

Implemente:
1) Auth Bearer token (ou X-Api-Key)
2) GET /v1/products (paginado com cursor + updated_since)
3) GET /v1/products/{sku}
4) GET /v1/stock (paginado)
5) GET /v1/warehouses
6) Payload JSON conforme documentação DropNexo (sku obrigatório, preços numéricos, imagens URL, warehouses opcional)
7) HTTPS, UTF-8, next_cursor
8) Endpoint interno opcional para receber webhooks DropNexo (order.created / order.status_changed) com HMAC sha256

Não invente campos obrigatórios além do guia. SKU é a chave. Variações usam sku_pai + atributos.
Entregue: OpenAPI resumido + exemplos de response + checklist de testes com curl.
"""


def painel_docs() -> dict:
    return {
        "titulo": "Documentação API Externa",
        "versao": "1.0",
        "markdown": documentacao_markdown(),
        "prompt_ai": prompt_para_ai(),
        "html_path": "/ajuda/api-externa",
    }
