# DropNexo

Marketplace B2B de distribuição digital — ecossistema **H74 HUB**.

## Subir localmente

1. Copie `.env.example` para `.env` e configure `DB_PASSWORD_DEV` (+ Brevo se for testar e-mail).
2. Crie banco, tabelas, perfis e usuário DEV: `python scripts/bootstrap_db.py`
3. Instale dependências: `pip install -r requirements.txt`
4. Execute: `python app.py`
5. Acesse: `http://127.0.0.1:5260`

## Cadastro

- Home: escolha **Fornecedor** ou **Vendedor**.
- Formulário: `/cadastro?tipo=fornecedor` ou `?tipo=vendedor`.
- Ativação: e-mail com link `/definir-senha?token=...`

Documentação completa: `__doc/00 - Plano Mestre de Construção - DropNexo.md`

## Estrutura de pastas

**Raiz:**

- `app.py` — bootstrap Flask + registro de APIs e módulos
- `global_utils.py` — infra (DB, auth, permissões, marca)
- `templates/`, `static/` — globais (frm_base, home, login…)

**`core/`** — domínio compartilhado (fornecedor + vendedor):

- `core/pedidos/servico.py` — pedidos B2B, status, importação Bling
- `core/pedidos/estoque_reserva.py` — reserva/baixa de estoque
- `core/pedidos/meios_pagamento.py` — facade MP + PIX manual
- `core/categorias.py` — árvore de categorias
- `core/vinculos.py` — vínculo vendedor × fornecedor
- `core/cnpj.py` — consulta CNPJ

**`sistema/`** — plataforma:

- `sistema/acesso/srotas.py` — home pública, login, cadastro
- `sistema/plataforma/sessao.py` — módulo ativo, usuários por tenant
- `sistema/integracoes/srotas_integracoes.py` — catálogo do hub de integrações
- demais features em `sistema/<feature>/srotas_*.py`

**`api/`** — integrações externas (OAuth, webhook, sync); cada provedor em `api/<nome>/` com módulo de domínio + `srotas_*.py` (ex.: `api/pix_manual/pix_manual.py`, `api/mercadopago/mercadopago.py`, `api/melhor_envio/melhor_envio.py`, `api/mercado_livre/mercado_livre.py`).

**`core/`** — domínio compartilhado (`pedidos/servico.py`, `dominio.py`, `tokens.py`).

**`core/pedidos/servico.py`** — pedidos B2B, reserva de estoque e meios de pagamento (seções `# ──`).

**`core/dominio.py`** — categorias, consulta CNPJ e vínculos vendedor×fornecedor.

**`api/bling/`** — integração Bling (módulos por domínio, seções `# ──` dentro de cada arquivo):

| Arquivo | Responsabilidade |
|---------|------------------|
| `cliente.py` | OAuth, tokens API, HTTP |
| `config.py` | defaults, conta empresa, eco estoque |
| `campos.py` | parse produto + pedido |
| `produtos.py` | imagens, importação e exportação de produtos |
| `pedidos.py` | importação, exportação e status de pedidos |
| `estoque.py` | depósitos e sincronização de estoque |
| `categorias_bling.py` | sync e mapeamento de categorias |
| `webhooks.py` | estoque + pedidos |
| `sync_progresso.py` | jobs assíncronos (produtos, estoque, categorias) |
| `homologacao.py` | homologação + manual público |
| `srotas_bling.py` | rotas HTTP |

(`tokens.py` de OAuth ficou em `core/tokens.py`, compartilhado entre integrações.)

**`fornecedor/`, `vendedor/`** — módulos de negócio (telas + rotas por feature). Serviços agrupados quando pequenos (ex.: `vendedor/meus_produtos/servico_meus_produtos.py`, `fornecedor/importacao/servico_importacao.py`, `fornecedor/catalogo/catalogo.py`, `fornecedor/parametros/precificacao.py`).

**Cada feature (`fornecedor/categorias/`, `vendedor/catalogo/`, …):**

- `srotas_<feature>.py` — blueprint + rotas + `init_app`
- `templates/`, `static/` — assets locais

Serviços de domínio ficam em `core/` ou na pasta da feature; orquestração com ERP/pagamento/frete fica em `api/<provedor>/` (módulo unificado por integração). Detalhes: `__doc/00 - Plano Mestre…` §6.4.
