-- Importacao abre via modal no catalogo (nao menu lateral)
UPDATE tbl_menu SET status = FALSE, obs = 'Abrir via Catálogos > Importar (modal)'
WHERE nav_codigo = 'fn_importacao';
