# 📘 PADRÃO INSTITUCIONAL  
## Uso de Classes Globais e Captura por Classe  
### BARACAT Gestão Empresarial

**Versão:** 1.0  
**Status:** Norma institucional obrigatória  
**Escopo:** HTML, CSS e JavaScript de telas e scripts do sistema BARACAT

---

## 1️⃣ Objetivo deste documento

Este documento define o **padrão oficial e obrigatório** para:

- uso das classes definidas no `global_utils.css`
- criação de elementos HTML institucionais
- captura e manipulação de elementos via JavaScript
- prevenção de duplicação de CSS
- garantia de previsibilidade visual e comportamental

📌 Este arquivo deve ser considerado **fonte da verdade** pelo sistema **GPT-BARACAT** ao gerar ou revisar qualquer script, HTML ou orientação técnica.

---

## 2️⃣ Princípio fundamental (regra-mãe)

> **Se existe classe no CSS global para um elemento, ela DEVE ser usada.**

Consequências diretas:

- ❌ Nunca recriar CSS para componentes já padronizados
- ❌ Nunca inventar novas classes para componentes institucionais
- ❌ Nunca estilizar componentes institucionais via `style=""`
- ❌ Nunca sobrescrever comportamento visual global em CSS local

O CSS global é **a fonte da verdade visual**.

---

## 3️⃣ Separação clara de responsabilidades

### CSS Global
- Define aparência
- Define estados visuais (hover, focus, disabled, print, acessibilidade)
- Define identidade institucional

### HTML da Tela
- Apenas **estrutura**
- Usa **classes globais existentes**
- Não cria variações visuais

### JavaScript da Tela
- Controla **comportamento**
- Captura elementos por:
  - classes institucionais
  - `data-*`
  - IDs apenas quando o elemento é único

---

## 4️⃣ Padrão obrigatório de captura no JavaScript

### 4.1 Regra geral
- O JS **nunca depende de CSS local**
- O JS **nunca depende de estrutura frágil** (`div > div:nth-child(3)`)

### 4.2 Hierarquia de captura (ordem correta)
1. `data-*` (ações)
2. classe institucional (`.Cl_*`)
3. classe semântica da tela (`.btnEditar`, `.btnExcluir`)
4. ID (somente para elementos únicos)

### 4.3 Exemplo conceitual
```html
<button class="Cl_BtnAcao btnEditar" data-id="123"></button>
```

O CSS vem de .Cl_BtnAcao.
O comportamento vem de .btnEditar ou data-id.

## 5️⃣ Componentes institucionais e classes obrigatórias
### 5.1 Painel de filtros
Classes obrigatórias:
- .filter-panel
- .filter-panel-fields
- .filter-group
- .filter-panel-actions
📌 Existem variações visuais institucionais do filtro.
❗ O HTML não muda — apenas o CSS global define o visual.

❌ Nunca criar painel de filtro customizado.

### 5.2 Tabela de dados
Classe obrigatória:
- .Cl_TabelaPrincipal
- Recursos já cobertos pelo CSS global:
- bordas
- zebra striping
- hover
- ellipsis
- tooltip via title
- modo print

Classes auxiliares:
- .no-ellipsis
- .Cl_Cell
❌ Nunca recriar CSS de tabela.

### 5.3 Coluna de ações (ícones)
Classes obrigatórias:
- .Cl_BtnAcao
- .icon-tech
- opcional: .btn-icon
Regras:
- Ícones sem texto
- Ícones gerados exclusivamente via Util.gerarIconeTech()
- CSS define cor, hover e tamanho
❌ Proibido usar <i data-lucide> direto no HTML da tela.

### 5.4 Paginação
Classes obrigatórias:
- .Cl_Paginacao
- .Cl_direcao
O CSS global já controla:
- hover
- disabled
- alinhamento
- responsividade
❌ Nunca estilizar paginação por tela.

### 5.5 Botões institucionais
Classes globais disponíveis:
- .Cl_botaoprimario
- .Cl_botaoFiltro
- .Cl_BtnIncluir
- .Cl_BtnSalvar
- .Cl_BtnExcluir
- .Cl_BtnCancelar
- .Cl_BotoesApoio
- .btn-secundario
📌 O uso correto da classe define automaticamente:
- cor
- hover
- foco
- sombra
-comportamento no print

### 5.6 Switch (liga/desliga)
Classes obrigatórias:
- .Cl_Switch
- .Cl_SwitchSlider
- .Cl_SwitchGroup
- .Cl_SwitchLabel
❌ Nunca criar switch customizado.

### 5.7 Modal de apoio (iframe)
Regras absolutas:
- Abrir somente via GlobalUtils.abrirJanelaApoioModal
- Fechar somente via GlobalUtils.fecharJanelaApoio
- Comunicação via postMessage
Classes CSS institucionais:
- .apoio-overlay
- .apoio-janela
- .apoio-iframe
❌ Nunca criar modal próprio por tela.

### 5.8 Combobox personalizada (ComboBusca)
Regras:
❌ Nunca usar <select>
HTML deve usar exatamente:
- .Cl_SelectLike
- .Cl_SelectDisplay
- .Cl_Caret
- .Cl_ComboPanel
- .Cl_ComboSearch
- .Cl_ComboLista
- .Cl_Item, .Cl_Item__linha, .Cl_Item__rotulo
Inicialização obrigatória:
Util.combobox_personalisado({...})

📌 Todo visual, highlight, foco e floating já estão no CSS global.

## 6️⃣ SweetAlert (alertas)
Regras:
- Sempre usar o SweetAlert já configurado no global
- Nunca alterar ordem, cores ou layout dos botões
- Confirmar sempre à esquerda, cancelar à direita (padrão global)
❌ Nunca instanciar SweetAlert “cru”.

## 7️⃣ Scrollbars, acessibilidade e print
Já tratados no CSS global:
- scrollbars institucionais
- prefers-reduced-motion
- regras de impressão
❌ Nunca sobrescrever scrollbar por tela
❌ Nunca esconder botões manualmente para print

## 8️⃣ Quando CSS local é permitido
✅ Permitido:
- largura de colunas
- alinhamento de colunas
- ocultar coluna específica
- ajustes estruturais de layout da página
❌ Proibido:
- redefinir cor, borda, hover ou sombra de componentes institucionais
- duplicar estilos já existentes no global

## 9️⃣ Checklist obrigatório (para humano e GPT)
Antes de gerar ou aceitar um script:
- Existe classe global para esse elemento?
- A classe global está sendo usada?
- O JS captura por classe ou data-*?
- Não existe CSS duplicado?
- Nenhum style="" foi usado?
- Modal e combobox usam apenas APIs globais?
- O visual depende exclusivamente do CSS institucional?
Se qualquer resposta for não, o código não está conforme o padrão BARACAT.