# TEMPLATE CANÔNICO — TELA DE APOIO (BARACAT)

Este arquivo define o padrão canônico para **telas de apoio** (incluir/editar) no BARACAT.

Objetivo do padrão:
- `GlobalUtils.receberDadosApoio(callback)` é a **fonte de verdade** para receber `nivel` e `id`
- `id` **nulo/vazio/0** ⇒ **INCLUIR**
- `id` **válido (>0)** ⇒ **EDITAR** (buscar dados na rota `/.../apoio`)
- `nivel` é obrigatório para fechar corretamente com `GlobalUtils.fecharJanelaApoio(nivel)`

---

## 1️⃣ JS — PADRÃO CANÔNICO (INLINE HANDLERS)

Regras obrigatórias deste modelo:
- **Variáveis no topo**
- **Receber dados do apoio** logo no início
- **Declaração de botões** sempre no formato:
  `document.querySelector("#...").addEventListener("click", () => { ... })`
- **Sem “função intermediária”** só para chamar o clique (lógica direta no handler)
- `postMessage` padronizado:
  `{ grupo: "atualizarTabela", nivel: nivelModal }`
- Fechamento sempre:
  `window.parent.GlobalUtils.fecharJanelaApoio(nivelModal)`

```javascript
console.log("📘 apoio.js carregado");

// ============================================================
// 1) VARIÁVEIS (sempre no topo)
// ============================================================
let nivelModal = 1;
let idRegistro = 0;

// ============================================================
// 2) RECEBER DADOS DO APOIO (fonte da verdade)
// - recebe: { nivel, id }
// - id vazio/nulo => INCLUIR
// - id válido      => EDITAR (carrega dados via rota /.../apoio)
// ============================================================
if (window.GlobalUtils && typeof GlobalUtils.receberDadosApoio === "function") {
  GlobalUtils.receberDadosApoio(({ nivel, id }) => {
    nivelModal = Number(nivel || 1) || 1;
    idRegistro = Number(id || 0) || 0;

    if (idRegistro > 0) {
      carregarDadosEdicao();
    } else {
      prepararInclusao();
    }
  });
} else {
  // fallback de contingência (não é o padrão preferido)
  const params = new URLSearchParams(window.location.search);
  idRegistro = Number(params.get("id") || 0) || 0;
  nivelModal = Number(params.get("nivel") || 1) || 1;

  if (idRegistro > 0) carregarDadosEdicao();
  else prepararInclusao();
}

// ============================================================
// 3) DECLARAÇÃO DOS BOTÕES (sempre inline, sem função "ponte")
// ============================================================
document.querySelector("#btnSalvar").addEventListener("click", async () => {
  // (exemplo) validação mínima — adapte ao módulo
  const nome = (document.querySelector("#ob_nome")?.value || "").trim();
  const status = document.querySelector("#ob_status")?.value;

  if (!nome) {
    Swal.fire("Atenção", "Informe o nome.", "warning");
    return;
  }

  Swal.fire({
    title: "Salvando…",
    allowOutsideClick: false,
    didOpen: () => Swal.showLoading()
  });

  try {
    const payload = {
      id: idRegistro > 0 ? idRegistro : null,
      nome,
      status
    };

    // POST /<modulo>/salvar
    const resp = await fetch(`/modulo/salvar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const json = await resp.json();

    if (!resp.ok) {
      Swal.fire("Erro", json.erro || "Erro ao salvar.", "error");
      return;
    }

    Swal.fire("Sucesso", json.message || "Registro salvo.", "success");

    // Atualiza tela principal (padrão único)
    window.parent.postMessage(
      { grupo: "atualizarTabela", nivel: nivelModal },
      "*"
    );

    // Fecha o apoio do nível correto
    window.parent.GlobalUtils.fecharJanelaApoio(nivelModal);

  } catch (err) {
    Swal.fire("Erro inesperado", err.message, "error");
  }
});

document.querySelector("#btnCancelar").addEventListener("click", () => {
  window.parent.GlobalUtils.fecharJanelaApoio(nivelModal);
});

document.querySelector("#btnExcluir").addEventListener("click", async () => {
  if (!(idRegistro > 0)) {
    Swal.fire("Atenção", "Nada para excluir (registro novo).", "warning");
    return;
  }

  const confirma = await Swal.fire({
    title: "Excluir este registro?",
    text: "Essa ação não poderá ser desfeita.",
    icon: "warning",
    showCancelButton: true,
    confirmButtonText: "Sim, excluir",
    cancelButtonText: "Cancelar"
  });

  if (!confirma.isConfirmed) return;

  Swal.fire({
    title: "Excluindo…",
    allowOutsideClick: false,
    didOpen: () => Swal.showLoading()
  });

  try {
    // POST /<modulo>/deletar
    const resp = await fetch(`/modulo/deletar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: idRegistro })
    });

    const json = await resp.json();

    if (!resp.ok) {
      Swal.fire("Erro", json.erro || "Erro ao excluir.", "error");
      return;
    }

    Swal.fire("Sucesso", json.message || "Registro excluído.", "success");

    window.parent.postMessage(
      { grupo: "atualizarTabela", nivel: nivelModal },
      "*"
    );

    window.parent.GlobalUtils.fecharJanelaApoio(nivelModal);

  } catch (err) {
    Swal.fire("Erro inesperado", err.message, "error");
  }
});

// ============================================================
// 4) MESSAGE (opcional / reservado)
// - normalmente o APOIO envia mensagem e a TELA PRINCIPAL escuta
// - manter como reservado para casos especiais
// ============================================================
window.addEventListener("message", function (event) {
  if (!event.data) return;

  // Exemplo reservado:
  // if (event.data.grupo === "atualizarApoio") { ... }
});

// ============================================================
// 5) FUNÇÕES INTERNAS (somente as necessárias ao fluxo)
// - aqui pode existir função utilitária (carregar/preparar)
// - não é "ponte" de clique: é lógica interna do fluxo
// ============================================================
async function carregarDadosEdicao() {
  Swal.fire({
    title: "Carregando…",
    allowOutsideClick: false,
    didOpen: () => Swal.showLoading()
  });

  try {
    // GET /<modulo>/apoio?id=...
    const res = await fetch(`/modulo/apoio?id=${encodeURIComponent(idRegistro)}`);
    const json = await res.json();

    if (!res.ok) {
      Swal.fire("Erro", json.erro || "Erro ao carregar dados.", "error");
      return;
    }

    Swal.close();

    // Exemplo de preenchimento
    document.querySelector("#ob_id").value = json.id || idRegistro;
    document.querySelector("#ob_nome").value = json.nome || "";
    document.querySelector("#ob_status").value = String(json.status ?? "true");

  } catch (err) {
    Swal.fire("Erro inesperado", err.message, "error");
  }
}

function prepararInclusao() {
  // Exemplo de preparação para incluir
  const campoId = document.querySelector("#ob_id");
  if (campoId) campoId.value = "NOVO";

  const campoStatus = document.querySelector("#ob_status");
  if (campoStatus) campoStatus.value = "true";
}
```

## 2️⃣ Observação rápida sobre rotas (padrão esperado)
Carregar edição:
- GET /<modulo>/apoio?id=<id>
Salvar:
- POST /<modulo>/salvar
Excluir:
- POST /<modulo>/deletar
Mensagem para a tela principal:
- postMessage({ grupo: "atualizarTabela", nivel })

