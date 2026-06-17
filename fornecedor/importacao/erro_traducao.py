# fornecedor/importacao/erro_traducao.py — mensagens amigáveis para erros de importação
from __future__ import annotations

import re
from typing import Any


def _msg_low(mensagem: str) -> str:
    return (mensagem or "").strip().lower()


def traduzir_mensagem_erro(
    campo: str | None,
    mensagem: str,
    payload: dict | None = None,
    origem: str | None = None,
) -> str:
    """Converte exceção técnica em texto para o usuário."""
    campo_u = (campo or "").strip().upper()
    msg = (mensagem or "").strip()
    msg_low = _msg_low(msg)
    pl = payload or {}
    origem = (origem or pl.get("origem") or "").strip().lower()

    if campo_u == "__HEADER__":
        return "Coluna obrigatória não encontrada no arquivo."

    if campo_u == "__CONFIG__":
        if "competência" in msg_low or "competencia" in msg_low:
            return "Layout incompleto para este tipo de importação."
        return "Layout inválido."

    if campo_u == "__DB__" or "violates" in msg_low or "null value in column" in msg_low:
        return _traduzir_erro_banco(msg, msg_low)

    # Integração Bling / Python interno
    if "nonetype" in msg_low and "not subscriptable" in msg_low:
        return (
            "Não foi possível gravar o produto: o vínculo com o catálogo local está inconsistente "
            "(registro mapeado ausente ou inválido). Tente reimportar; se persistir, remova o vínculo "
            "antigo na integração Bling."
        )

    if "sku obrigatório" in msg_low or "sku obrigatorio" in msg_low:
        return "SKU obrigatório: o produto no Bling não possui código (SKU)."

    if "produto pai não encontrado" in msg_low or "produto pai nao encontrado" in msg_low:
        return "Produto pai não encontrado na API do Bling."

    if "nenhuma variação importada" in msg_low or "nenhuma variacao importada" in msg_low:
        return "Grupo de variações rejeitado: todas as variações precisam ser válidas (regra tudo ou nada)."

    if "imagem excede" in msg_low:
        return "Imagem maior que 3 MB — reduza ou altere o modo de importação de imagens."

    if "timeout" in msg_low or "timed out" in msg_low:
        return "Tempo esgotado ao comunicar com o Bling. Tente novamente em instantes."

    if "401" in msg or "403" in msg or "unauthorized" in msg_low:
        return "Falha de autenticação com o Bling. Reconecte a integração."

    if "429" in msg or "rate limit" in msg_low:
        return "Limite de requisições do Bling atingido. Aguarde e tente novamente."

    if origem == "bling" and msg_low.startswith("valueerror"):
        return msg.split(":", 1)[-1].strip() or "Dados inválidos retornados pelo Bling."

    # Validações de negócio comuns (CSV / layout)
    if "campo obrigatório" in msg_low or "campo obrigatorio" in msg_low:
        return "Campo obrigatório não preenchido."

    if "nome obrigatório" in msg_low or "nome obrigatorio" in msg_low:
        return "Nome do produto é obrigatório."

    if "máximo de" in msg_low and "linhas" in msg_low:
        return msg

    if "valor inválido" in msg_low or "valor invalido" in msg_low:
        return "Valor inválido na linha importada."

    if "duplicate key" in msg_low or "unique constraint" in msg_low or "já existe" in msg_low:
        return "Registro duplicado (SKU ou identificador já existente)."

    return msg or "Erro de importação."


def _traduzir_erro_banco(msg: str, msg_low: str) -> str:
    if (
        "null value in column" in msg_low
        or "not-null constraint" in msg_low
        or "violates not-null constraint" in msg_low
    ):
        return "Campo obrigatório não preenchido."

    if "duplicate key" in msg_low or "unique constraint" in msg_low:
        return "Valor já existe no banco (duplicado)."

    if "violates foreign key constraint" in msg_low:
        return "Referência inválida: valor relacionado não encontrado."

    if "invalid input syntax for type numeric" in msg_low:
        return "Número inválido."

    if "invalid input syntax for type integer" in msg_low:
        return "Número inteiro inválido."

    if "invalid input syntax for type date" in msg_low:
        return "Data inválida."

    if "value too long for type" in msg_low:
        return "Texto maior que o tamanho permitido."

    if "tuple index out of range" in msg_low:
        return "Estrutura de gravação incompatível (quantidade de campos)."

    return msg or "Falha ao gravar registro no banco."


def obter_dica_erro(
    mensagem_tecnica: str,
    payload: dict | None = None,
    origem: str | None = None,
) -> str:
    """Sugestão prática para o usuário."""
    msg_low = _msg_low(mensagem_tecnica)
    pl = payload or {}
    origem = (origem or pl.get("origem") or "").strip().lower()

    if "nonetype" in msg_low and "not subscriptable" in msg_low:
        return (
            "Verifique se o produto ainda existe no DropNexo. Se foi excluído manualmente, "
            "desvincule-o no Bling ou limpe tbl_integracao_map e importe novamente."
        )

    if "sku obrigatório" in msg_low or "sku obrigatorio" in msg_low:
        return "No Bling, preencha o campo Código (SKU) do produto e reimporte."

    if origem == "bling" and pl.get("id_bling"):
        return f"Abra o produto #{pl.get('id_bling')} no Bling, corrija os dados e execute a importação de novo."

    if pl.get("linha_arquivo"):
        return f"Corrija a linha {pl.get('linha_arquivo')} do arquivo e importe novamente."

    return "Corrija o registro na origem e repita a importação."


def classificar_erro(mensagem_tecnica: str, origem: str | None = None) -> str:
    """Categoria curta para badge na UI."""
    msg_low = _msg_low(mensagem_tecnica)
    origem = (origem or "").lower()

    if origem == "bling":
        return "Integração Bling"
    if origem == "arquivo":
        return "Arquivo CSV"
    if "nonetype" in msg_low:
        return "Vínculo inconsistente"
    if "sku" in msg_low:
        return "Dados incompletos"
    if "violates" in msg_low or "constraint" in msg_low:
        return "Banco de dados"
    return "Importação"


def enriquecer_erro(
    *,
    id: int,
    linha_arquivo: int | None,
    ref_externa: str | None,
    nome: str | None,
    sku: str | None,
    campo: str | None,
    mensagem: str,
    payload: Any,
    corrigido: bool,
    criado_em: str | None,
) -> dict:
    """Normaliza linha de tbl_importacao_erro para a API/UI."""
    pl: dict = {}
    if isinstance(payload, dict):
        pl = payload
    elif isinstance(payload, str) and payload.strip():
        try:
            import json

            pl = json.loads(payload)
        except Exception:
            pl = {"raw": payload}

    tecnica = (pl.get("mensagem_tecnica") or mensagem or "").strip()
    origem = pl.get("origem")
    amigavel = traduzir_mensagem_erro(campo, tecnica, pl, origem)
    # Registros antigos já gravados com mensagem amigável
    if not pl.get("mensagem_tecnica") and mensagem and mensagem != tecnica:
        amigavel = mensagem

    categoria = classificar_erro(tecnica, origem)
    dica = pl.get("dica") or obter_dica_erro(tecnica, pl, origem)

    detalhe = {
        "id": id,
        "linha_arquivo": linha_arquivo,
        "ref_externa": ref_externa,
        "nome": nome,
        "sku": sku,
        "campo": campo,
        "mensagem": amigavel,
        "mensagem_tecnica": tecnica,
        "categoria": categoria,
        "dica": dica,
        "corrigido": corrigido,
        "criado_em": criado_em,
        "payload": pl,
    }
    return detalhe


def montar_payload_erro(
    *,
    mensagem_tecnica: str,
    origem: str,
    campo: str | None = None,
    extra: dict | None = None,
    traceback_txt: str | None = None,
) -> dict:
    pl: dict = {"origem": origem, "mensagem_tecnica": mensagem_tecnica}
    if campo:
        pl["campo_original"] = campo
    if traceback_txt:
        pl["traceback"] = traceback_txt[-3000:]
    if extra:
        pl.update(extra)
    pl["dica"] = obter_dica_erro(mensagem_tecnica, pl, origem)
    pl["categoria"] = classificar_erro(mensagem_tecnica, origem)
    return pl
