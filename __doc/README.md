# Documentação DropNexo

Índice oficial da pasta `__doc`. Use estes arquivos como **fonte da verdade** ao construir telas, APIs e roadmap.

| # | Arquivo | Uso |
|---|---------|-----|
| **00** | [Plano Mestre de Construção](./00%20-%20Plano%20Mestre%20de%20Construção%20-%20DropNexo.md) | Visão, roadmap, arquitetura, fases de execução, critérios de aceite |
| **01** | [Uso do Modal (BARACAT)](./01-%20Uso%20do%20Modal(BARACAT).md) | Abrir/fechar apoios via `GlobalUtils` |
| **02** | [Uso do ícone (BARACAT)](./02%20-%20Uso%20do%20icone(BARACAT).md) | Ícones via `Util.gerarIconeTech` |
| **03** | [Tela principal — Modelo BARACAT](./03%20-%20Criando%20tela%20principal-Modelo%20BARACAT.md) | Listagens, filtros, tabela, Hub JS |
| **04** | [Tela de apoio — Padrão BARACAT](./04%20-%20Criando%20tela%20de%20apoio%20-%20Padrão%20Baracat.md) | Incluir/editar em modal iframe |
| **05** | [Classes globais BARACAT](./05%20-%20Padrão%20Uso%20de%20Class%20Globais%20BARACAT.md) | CSS/JS institucional, sem duplicar estilo |
| — | [Combobox personalizada](./Combobox%20Personalizada.md) | ComboBusca remota |

**Referência de implementação (somente leitura):** `OLD/HUBSUPPORT/` (ex-HubSupport).

**Código ativo:** raiz do projeto — pastas `fornecedor/`, `vendedor/`, `sistema/`, `api/`, `templates`, `static` (migração em curso a partir de `modulos/`).

**Tipos de tenant:** cadastro público só `fornecedor` ou `vendedor`; evolução para `hibrido` documentada em [Plano Mestre §6.3.1](./00%20-%20Plano%20Mestre%20de%20Construção%20-%20DropNexo.md#631-tipo_negocio-do-tenant-ciclo-de-vida).
