# API do Assistente DropNexo

Base: `/api/v1/assistente`  
Auth: `Authorization: Bearer dn_assist_…` (token gerado em **Configurações → Manutenção de tenant → Fornecedor Fundador → Token do Assistente**, só para desenvolvedor/admin da plataforma).  
Escopo: somente fornecedores (`tipo_negocio` = `fornecedor` ou `hibrido`). Escrita só em **fase** e **contatos**. Fornecedor indicado por parceiro → `403` na escrita (leitura continua liberada).

Migração: `sql/24_assistente_token.sql` (espelho em `__doc/sql/065_assistente_token.sql`). Nenhum DDL é executado em tempo de requisição.

## Autenticação e limites

```http
GET /api/v1/assistente/resumo
Authorization: Bearer dn_assist_xxxxxxxx
```

- Token ausente, inválido ou revogado → `401`.
- Rate limit ~60 req/min por token → `429`.
- Cada chamada é registrada em `tbl_assistente_auditoria` (rota, método, data, IP, `token_hint`, status).
- Erros sempre genéricos:

```json
{ "success": false, "message": "Token ausente ou inválido." }
```

O token é exibido **uma única vez** na geração; só o hash SHA-256 fica no banco (`token_hint` = primeiros 4 … últimos 4 caracteres).

---

## GET `/fornecedores`

Query: `page`, `per_page` (máx. 100), `fundador=0|1`, `fase`, `indicado=0|1`, `desde` (ISO 8601, filtra `criado_em`).

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
      "prazo_ativacao_cor": "amarelo",
      "sistema_erp": "Bling",
      "indicado": false,
      "fase": "cadastrado",
      "fase_em": "2026-10-01T12:05:00+00:00",
      "fase_rotulo": "Cadastrado",
      "ultimo_contato": { "data": "2026-11-18T10:00:00+00:00", "canal": "whatsapp", "resumo": "Boas-vindas enviadas" },
      "whatsapp": "5511999999999",
      "email": "dono@empresa.com",
      "triagem": { "fabrica": "sim", "skus": "11_50", "revende": "sim", "mesmo_assim_fornecedor": false },
      "triagem_rotulo": "fabrica/estoque: sim · SKUs: 11–50 · revende: sim",
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

`whatsapp` / `email` são do **fornecedor** (dono). Nunca de vendedores.

---

## GET `/fornecedores/<id>`

Raio-x completo.

```json
{
  "success": true,
  "cadastro": { "id": 3828, "nome": "…", "documento": "…", "cidade": "…", "uf": "SP", "plano": "…",
                "ativo": true, "eh_fundador": true, "fundador_ativo": true, "fundador_em": "…",
                "prazo_ativacao": { "prazo_rotulo": "15/10/2026", "prazo_cor": "amarelo", "dias_restantes": 3,
                                    "produtos_meta": 20, "produtos_publicados": 12 },
                "sistema_erp": "Bling", "indicado": false, "fase": "cadastrado", "fase_em": "…",
                "whatsapp": "…", "email": "…", "triagem": {}, "triagem_rotulo": "",
                "usuarios": [ { "nome": "…", "perfil": "dono", "perfil_nome": "Dono", "ultimo_acesso_em": "…", "ativo": true } ] },
  "produtos": {
    "total": 20, "publicados": 12, "inativos": 8,
    "incompletos_total": 5,
    "contagem_motivos": { "sem foto": 3, "sem estoque": 2 },
    "incompletos": [ { "id": 10, "sku": "ABC", "nome": "Produto", "motivos": ["sem foto", "sem estoque"] } ]
  },
  "pedidos": {
    "por_status_30d": { "pago": 2, "entregue": 5 },
    "por_status_90d": { "pago": 2, "entregue": 14 },
    "atrasados": [ { "id": 99, "numero": "P-1001", "criado_em": "…", "status": "pago", "status_pagamento": "pago",
                     "valor_centavos": 15990, "pago_em": "…", "expedido_em": null, "entregue_em": null,
                     "atrasado": true, "horas_em_atraso": 30 } ],
    "cancelados_30d": 1,
    "devolvidos_30d": 0
  },
  "desempenho": {
    "30d": { "pedidos": 8, "faturamento_centavos": 450000, "ticket_medio_centavos": 56250 },
    "90d": { "pedidos": 20, "faturamento_centavos": 1200000, "ticket_medio_centavos": 60000 },
    "taxa_cancelamento_30d": 11.1,
    "tempo_medio_pago_expedido_horas": 20.5,
    "ultimo_pedido_em": "…",
    "top_produtos_30d": [ { "sku": "ABC", "nome": "Produto", "quantidade": 12 } ]
  },
  "rede": { "vendedores_conectados": 2, "vendedores_aguardando": 1,
            "aguardando_mais_antigo_dias": 4, "vendedores_com_pedido_30d": 2 },
  "integracoes": [ { "nome": "Bling", "ligado": true, "status": "conectado", "ultima_sincronizacao": "…",
                     "ultimo_erro": "", "fila_imagens_pendentes": 0 } ],
  "acompanhamento": { "fase": "cadastrado", "fase_rotulo": "Cadastrado", "prazo": {},
                      "contatos": [ { "id": 1, "criado_em": "…", "canal": "whatsapp", "direcao": "enviado",
                                       "resumo": "…", "fase_apos": "boas_vindas", "autor": "Assistente" } ] },
  "resumo": { "produtos_publicados": 12, "produtos_total": 20, "pedidos_30d": 8, "pedidos_atrasados": 1,
              "vendedores_conectados": 2, "vendedores_aguardando": 1 }
}
```

Motivos de produto incompleto: `sem preço`, `sem categoria`, `sem descrição`, `sem peso/dimensões`, `sem foto`, `sem estoque`, `sem variação cadastrada`. `incompletos` traz no máximo 50 itens.  
Integrações são *best-effort* (somente as tabelas existentes; sem tokens).

---

## GET `/fornecedores/<id>/produtos`

Query: `status=incompleto|inativo|publicado`, `page`, `per_page`.

```json
{
  "success": true,
  "itens": [
    { "id": 10, "sku": "ABC", "nome": "Produto", "preco": 19.9, "estoque": 0.0,
      "publicado": false, "motivos": ["sem foto", "sem estoque"], "atualizado_em": "…" }
  ],
  "page": 1, "per_page": 50, "total": 1
}
```

---

## GET `/fornecedores/<id>/pedidos`

Query: `status`, `atrasados=1`, `desde` (ISO), `page`, `per_page`.  
Atrasado = pago / aguardando confirmação (ou em expedição sem envio) há mais de 48 h.

```json
{
  "success": true,
  "itens": [
    { "id": 99, "numero": "P-1001", "criado_em": "…", "status": "pago", "status_pagamento": "pago",
      "valor_centavos": 15990, "pago_em": "…", "expedido_em": null, "entregue_em": null,
      "atrasado": true, "horas_em_atraso": 30 }
  ],
  "page": 1, "per_page": 50, "total": 1
}
```

Sem nenhum dado do comprador final nem do vendedor.

---

## GET `/resumo`

```json
{
  "success": true,
  "por_fase": { "cadastrado": 4, "ativo": 2, "sem_fase": 3 },
  "fundadores": { "ativos": 10, "vagas_max": 15, "vagas_restantes": 5 },
  "fornecedores_catalogo_lt_20": 7,
  "fornecedores_com_vendedores_aguardando": 3,
  "pedidos_atrasados_total": 2
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

Resposta `200`:

```json
{ "success": true,
  "contato": { "id": 7, "criado_em": "…", "canal": "whatsapp", "direcao": "enviado",
               "resumo": "…", "fase_apos": "boas_vindas", "autor": "Assistente (aprovado por Hazael)" } }
```

`canal`: whatsapp | email | telefone | outro · `direcao`: enviado | recebido · `resumo` ≤ 500 caracteres.  
Autor gravado: `Assistente` ou `Assistente (aprovado por …)`.  
Fornecedor indicado:

```json
HTTP 403
{ "success": false, "message": "Fornecedor indicado por parceiro: contato não permitido pelo assistente" }
```

---

## POST `/fornecedores/<id>/fase`

```json
{ "fase": "lembrete", "motivo": "Sem resposta há 5 dias" }
```

Resposta `200`:

```json
{ "success": true, "id": 3828, "fase": "lembrete", "fase_em": "2026-11-21T20:00:00+00:00" }
```

Fases: cadastrado, boas_vindas, cadastrando, lembrete, ativo, eh_vendedor, sem_resposta, desistiu. Indicado → `403` (mesma mensagem acima).

---

## Privacidade e garantias

- Nenhum endpoint devolve nome/e-mail/telefone/documento de **vendedores**. Lado vendedor: apenas contagens.
- Pedidos: sem dados do comprador final (nome, contato, endereço) nem identificação do vendedor.
- `indicado` é apenas booleano (não expõe o parceiro indicador).
- A API **não** altera produto, pedido, preço, estoque, plano nem status de Fundador. Únicas escritas: fase, histórico de contato (`tbl_fornecedor_contato`) e auditoria da própria API.
