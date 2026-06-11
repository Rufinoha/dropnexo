# TEMPLATE CANÔNICO — TELA PRINCIPAL BARACAT

Este arquivo define o **padrão oficial e canônico** para criação de **telas principais de negócio** no sistema BARACAT.

O conteúdo abaixo **não é documentação didática**.  
Ele existe para **fixar padrão estrutural, semântico e comportamental**, tanto para humanos quanto para o **GPT-BARACAT**.

⚠️ Alterações neste padrão devem ser **intencionais**.

---

## 1️⃣ TEMPLATE HTML — TELA PRINCIPAL

Regras implícitas neste exemplo:
- Tela principal **SEMPRE** estende `frm_base.html`
- ❌ Nunca recriar `<html>`, `<head>` ou `<body>`
- CSS e JS específicos são carregados via blocos
- Conteúdo de negócio fica somente em `{% block content %}`

```html
{% extends "frm_base.html" %}

{% block title %}Gestão de Entidades{% endblock %}

{% block css_especifico %}
<link rel="stylesheet" href="{{ url_for('modulo.static', filename='css/modulo.css') }}">
{% endblock %}

{% block content %}
<div class="page-container">

  <div class="page-title">
    <h2>Gestão de Entidades</h2>
  </div>

  <!-- Painel de filtros -->
  <div class="filter-panel">

    <div class="filter-panel-fields">
      <div class="filter-group">
        <label for="ob_filtroNome">Nome:</label>
        <input type="text" id="ob_filtroNome" class="input-text">
      </div>

      <div class="filter-group">
        <label for="ob_filtroStatus">Status:</label>
        <select id="ob_filtroStatus" class="input-select">
          <option value="">Todos</option>
          <option value="true" selected>Ativo</option>
          <option value="false">Inativo</option>
        </select>
      </div>
    </div>

    <div class="filter-panel-actions">
      <button class="btn btn-secondary" id="ob_btnFiltrar">Filtrar</button>
      <button class="btn btn-secondary" id="ob_btnlimparFiltro">Limpar Filtro</button>
    </div>

  </div>

  <div class="page-actions">
    <button class="btn btn-primary" id="ob_btnIncluir">Novo Registro</button>
  </div>

  <div class="table-wrapper" id="content-area-Principal">
    <table class="table-default">
      <thead>
        <tr>
          <th>ID</th>
          <th>Nome</th>
          <th>Status</th>
          <th class="col-acoes">Ações</th>
        </tr>
      </thead>
      <tbody id="ob_listaRegistros">
        <tr>
          <td colspan="4">Carregando...</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="pagination-bar">
    <button id="ob_btnPrimeiro" disabled>Primeiro</button>
    <button id="ob_btnAnterior" disabled>Anterior</button>
    <span>Página <span id="ob_paginaAtual">1</span> de <span id="ob_totalPaginas">1</span></span>
    <button id="ob_btnProximo" disabled>Próximo</button>
    <button id="ob_btnUltimo" disabled>Último</button>
  </div>

</div>
{% endblock %}

{% block js_especifico %}
<script src="{{ url_for('modulo.static', filename='js/modulo.js') }}"></script>
{% endblock %}
```


## 2️⃣ TEMPLATE JS — HUB CANÔNICO
/**
 * PADRÃO BARACAT — HUB DE TELA PRINCIPAL
 *
 * Regras obrigatórias:
 * - Sempre usar typeof window.Hub
 * - Nunca criar múltiplos hubs
 * - Ordem dos métodos é fixa
 * - Toda interação passa pelo Hub
 */


```js
if (typeof window.Hub === "undefined") {
  window.Hub = {
    paginaAtual: 1,
    registrosPorPagina: 20,
    totalPaginas: 1,
    dadosCache: {},
    __eventosOk: false,

    /**
     * configurarEventos
     * - Declarar TODOS os listeners da tela
     * - Usar SEMPRE querySelector + addEventListener
     * - Nunca declarar eventos fora deste método
     */
    configurarEventos: function () {
      if (Hub.__eventosOk) return;
      Hub.__eventosOk = true;

      document.querySelector("#ob_btnIncluir").addEventListener("click", () => {
        GlobalUtils.abrirJanelaApoioModal({
          rota: "/modulo/incluir",
          titulo: "Novo Registro",
          largura: 800,
          altura: 480,
          nivel: 1
        });
      });

      document.querySelector("#ob_btnFiltrar").addEventListener("click", () => {
        Hub.paginaAtual = 1;
        Hub.carregarDados();
      });

      document.querySelector("#ob_btnlimparFiltro").addEventListener("click", () => {
        document.getElementById("ob_filtroNome").value = "";
        document.getElementById("ob_filtroStatus").value = "true";
        Hub.paginaAtual = 1;
        Hub.carregarDados();
      });

      ["ob_btnPrimeiro", "ob_btnAnterior", "ob_btnProximo", "ob_btnUltimo"].forEach(id => {
        document.getElementById(id).addEventListener("click", () => {
          if (id === "ob_btnPrimeiro") Hub.paginaAtual = 1;
          else if (id === "ob_btnAnterior" && Hub.paginaAtual > 1) Hub.paginaAtual--;
          else if (id === "ob_btnProximo" && Hub.paginaAtual < Hub.totalPaginas) Hub.paginaAtual++;
          else if (id === "ob_btnUltimo") Hub.paginaAtual = Hub.totalPaginas;
          Hub.carregarDados();
        });
      });

      Hub.carregarDados();
    },

    /**
     * carregarDados
     * - Responsável por buscar dados conforme filtros e paginação
     * - Nunca renderiza HTML diretamente
     */
    carregarDados: function () {
      // implementação padrão de fetch
    },

    /**
     * renderizarTabela
     * - Define HTML da tabela
     * - Botões de ação DEVEM conter data-id
     * - Ícones aplicados neste momento
     */
    renderizarTabela: function () {
      // implementação padrão de renderização
    },

    /**
     * atualizarPaginacao
     * - Atualiza estado visual da paginação
     */
    atualizarPaginacao: function () {
      // implementação padrão
    }
  };

  // ============================================================
  // AÇÕES DA TABELA
  // - Delegação de eventos
  // - Nunca declarar ações dentro do render
  // ============================================================
  document.getElementById("ob_listaRegistros").addEventListener("click", function (e) {
    const btn = e.target.closest("button");
    if (!btn) return;

    const id = btn.dataset.id;
    if (!id) return;

    if (btn.classList.contains("btnEditar")) {
      GlobalUtils.abrirJanelaApoioModal({
        rota: "/modulo/editar",
        id: parseInt(id, 10),
        titulo: "Editar Registro",
        largura: 800,
        altura: 480,
        nivel: 1
      });
    }
  });

  // ============================================================
  // MESSAGE
  // - Escuta chamadas de telas de apoio
  // - Atualiza dados da tela principal
  // ============================================================
  window.addEventListener("message", function (event) {
    if (event.data && event.data.grupo === "atualizarTabela") {
      Hub.carregarDados();
    }
  });

  // init
  Hub.configurarEventos();
}
```

## 3️⃣ CSS LOCAL — SOMENTE EXCEÇÕES

/* Ajustes específicos da tabela deste módulo */
/* Nunca duplicar estilos existentes no CSS global */

```css
#content-area-Principal table td:nth-child(1),
#content-area-Principal table th:nth-child(1) {
  display: none;
}

#content-area-Principal .col-acoes {
  text-align: center;
  width: 120px;
}
```
