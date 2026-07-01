-- Garante que dono/admin veem todos os menus ativos (incl. itens criados após o seed inicial)

INSERT INTO tbl_perfil_menu (id_perfil, id_menu, exibir)
SELECT p.id, m.id, TRUE
FROM tbl_perfil p
CROSS JOIN tbl_menu m
WHERE p.codigo IN ('dono', 'admin')
  AND m.status = TRUE
ON CONFLICT (id_perfil, id_menu) DO UPDATE SET exibir = TRUE;
