-- Corrige endereço de entrega de um pedido (ex.: importação Bling sem endereço)
-- Ajuste o número do pedido e os campos de endereço antes de executar o UPDATE.

-- 1) Conferir qual pedido será alterado
SELECT
    p.id,
    p.numero,
    p.origem,
    p.cliente_nome,
    p.entrega_cep,
    p.entrega_logradouro,
    p.entrega_numero,
    p.entrega_complemento,
    p.entrega_bairro,
    p.entrega_cidade,
    p.entrega_uf,
    p.id_bling_pedido
FROM tbl_pedido p
WHERE p.numero = 'PED-2026-00001'
   OR p.id_bling_pedido = '26268524625';

-- 2) Atualizar endereço (descomente e ajuste se necessário)
/*
UPDATE tbl_pedido
SET
    entrega_cep           = '13214-716',
    entrega_logradouro    = '',              -- preencha: ex. Rua ...
    entrega_numero        = '95',
    entrega_complemento   = NULL,            -- opcional
    entrega_bairro        = '',              -- preencha
    entrega_cidade        = '',              -- preencha: ex. Jundiaí
    entrega_uf            = 'SP',            -- 2 letras
    atualizado_em         = NOW()
WHERE numero = 'PED-2026-00001';
-- WHERE id = 1;  -- alternativa: pelo id retornado no SELECT acima
*/

-- 3) Conferir depois do UPDATE
/*
SELECT
    id, numero, entrega_cep, entrega_logradouro, entrega_numero,
    entrega_bairro, entrega_cidade, entrega_uf
FROM tbl_pedido
WHERE numero = 'PED-2026-00001';
*/
