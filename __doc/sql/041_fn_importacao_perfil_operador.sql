-- Permite importação Bling/CSV pelo modal em Catálogos para perfil Operador
INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id
FROM tbl_perfil p
JOIN tbl_permissao m ON m.codigo IN ('fn_importacao.ver', 'fn_importacao.editar')
WHERE p.codigo = 'operador'
ON CONFLICT DO NOTHING;
