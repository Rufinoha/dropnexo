# 04 — Uso do Modal (Janelas de Apoio) — Padrão BARACAT

Versão: 2026  
Projeto: BARACAT Gestão Empresarial  

Este documento define o padrão institucional para **abrir, comunicar e fechar** janelas de apoio via modal (iframe), **sem alterar o `global_utils.js`**.

---

## 1. Funções globais oficiais

Todas as telas devem usar **somente** estas funções (já existentes no `global_utils.js`):

- `GlobalUtils.abrirJanelaApoioModal({ ... })`
- `GlobalUtils.receberDadosApoio(callback)`
- `GlobalUtils.fecharJanelaApoio(nivel, quiet?)`

⚠️ Não criar “modal próprio” por tela.

---

## 2. Abrindo um apoio (tela principal)

### 2.1 Assinatura (como está no global hoje)

```js
GlobalUtils.abrirJanelaApoioModal({
  rota,
  titulo = "Apoio",
  largura = 1000,
  altura = 600,   // número (px) OU "auto"
  nivel = 1
});
```

### 2.2 Como passar um **ID** para o apoio (sem mudar o global)

Como a função global **não recebe `id`**, o padrão BARACAT é:
- **quando precisar abrir para edição**, inclua o id na própria `rota` (querystring ou path)
- exemplo (querystring):

```js
GlobalUtils.abrirJanelaApoioModal({
  rota: "/anexoa/apoio/cliente?id=123",
  titulo: "Apoio — Cliente",
  largura: 1100,
  altura: "auto",
  nivel: 1
});
```

✅ No apoio, leia via backend (preferível) ou via URL:
- backend: `request.args.get("id")` (Flask)
- frontend (se for inevitável): `new URLSearchParams(location.search).get("id")`

📌 Regra BARACAT: mesmo com `id` na rota, **toda operação de negócio continua filtrando por `id_projeto` da sessão**.

---

## 3. Recebendo mensagens do apoio (tela principal)

O `GlobalUtils.receberDadosApoio(callback)` é um listener **simples** que:
- exige `event.data.grupo`
- captura `nivel`
- chama `callback(null, nivel)` (o payload não é repassado)

Uso padrão:

```js
GlobalUtils.receberDadosApoio((_, nivel) => {
  // Por padrão, trate como “houve um evento no apoio”
  // Ex.: recarregar listagem e fechar o modal do nível recebido
  carregarDados();
  GlobalUtils.fecharJanelaApoio(nivel);
});
```

### 3.1 Comunicação avançada (quando você precisa do `grupo`/dados)

Se você precisa saber **qual** ação ocorreu (ex.: “salvou”, “excluiu”, “selecionou”), use um listener local **com whitelist**, além do `receberDadosApoio`:

```js
window.addEventListener("message", (event) => {
  if (!event.data?.grupo) return;

  // ✅ whitelist de grupos aceitos
  const aceitos = new Set(["cliente:salvo", "cliente:excluido"]);
  if (!aceitos.has(event.data.grupo)) return;

  // nunca confie em localStorage como segurança
  // backend é a fonte da verdade

  carregarDados();
  GlobalUtils.fecharJanelaApoio(event.data.nivel ?? 1);
});
```

---

## 4. Enviando mensagens do apoio (tela de apoio → principal)

No apoio, para notificar a tela principal:

```js
window.parent.postMessage({
  grupo: "cliente:salvo",
  nivel: window.__nivelModal__ ?? 1
}, "*");
```

📌 O `nivel` deve ser enviado para a principal fechar o modal correto.

---

## 5. Fechando o apoio

### 5.1 Fechar pelo nível (padrão)
```js
GlobalUtils.fecharJanelaApoio(1);
```

### 5.2 Fechar o “topo”
```js
GlobalUtils.fecharJanelaApoio(null);
```

---

## 6. Boas práticas obrigatórias

- ✔ Use `nivel=2`, `nivel=3` somente quando abrir apoio “em cima de apoio”
- ✔ No apoio, ao finalizar (salvar/excluir), **notifique** a principal com `postMessage`
- ✔ Sempre filtre dados por `id_projeto` (sessão backend)
- ✔ Não armazene permissão/projeto no localStorage como verdade

---

## 7. Anti‑padrões proibidos

- ❌ Abrir modal criando HTML/CSS por tela
- ❌ Criar protocolo paralelo (ex.: `carregarApoio`) sem existir no global
- ❌ Confiar em `localStorage` para autorização
- ❌ Query de negócio sem `id_projeto`

