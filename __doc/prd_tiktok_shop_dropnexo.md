# DropNexo — Integração TikTok Shop (PRD / Documento de Design)

**Produto:** DropNexo  
**Módulo:** Integrações (vendedor)  
**Canal:** TikTok Shop (vendedores locais — Brasil)  
**Versão do documento:** 1.0  
**Data:** 14/07/2026  

---

## 1. Visão geral

O DropNexo é uma plataforma B2B de dropshipping que conecta **vendedores** a **fornecedores**. A integração TikTok Shop permite que o vendedor:

1. Conecte a loja TikTok Shop via OAuth (Partner App)
2. Publique ou vincule produtos a partir de **Meus produtos**
3. Sincronize estoque DropNexo → TikTok Shop
4. Importe pedidos pagos para o painel de **Pedidos**
5. Sincronize cancelamentos/devoluções
6. Atualize status de envio (expedido/entregue) e baixe etiqueta quando disponível

O objetivo é eliminar retrabalho manual entre a TikTok Shop e a operação de dropshipping no DropNexo.

---

## 2. Escopo do serviço

| Item | Detalhe |
|------|---------|
| Público | Vendedores locais Brasil (TikTok Shop) |
| Tipo de app | Partner / Open API |
| Multi-tenant | Sim — cada vendedor (tenant) autoriza a própria loja |
| Fora do escopo | Chat, live analytics, promoções/cupons, extrato financeiro |

---

## 3. Fluxo de dados

```
[Vendedor DropNexo]
        |
        | OAuth (auth.tiktok-shops.com)
        v
[tbl_integracao_tiktok]  ← tokens, shop_id, flags
        |
        +-- Produtos --> API Product --> tbl_integracao_map (provedor=tiktok)
        |
        +-- Estoque  --> API Stock   --> eco anti-loop (tbl_integracao_tiktok_eco_estoque)
        |
        +-- Pedidos  --> Webhook/Sync Order API --> tbl_pedido (origem=tiktok)
        |
        +-- Envio    --> Fulfillment / Delivery Status API
```

### 3.1 Autorização
1. Vendedor clica **Conectar loja** em Integrações → TikTok Shop  
2. Redireciona para OAuth TikTok com `app_key` + `redirect_uri`  
3. Callback DropNexo troca `code` por `access_token` / `refresh_token`  
4. Sistema grava tokens cifrados e dados da loja (`shop_id`, `shop_cipher`)

**Redirect URI:** `https://dropnexo.com.br/api/integracoes/tiktok/oauth/callback`  
**Webhook:** `https://dropnexo.com.br/api/integracoes/tiktok/webhook`

### 3.2 Produtos
- Origem: vitrine do vendedor (`Meus produtos`)
- Modos: **criar anúncio** ou **vincular por SKU**
- Mapeamento de categoria DropNexo → category_id TikTok
- Vínculo salvo em `tbl_integracao_map` (`product_id` / `sku_id`)

### 3.3 Estoque
- Push automático quando estoque/preço muda (se flag ativa)
- Sync manual em Integrações → Estoque
- Tabela de eco evita loop de feedback

### 3.4 Pedidos
- Importação automática via webhook (se flag ativa)
- Sync manual: buscar pedidos recentes
- Somente itens já vinculados ao DropNexo
- Pedido criado com `origem = tiktok`, status importado, estoque reservado
- Cancelamento/devolução cancela o pedido local

### 3.5 Fulfillment
- Ao marcar **expedido** / **entregue** no DropNexo → atualiza status na TikTok Shop
- Botão **Baixar etiqueta TikTok** no pedido (quando a API liberar o documento)

---

## 4. Principais recursos

### Pedidos
1. Sincronização / importação de pedidos  
2. Webhook de mudança de status  
3. Cancelamento e devolução  
4. Atualização de envio (expedido/entregue)  
5. Etiqueta / logística  

### Produto
1. Criação de anúncio  
2. Atualização de anúncio (preço, estoque, dados)  
3. Vínculo por SKU  
4. Mapeamento de categorias  

### Estoque
1. Sincronização automática DropNexo → TikTok  
2. Sincronização manual  

---

## 5. Casos de uso principais

### UC1 — Conectar loja
**Ator:** Vendedor  
**Fluxo:** Integrações → TikTok Shop → Conectar → autorizar no TikTok → status Conectado  

### UC2 — Publicar / vincular produtos
**Ator:** Vendedor  
**Fluxo:** Meus produtos → selecionar itens → Integrar TikTok Shop → criar ou atualizar anúncios  

### UC3 — Receber pedido
**Ator:** Sistema + Vendedor  
**Fluxo:** Pedido pago na TikTok Shop → webhook/sync → pedido aparece em Pedidos DropNexo → fornecedor atende  

### UC4 — Enviar e concluir
**Ator:** Vendedor / fornecedor  
**Fluxo:** Pedido expedido/entregue no DropNexo → status enviado à TikTok Shop; etiqueta baixável quando disponível  

### UC5 — Cancelamento
**Ator:** Sistema  
**Fluxo:** Cancelamento/devolução na TikTok Shop → pedido local cancelado e estoque ajustado  

---

## 6. Escopos de API utilizados

| Escopo | Finalidade |
|--------|------------|
| Shop Authorized Information | Identificar loja autorizada |
| Global Shop Information | Dados da loja |
| Product Basic | Leitura de produtos |
| Product Modify | Criar/atualizar anúncios e estoque |
| Order Information | Importar pedidos e dados de entrega |
| Fulfillment Basic | Pacotes / fulfillment |
| Logistics Basic | Logística / etiqueta |
| Update Delivery Status | Expedido / entregue |
| Return & Refund Basic | Devolução / cancelamento |

---

## 7. Instruções de teste (para revisores)

1. Acesse `https://dropnexo.com.br` com a conta de teste fornecida.  
2. Vá em **Integrações → TikTok Shop → Conectar loja** e autorize o app.  
3. Em **Meus produtos**, selecione itens e use **Integrar TikTok Shop**.  
4. Em **Integrações → TikTok Shop → Pedidos**, ative importação automática e clique **Buscar pedidos recentes**.  
5. Abra **Pedidos** no DropNexo, confira o pedido importado e marque expedido/entregue para validar o envio de status.  

**Contato suporte para revisão:** hazael@h74.com.br  

---

## 8. Segurança e privacidade

- Tokens OAuth armazenados cifrados por tenant  
- Acesso às telas de integração exige login e permissão  
- Dados de pedido (PII) usados apenas para fulfillment dropshipping  
- Webhook em HTTPS público  

---

## 9. Arquitetura técnica (resumo)

| Camada | Local |
|--------|--------|
| UI Integrações | `/integracoes/tiktok` |
| UI Meus produtos | ação em lote Integrar TikTok Shop |
| UI Pedidos | origem `tiktok`, etiqueta |
| API | `api/tiktok/` (OAuth, product, stock, orders, webhook) |
| Banco | `tbl_integracao_tiktok`, maps, eco estoque, `tbl_pedido.id_tiktok_pedido` |

---

*Documento preparado para submissão no TikTok Shop Partner Center — análise do aplicativo / PRD.*
