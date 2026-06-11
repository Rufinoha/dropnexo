# SQL DropNexo

| Arquivo | Conteúdo |
|---------|----------|
| `001_schema_inicial.sql` | Tabelas: perfil, permissão, tenant, usuario, vínculos, e-mail |
| `002_seed_perfis_permissoes.sql` | Perfis (dono, admin, financeiro, vendedor, operador, visualizador) + permissões |

**Instalação automática (recomendado):**

```bash
python scripts/bootstrap_db.py
```

Cria `bd_dropnexo`, aplica os scripts acima e o usuário **DEV** (`eh_desenvolvedor=true`).

## Perfis de acesso (tenant)

| Código | Uso |
|--------|-----|
| `dono` | Dono da conta — todas permissões do tenant |
| `admin` | Administrador operacional |
| `financeiro` | Financeiro e plano |
| `vendedor` | Equipe comercial (busca catálogo/produtos) |
| `operador` | Cadastro de catálogo |
| `visualizador` | Somente leitura (`*.ver`) |

## Desenvolvedor da plataforma

`tbl_usuario.eh_desenvolvedor = TRUE` → **bypass total** do RBAC (testes e suporte).

No código: `usuario_tem_permissao()` e `@exigir_permissao(codigo='...')` em `global_utils.py`.

## Permissões (exemplos)

- `catalogos.ver` / `catalogos.editar`
- `financeiro.ver` / `financeiro.editar`
- `usuarios.editar` (equipe)
- `plataforma.dev` (reservado; só dev real)
