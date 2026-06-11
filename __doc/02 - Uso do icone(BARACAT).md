# 05 — Uso de Ícones — Padrão BARACAT (Tech Icons)

Versão: 2026  
Projeto: BARACAT Gestão Empresarial  

Este documento define o padrão institucional para uso de ícones no BARACAT.

✅ **Regra de ouro:** todo ícone do sistema deve ser gerado via **uma única função global**:  
`Util.gerarIconeTech(...)`

---

## 1. Por que existe este padrão?

- UX consistente
- Zero “data-lucide” espalhado por telas
- CSP-friendly (sem inline)
- Manutenção centralizada (mapa único)

---

## 2. API oficial: `Util.gerarIconeTech`

### 2.1 Retornar HTML do ícone (modo mais comum)

```js
const html = Util.gerarIconeTech("editar");
// use em render de tabela, botões etc.
```

### 2.2 Aplicar diretamente em um elemento (sem montar string)

```js
Util.gerarIconeTech({
  dest: document.querySelector("#btnSalvar"),
  nome: "salvar"
});
```

### 2.3 Modos `append` e `prepend`

```js
Util.gerarIconeTech({ dest: el, nome: "salvar", modo: "prepend" });
Util.gerarIconeTech({ dest: el, nome: "excluir", modo: "append" });
```

---

## 3. Padrão para coluna de ações (tabelas)

✅ Sempre usar **apenas ícone**, sem texto:

```html
<td class="col-acoes">
  <button class="Cl_BtnAcao btnEditar" data-id="1">
    <!-- ícone inserido por JS -->
  </button>
  <button class="Cl_BtnAcao btnExcluir" data-id="1"></button>
</td>
```

E no JS:

```js
document.querySelectorAll(".btnEditar").forEach(btn => {
  Util.gerarIconeTech({ dest: btn, nome: "editar" });
});

document.querySelectorAll(".btnExcluir").forEach(btn => {
  Util.gerarIconeTech({ dest: btn, nome: "excluir" });
});
```

📌 Após renderizar linhas dinamicamente, o util já chama `lucide.createIcons()` internamente.

---

## 4. Regras obrigatórias

- ✔ Ícones semânticos: `"editar"`, `"excluir"`, `"salvar"` (não usar nome técnico do Lucide na tela)
- ✔ Estilo/cor vem do **CSS institucional**
- ✔ Se precisar de ícone novo: adicionar no **MAP do `global_utils.js`** (camada institucional)

---

## 5. Anti‑padrões proibidos

- ❌ `<i data-lucide="...">` direto no HTML da tela
- ❌ Importar Lucide na página
- ❌ CSS local “pintando” ícone com cores fora da paleta BARACAT
- ❌ Duplicar mapas/constantes de ícones em módulos

