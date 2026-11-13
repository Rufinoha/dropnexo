"""Documentação e prompt exibidos no card da API Externa."""
from __future__ import annotations

from api.api_externa import exemplos_docs as ex


def documentacao_markdown() -> str:
    return f"""# API Externa DropNexo — guia do parceiro

O DropNexo **consulta a API de vocês** para importar/atualizar produtos e estoque.
Opcionalmente, o DropNexo **envia eventos** (pedidos/status) para o webhook de vocês.

Campos abaixo espelham o catálogo e pedidos do DropNexo. Envie todos que tiver;
os não obrigatórios podem ser `null` ou omitidos.

## Autenticação
- Preferencial: `Authorization: Bearer <TOKEN>`
- Alternativa: header `X-Api-Key: <TOKEN>`
- HTTPS obrigatório

## Endpoints que o DropNexo chama (na sua API)

### `GET /v1/products`
Query: `cursor`, `updated_since` (ISO-8601), `limit`

```json
{ex.dumps(ex.LISTA_PRODUTOS)}
```

### `GET /v1/products/{{sku}}`
Retorna **um** produto (objeto único) no mesmo formato do item.

```json
{ex.dumps(ex.PRODUTO_COMPLETO)}
```

### `GET /v1/stock`
Query: `cursor`, `updated_since`, `sku`

```json
{ex.dumps(ex.LISTA_ESTOQUE)}
```

### `GET /v1/warehouses`
```json
{ex.dumps(ex.LISTA_WAREHOUSES)}
```

## Campos de produto (referência)
**Obrigatórios / fortemente esperados:** `sku`, `nome`, `descricao`, `preco`, `unidade`, `ncm`, `origem_fiscal`, `peso_bruto_kg`, `altura_cm`, `largura_cm`, `profundidade_cm`, imagens (lista ou URLs).

**Opcionais (envie se existir no ERP):** `sku_pai`, `nome_variacao`, `atributos`, `external_id`, `preco_promocional`, `preco_custo`, `valor_atacado`, `valor_dropshipping`, `quantidade`, `gtin`, `cest`, `condicao`, `marca`, `grupo`, `categoria`, `peso_liquido_kg`, `peso_gramas`, `dimensao_caixa_cm`, `volumes`, `moq`, `prazo_envio_dias`, `frete_gratis`, `reposicao_estoque`, `producao`, `publicado`, `garantia_tipo`, `garantia_tempo`, `video_youtube`, `cfop`, `icms_situacao`, `pis_situacao`, `cofins_situacao`, `warehouses[]`, `updated_at`.

**Variação:** `sku_pai` + `atributos` (objeto ou `Cor=Azul;Tamanho=M`).

## Regras
- **SKU** é a chave estável (não pode mudar).
- Paginação com `next_cursor`; sync incremental com `updated_since`.
- Imagens em URL pública HTTPS.
- Homologação → checklist → aprovação DropNexo → produção.

## Capacidades no DropNexo
- Produtos: cadastrar / atualizar
- Estoque: atualizar
- Pedidos: enviar ao ERP / troca de status *(em expansão)*

## Homologação → produção
1. Começa em **homologação**
2. Configure URL + token, teste e sincronize
3. **Solicitar produção** (checklist: warehouses, products, stock)
4. DropNexo **aprova** ou **reprova**
5. Parceiro **não** promove sozinho

## Webhook do parceiro (DropNexo → vocês)
`POST` JSON. Header `X-DropNexo-Signature: sha256=<hmac>`. Responda `2xx`.

Status vendedor: {", ".join(ex.STATUS_VENDEDOR)}  
Origens: {", ".join(ex.ORIGENS_PEDIDO)}

### `order.created`
```json
{ex.dumps(ex.ORDER_CREATED)}
```

### `order.status_changed`
```json
{ex.dumps(ex.ORDER_STATUS_CHANGED)}
```

### `order.canceled`
```json
{ex.dumps(ex.ORDER_CANCELED)}
```

## Token DropNexo
Gerado no card (valor completo só uma vez).

## Boas práticas
1. Homologação → checklist → aprovação → produção
2. Rate limit razoável e JSON UTF-8
3. Logs com SKU/pedido
"""


def prompt_para_ai() -> str:
    return f"""Você vai construir uma API REST para integrar o ERP do fornecedor com o DropNexo.

Objetivo: DropNexo consome GET produtos/estoque; envia pedidos via webhook.

Implemente endpoints e payloads EXATAMENTE no formato abaixo (todos os campos; opcionais podem ser null).

### GET /v1/products
{ex.dumps(ex.LISTA_PRODUTOS)}

### GET /v1/products/{{sku}}
{ex.dumps(ex.PRODUTO_COMPLETO)}

### GET /v1/stock
{ex.dumps(ex.LISTA_ESTOQUE)}

### GET /v1/warehouses
{ex.dumps(ex.LISTA_WAREHOUSES)}

### Webhook order.created
{ex.dumps(ex.ORDER_CREATED)}

### Webhook order.status_changed
{ex.dumps(ex.ORDER_STATUS_CHANGED)}

### Webhook order.canceled
{ex.dumps(ex.ORDER_CANCELED)}

Auth: Bearer ou X-Api-Key. HTTPS. next_cursor. HMAC header X-DropNexo-Signature.
SKU é chave. Variações: sku_pai + atributos.
Homologação primeiro; produção só após checklist e aprovação DropNexo.
Entregue OpenAPI + curl de teste.
"""


def painel_docs() -> dict:
    return {
        "titulo": "Documentação API Externa",
        "versao": "1.2",
        "markdown": documentacao_markdown(),
        "prompt_ai": prompt_para_ai(),
        "html_path": "/ajuda/api-externa",
        "exemplos": {
            "products": ex.LISTA_PRODUTOS,
            "product": ex.PRODUTO_COMPLETO,
            "stock": ex.LISTA_ESTOQUE,
            "warehouses": ex.LISTA_WAREHOUSES,
            "order_created": ex.ORDER_CREATED,
            "order_status_changed": ex.ORDER_STATUS_CHANGED,
            "order_canceled": ex.ORDER_CANCELED,
        },
    }


def contexto_html() -> dict:
    return {
        "json_products": ex.dumps(ex.LISTA_PRODUTOS),
        "json_product": ex.dumps(ex.PRODUTO_COMPLETO),
        "json_stock": ex.dumps(ex.LISTA_ESTOQUE),
        "json_warehouses": ex.dumps(ex.LISTA_WAREHOUSES),
        "json_order_created": ex.dumps(ex.ORDER_CREATED),
        "json_order_status": ex.dumps(ex.ORDER_STATUS_CHANGED),
        "json_order_canceled": ex.dumps(ex.ORDER_CANCELED),
        "status_vendedor": ", ".join(ex.STATUS_VENDEDOR),
        "origens_pedido": ", ".join(ex.ORIGENS_PEDIDO),
    }
