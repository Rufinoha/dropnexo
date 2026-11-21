# API do Assistente DropNexo

Base: `/api/v1/assistente`  
Auth: `Authorization: Bearer dn_assist_…` (token gerado em **Configurações → Manutenção de tenant → Fornecedor Fundador**).  
Escopo: somente fornecedores (`fornecedor` / `hibrido`). Escrita só em fase e contatos. Fornecedor indicado → `403` na escrita.

## Autenticação

```http
GET /api/v1/assistente/resumo
Authorization: Bearer dn_assist_xxxxxxxx
```

Token inválido/revogado → `401`. Rate limit ~60 req/min → `429`.

---

## GET `/fornecedores`

Query: `page`, `per_page`, `fundador=0|1`, `fase`, `indicado=0|1`, `desde` (ISO).

```json
{
  "success": true,
  "page": 1,
  "per_page": 50,
  "total": 10,
  "pages": 1,
  "itens": [
    {
      "id": 3828,
      "nome": "Empresa Exemplo",
      "documento": "00.000.000/0001-00",
      "cidade": "São Paulo",
      "uf": "SP",
      "criado_em": "2026-10-01T12:00:00+00:00",
      "ultimo_acesso_em": "2026-11-20T18:00:00+00:00",
      "plano": "enterprise",
      "eh_fundador": true,
      "fundador_ativo": true,
      "fundador_em": "2026-10-01T12:05:00+00:00",
      "prazo_ativacao": "2026-10-15T12:05:00+00:00",
      "sistema_erp": "Bling",
      "indicado_por": null,
      "fase": "cadastrado",
      "fase_em": "2026-10-01T12:05:00+00:00",
      "ultimo_contato": { "data": "…", "canal": "whatsapp", "resumo": "…" },
      "whatsapp": "5511999999999",
      "email": "dono@empresa.com",
      "triagem": { "fabrica": "sim", "skus": "11_50", "revende": "sim" },
      "resumo": {
        "produtos_publicados": 12,
        "produtos_total": 20,
        "pedidos_30d": 3,
        "pedidos_atrasados": 0,
        "vendedores_conectados": 2,
        "vendedores_aguardando": 1
      }
    }
  ]
}
```

---

## GET `/fornecedores/<id>`

Raio-x: `cadastro`, `produtos`, `pedidos`, `desempenho`, `rede` (só contagens), `integracoes`, `acompanhamento`, `resumo`.

---

## GET `/fornecedores/<id>/produtos`

Query: `status=incompleto|inativo|publicado`, `page`, `per_page`.

```json
{
  "success": true,
  "itens": [
    {
      "id": 10,
      "sku": "ABC",
      "nome": "Produto",
      "preco": 19.9,
      "estoque": null,
      "publicado": false,
      "motivos": ["sem foto", "sem estoque"],
      "atualizado_em": "…"
    }
  ],
  "page": 1,
  "per_page": 50,
  "total": 1
}
```

---

## GET `/fornecedores/<id>/pedidos`

Query: `status`, `atrasados=1`, `desde`, `page`. Sem dados pessoais do comprador final além de cidade/UF quando disponíveis.

---

## GET `/resumo`

```json
{
  "success": true,
  "por_fase": { "cadastrado": 4, "ativo": 2, "sem_fase": 3 },
  "fundadores": { "ativos": 10, "vagas_max": 15, "vagas_restantes": 5 },
  "fornecedores_catalogo_lt_20": 7,
  "fornecedores_com_vendedores_aguardando": 3
}
```

---

## POST `/fornecedores/<id>/contato`

```json
{
  "canal": "whatsapp",
  "direcao": "enviado",
  "resumo": "Pedimos publicação dos primeiros 20 produtos",
  "fase_apos": "boas_vindas",
  "aprovado_por": "Hazael"
}
```

Autor gravado: `Assistente` ou `Assistente (aprovado por Hazael)`.  
Indicado → `403`.

---

## POST `/fornecedores/<id>/fase`

```json
{ "fase": "lembrete", "motivo": "Sem resposta há 5 dias" }
```

Indicado → `403`.

---

## Privacidade

- Nenhum endpoint devolve nome/e-mail/telefone/documento de **vendedores**.
- Rede: apenas contagens.
- Pedidos: sem comprador final além de cidade/UF.
- A API **não** altera produto, pedido, preço, estoque, plano nem status de Fundador.
