# Integração Bling — DropNexo

Documento de referência para a integração OAuth multi-tenant com o ERP Bling (API v3).

## Objetivo

Cada **tenant** conecta sua própria conta Bling. Fornecedor e vendedor usam o mesmo conector, com configuração e escopo independentes por contexto.

## Entidades

| Entidade | Fornecedor | Vendedor | Fases |
|----------|------------|----------|-------|
| Produtos | `tbl_produto` | `tbl_produto` (catálogo próprio) | Sprint 1 (importar) |
| Estoque | `tbl_produto_variante_estoque` × depósitos | idem | Sprint 2 |
| Pedidos | `tbl_pedido` B2B | pedidos Bling | Sprint 4 (após módulo pedidos) |

## Modos de sync (por entidade e contexto)

- **importar** — Bling → DropNexo  
- **exportar** — DropNexo → Bling  
- **atualizar** — bidirecional (última alteração vence no MVP)

## Imagens

| Modo | Comportamento |
|------|----------------|
| **link** | URL gravada em `tbl_produto_imagem.caminho` |
| **download** | Arquivo em `upload/tenant{id}/produtos/{sku}/{ordem}-{nome}.ext` |

Regras:

- Máximo **3 MB** por imagem na importação.
- **SKU obrigatório** — produto sem SKU não sincroniza.
- Não misturar link e arquivo no mesmo produto (regra do catálogo).
- **Dev:** arquivos locais `upload/...` exibem ícone placeholder; links externos exibem normalmente.
- **Produção:** servir arquivos via rota dedicada (validar depois).

## OAuth Bling

1. App cadastrado em [developer.bling.com.br](https://developer.bling.com.br/aplicativos).
2. Redirect URI: `{BASE}/api/integracoes/bling/oauth/callback`
3. Authorize: `GET https://www.bling.com.br/Api/v3/oauth/authorize`
4. Token: `POST https://www.bling.com.br/Api/v3/oauth/token`
5. Tokens por tenant, criptografados com derivado de `SECRET_KEY`.
6. Refresh token rotacionado a cada renovação.

### Variáveis `.env`

```
BLING_CLIENT_ID=
BLING_CLIENT_SECRET=
```

### Manual público (cadastro Bling)

- URL: `{BASE}/ajuda/bling`
- Rota: `GET /ajuda/bling` (página pública, sem login)

## Modelo de dados

| Tabela | Uso |
|--------|-----|
| `tbl_integracao_bling` | Conexão OAuth por tenant |
| `tbl_integracao_bling_config` | Config por contexto (`fornecedor` / `vendedor`) |
| `tbl_integracao_map` | Mapa `id_bling` ↔ `id_dropnexo` |
| `tbl_integracao_log` | Histórico de sync |
| `tbl_integracao_deposito_map` | Pareamento depósitos (Sprint 2) |

## Rotas

| Rota | Descrição |
|------|-----------|
| `GET /integracoes/bling` | Tela de configuração |
| `GET /api/integracoes/bling/status` | Status + config |
| `GET /api/integracoes/bling/oauth/iniciar` | Redireciona ao Bling |
| `GET /api/integracoes/bling/oauth/callback` | Callback OAuth |
| `POST /api/integracoes/bling/desconectar` | Revoga conexão |
| `POST /api/integracoes/bling/config/salvar` | Salva flags |
| `POST /api/integracoes/bling/sync/produtos` | Sync manual produtos |
| `GET /api/produto-imagem/arquivo` | Serve imagem local `upload/...` |

## Fases de implementação

### Sprint 1 (atual)
- OAuth + tela Bling + importar produtos + imagens (link/download)

### Sprint 2
- Pareamento multi-depósito + sync estoque

### Sprint 3
- Exportar/atualizar produtos + URLs públicas para exportação de imagens

### Sprint 4
- Pedidos (import/export/atualizar) após módulo B2B

## Decisões validadas

1. Limite imagem: **3 MB**
2. SKU: **obrigatório**
3. Vendedor e fornecedor: mesmas opções importar/exportar/atualizar
4. Dev: placeholder para arquivos locais; sem URL pública em homologação
