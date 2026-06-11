# Manual Oficial – Combobox Personalizada BARACAT (ComboBusca)

Versão: 2025  
Projeto: BARACAT Gestão Empresarial  

Este documento define o **padrão oficial** para criação e uso de **comboboxes personalizadas com busca** no sistema BARACAT.

Este padrão é **obrigatório** para garantir:
- UX consistente
- Manutenção simples
- Performance
- Segurança
- Clareza conceitual
- Zero duplicação de CSS

---

## 1. Conceito

A Combobox BARACAT:
- **NÃO usa `<select>`**
- É composta por HTML + CSS global + JS global
- Possui **busca remota**
- Suporta **1 a 5 linhas por item**
- Permite **rótulos opcionais por linha**
- Guarda o **id do registro em campo oculto**
- Mostra no display **apenas a primeira linha**

---

## 2. Arquivos Globais

### CSS
- Arquivo: `global_util.css`
- Contém todas as classes `.Cl_*`
- ❌ Nunca criar CSS novo para a combobox
- ❌ Nunca sobrescrever estilos locais

### JS
- Arquivo: `global_util.js`
- Contém:
  - `GlobalUtils.ComboboxBusca`
  - `Util.combobox_personalisado()`

---

## 3. Estrutura HTML Obrigatória

Use **sempre** esta estrutura:

```html
<div id="combo_exemplo" class="Cl_SelectLike">
    <input
        type="text"
        class="Cl_SelectDisplay"
        placeholder="Selecione..."
        autocomplete="off"
        readonly
    />

    <div class="Cl_Caret"></div>

    <div class="Cl_ComboPanel" aria-hidden="true">
        <div class="Cl_ComboSearch">
            <input
                class="Cl_ComboSearchInput"
                placeholder="Digite 3 caracteres ou mais..."
                autocomplete="off"
            />
        </div>

        <div class="Cl_ComboStatus">Digite 3+ para pesquisar</div>
        <div class="Cl_ComboLista"></div>
    </div>
</div>

<input type="hidden" id="exemplo_id" />
```

Regras:
- IDs devem ser únicos
- Não adicionar HTML extra dentro do painel
- A lista é montada exclusivamente pelo JS

## 4. API Oficial – Util.combobox_personalisado

A inicialização da combobox é feita por uma única função.

Assinatura
Util.combobox_personalisado({
  seletor: "#combo_exemplo",
  caracteres: 3,
  rota: "/entidade/combobox",
  limite: 20,
  campoOcultoId: "exemplo_id",

  col_l1: ["campo_principal", false],
  col_l2: ["campo_secundario", true],
  col_l3: ["outro_campo", "Rótulo customizado"],
  col_l4: null,
  col_l5: null,

  onSelect: (item) => {}
});


## 5. Parâmetros de Configuração
# 5.1 Gerais

| Parâmetro       | Descrição                                         |
| --------------- | ------------------------------------------------- |
| `seletor`       | ID do container da combobox                       |
| `caracteres`    | Mínimo de caracteres para iniciar a busca         |
| `rota`          | Endpoint da API                                   |
| `limite`        | Máximo de registros retornados                    |
| `campoOcultoId` | ID do `<input type="hidden">` que receberá o `id` |


# 5.2 Definição das Linhas (col_l1 … col_l5)
Cada item pode exibir a
Formato aceito:
["campo", false]
["campo", true]
["campo", "Rótulo"]

Regras do rótulo:
- false ou vazio → não mostra rótulo
- true → mostra o nome do campo
- "Texto" → rótulo customizado

Exemplo visual:
JOSE ALBIERI
CPF: 90545524920
RESPONSÁVEL: Paulo Silva

## 6. Comportamento da Busca
- A busca só ocorre após atingir o número mínimo de caracteres
- Antes disso:
    - Lista vazia
    - Mensagem: Digite X+ para pesquisar
- Enquanto busca:
    - Mensagem: Carregando...
- Sem resultados:
    - Mensagem: Sem resultados

## 7. Seleção
Ao selecionar um item:
✅ O display mostra somente a primeira linha
✅ O campo oculto recebe o id
❌ Nenhum outro campo é alterado automaticamente
- O callback onSelect(item) é disparado

## 8. Exemplo Real – Motorista
Util.combobox_personalisado({
  seletor: "#combo_motorista",
  caracteres: 3,
  rota: "/combo/motorista",
  limite: 20,
  campoOcultoId: "motorista_id",

  col_l1: ["nome_completo", false],
  col_l2: ["cpf", "CPF"],

  onSelect: (item) => {
    console.log("Motorista selecionado:", item);
  }
});


9. Padrão de API (Backend)
Rota
GET /combo/entidade

Parâmetros
- ?filtro=
- ?limitar=

Retorno
{
  "sucesso": true,
  "dados": [
    { "id": 1, "campo": "valor" }
  ]
}

Regras BARACAT
- Para tabelas de negócio:
    - Filtrar obrigatoriamente por id_projeto da sessão
- Projeto ativo é obrigatório
- Nunca misturar dados de projetos

## 10. Uso no Header (Projeto Ativo)
- O <select> do header será substituído por esta combobox
- A combobox:
    - Define o projeto ativo
    - Guarda o id_projeto no campo oculto
    - Dispara atualização do header via onSelect
⚠️ Isso não é multi-tenant
É apenas seleção de projeto ativo

## 11. Boas Práticas
✔ Sempre usar dispose() ao destruir telas
✔ Nunca duplicar CSS
✔ Nunca usar <select>
✔ Sempre usar campo oculto para ID
✔ Sempre usar id_projeto em consultas de negócio

12. Resumo
| Item          | Padrão                          |
| ------------- | ------------------------------- |
| Componente    | `Cl_SelectLike`                 |
| CSS           | `global_util.css`               |
| JS            | `global_util.js`                |
| API JS        | `Util.combobox_personalisado()` |
| Busca         | Remota                          |
| Linhas        | 1 a 5                           |
| Projeto ativo | Obrigatório                     |
| Multi-tenant  | ❌ Proibido                      |

📌 Este é o padrão oficial do BARACAT.
Não reinventar. Não adaptar fora deste modelo.