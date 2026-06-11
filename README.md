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

- `app.py` — bootstrap + auto-registro de `srotas_*.py`
- `global_utils.py` — infra (DB, auth, permissões, marca)
- `srotas_acesso.py` — home pública, login, cadastro
- `srotas_plataforma.py` — navegação (módulo fornecedor/vendedor) e usuários por tenant
- `srotas_negocio.py` — categorias, precificação/vínculos e hub de integrações
- `templates/`, `static/` — globais (frm_base, home, login…)
- `fornecedor/`, `vendedor/`, `sistema/` — módulos de negócio
- `api/` — brevo, efi, whatsapp

**Cada feature (`fornecedor/categorias/`, `vendedor/catalogo/`, …):**

- `srotas_<feature>.py` — **único** arquivo Python (blueprint + rotas + `init_app`)
- `templates/`, `static/` — assets locais

Sem `__init__.py`. Detalhes: `__doc/00 - Plano Mestre…` §6.4.
