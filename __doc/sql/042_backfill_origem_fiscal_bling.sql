-- Backfill origem_fiscal = '0' para produtos importados do Bling quando o bug
-- descartava origem numérica 0. Ajuste o número do lote ou id_tenant se necessário.
--
-- TROVA DISTRIBUIDORA — lote IMP-2026-000003 (157 produtos, jun/2026)

-- 1) Conferir quantos serão afetados
SELECT
    t.nome AS conta,
    l.numero AS lote,
    COUNT(*) AS produtos_sem_origem
FROM tbl_produto p
JOIN tbl_importacao_lote l ON l.id = p.id_importacao_lote
JOIN tbl_tenant t ON t.id = p.id_tenant
WHERE l.numero = 'IMP-2026-000003'
  AND (p.origem_fiscal IS NULL OR BTRIM(p.origem_fiscal) = '')
GROUP BY t.nome, l.numero;

-- 2) Amostra antes do update
SELECT p.id, p.sku, p.ncm, p.cest, p.origem_fiscal
FROM tbl_produto p
JOIN tbl_importacao_lote l ON l.id = p.id_importacao_lote
WHERE l.numero = 'IMP-2026-000003'
  AND (p.origem_fiscal IS NULL OR BTRIM(p.origem_fiscal) = '')
ORDER BY p.sku
LIMIT 20;

-- 3) Aplicar (somente se no Bling todos eram origem 0)
UPDATE tbl_produto p
SET origem_fiscal = '0'
FROM tbl_importacao_lote l
WHERE l.id = p.id_importacao_lote
  AND l.numero = 'IMP-2026-000003'
  AND (p.origem_fiscal IS NULL OR BTRIM(p.origem_fiscal) = '');

-- 4) Validar SKU de exemplo
SELECT sku, ncm, cest, origem_fiscal
FROM tbl_produto
WHERE sku = '14891';
