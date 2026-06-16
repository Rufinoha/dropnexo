# Conteúdo do manual público — conexão Bling (passos alinhados às capturas em manual/)

MANUAL_BLING_PASSOS = [
    {
        "img": "image_bling1.jpg",
        "titulo": "Conta, plano e Integrações",
        "texto": (
            "O primeiro passo é ter uma <strong>conta ativa</strong> no DropNexo com um "
            "<strong>plano pago</strong> (Profissional ou superior). "
            "As integrações com ERP <strong>não estão disponíveis</strong> no plano gratuito (Starter). "
            "Se você ainda não tem conta, faça o cadastro como "
            "<a href=\"{url_cadastro_fornecedor}\">fornecedor</a> ou "
            "<a href=\"{url_cadastro_vendedor}\">vendedor</a>, conclua o cadastro e "
            "<strong>contrate um plano</strong> em <strong>Meu plano</strong> (menu do usuário, canto superior). "
            "Com o plano ativo, acesse o <a href=\"{url_login}\">login</a>, entre na sua empresa e, "
            "no menu lateral, abra <strong>Integrações</strong>. "
            "Na categoria <strong>ERP</strong>, clique no card <strong>Bling</strong>."
        ),
    },
    {
        "img": "image_bling2.jpg",
        "titulo": "Inicie a conexão",
        "texto": (
            "Na janela <strong>Conectar Bling</strong>, clique em "
            "<strong>Conectar conta</strong>. Você será redirecionado com segurança ao site do Bling."
        ),
    },
    {
        "img": "image_bling3.jpg",
        "titulo": "Faça login no Bling",
        "texto": (
            "Informe seu <strong>usuário ou e-mail</strong> e <strong>senha</strong> da conta Bling "
            "e clique em <strong>Entrar</strong>. Em seguida, autorize o acesso do DropNexo."
        ),
    },
    {
        "img": "image_bling4.jpg",
        "titulo": "Confirme que está conectado",
        "texto": (
            "De volta ao DropNexo, o card do Bling exibirá o status "
            "<strong>Conectado</strong>. Clique novamente no card para abrir a configuração."
        ),
    },
    {
        "img": "image_bling5.jpg",
        "titulo": "Configure e sincronize",
        "texto": (
            "Revise produtos, estoque e pedidos conforme seu perfil. "
            "Clique em <strong>Salvar</strong> e use <strong>Sincronizar produtos</strong> "
            "para importar ou atualizar o catálogo."
        ),
    },
]

MANUAL_IMAGENS_PERMITIDAS = frozenset(p["img"] for p in MANUAL_BLING_PASSOS)

# Referência da tela "Configuração — Fornecedor" (passo 5)
MANUAL_BLING_CONFIG_FORNECEDOR = [
    {
        "campo": "Modo das imagens",
        "descricao": (
            "Define como as fotos dos produtos vindos do Bling serão armazenadas no DropNexo "
            "durante a sincronização de catálogo."
        ),
        "padrao": "Manter como link",
        "opcoes": [
            {
                "nome": "Manter como link",
                "efeito": (
                    "O DropNexo grava a <strong>URL original</strong> da imagem hospedada no Bling. "
                    "As fotos continuam sendo servidas pelo Bling; a sincronização é mais rápida e ocupa menos espaço no servidor."
                ),
            },
            {
                "nome": "Baixar para o servidor",
                "efeito": (
                    "O DropNexo <strong>baixa cada imagem</strong> para a pasta da sua empresa "
                    "(<code>upload/tenant…/produtos/SKU/</code>). Limite de <strong>3 MB</strong> por arquivo. "
                    "Útil quando você quer independência do link externo ou controle local dos arquivos."
                ),
            },
        ],
    },
    {
        "campo": "Fonte principal",
        "descricao": (
            "Indica qual sistema é considerado a <strong>referência oficial</strong> quando os mesmos dados "
            "existem nos dois lados (Bling e DropNexo) e há divergência."
        ),
        "padrao": "Bling",
        "opcoes": [
            {
                "nome": "Bling",
                "efeito": (
                    "Em conflito de informação, prevalece o que está no <strong>Bling</strong>. "
                    "Recomendado para fornecedor que já opera o catálogo no ERP."
                ),
            },
            {
                "nome": "DropNexo",
                "efeito": (
                    "Em conflito, prevalece o que está no <strong>DropNexo</strong>. "
                    "Use se você mantém o cadastro mestre na plataforma e o Bling é secundário."
                ),
            },
        ],
    },
    {
        "campo": "Produtos",
        "descricao": (
            "Controla o <strong>fluxo de cadastro de produtos</strong> entre Bling e DropNexo. "
            "Afeta o botão <strong>Sincronizar produtos</strong>."
        ),
        "padrao": "Importar",
        "opcoes": [
            {
                "nome": "Importar",
                "efeito": (
                    "Traz produtos do <strong>Bling → DropNexo</strong>. Cria itens novos e atualiza os já mapeados. "
                    "Produtos <strong>sem SKU</strong> no Bling são ignorados."
                ),
            },
            {
                "nome": "Exportar",
                "efeito": (
                    "Envia produtos do <strong>DropNexo → Bling</strong>. "
                    "Nesta opção o botão <strong>Sincronizar produtos</strong> não executa importação "
                    "(modo pensado para quem cadastra no DropNexo e publica no ERP)."
                ),
            },
            {
                "nome": "Atualizar (ambos)",
                "efeito": (
                    "Permite <strong>importar e atualizar</strong> produtos do Bling no DropNexo, "
                    "mantendo o vínculo entre os cadastros. É o modo mais completo para quem edita nos dois lados."
                ),
            },
        ],
    },
    {
        "campo": "Estoque",
        "descricao": (
            "Define a direção da sincronização de <strong>quantidades em estoque</strong> "
            "entre depósitos do Bling e o DropNexo."
        ),
        "padrao": "Atualizar (ambos)",
        "opcoes": [
            {
                "nome": "Importar",
                "efeito": (
                    "O estoque do <strong>Bling alimenta</strong> o DropNexo. "
                    "Alterações feitas só no DropNexo podem ser sobrescritas na próxima sincronização."
                ),
            },
            {
                "nome": "Exportar",
                "efeito": (
                    "O estoque do <strong>DropNexo é enviado</strong> ao Bling. "
                    "Indicado quando o controle de saldo é feito na plataforma."
                ),
            },
            {
                "nome": "Atualizar (ambos)",
                "efeito": (
                    "Sincronização <strong>bidirecional</strong>: mudanças em qualquer lado podem refletir no outro "
                    "(na prática, prevalece a alteração mais recente conforme a regra do conector)."
                ),
            },
        ],
        "nota": (
            "A sincronização automática de estoque está em evolução. "
            "A configuração já fica salva para quando o módulo estiver ativo."
        ),
    },
    {
        "campo": "Pedidos",
        "descricao": (
            "Define como os <strong>pedidos de venda</strong> circulam entre DropNexo e Bling "
            "(pedidos B2B da rede, marketplace, etc.)."
        ),
        "padrao": "Exportar",
        "opcoes": [
            {
                "nome": "Importar",
                "efeito": (
                    "Pedidos criados no <strong>Bling</strong> são trazidos para o DropNexo. "
                    "Útil se você fatura ou processa pedidos primeiro no ERP."
                ),
            },
            {
                "nome": "Exportar",
                "efeito": (
                    "Pedidos gerados no <strong>DropNexo</strong> são enviados ao Bling para faturamento, "
                    "expedição e NF-e. Padrão recomendado para <strong>fornecedor</strong> que recebe pedidos da rede."
                ),
            },
            {
                "nome": "Atualizar (ambos)",
                "efeito": (
                    "Pedidos podem ser criados ou atualizados nos dois sistemas e refletidos no outro lado, "
                    "conforme status e regras do conector."
                ),
            },
        ],
        "nota": (
            "A sincronização de pedidos depende do módulo de pedidos B2B e será liberada em fase posterior. "
            "Salve a opção desejada já agora."
        ),
    },
]

MANUAL_BLING_BOTOES_FORNECEDOR = [
    {
        "nome": "Salvar",
        "efeito": "Grava todas as opções acima para o perfil <strong>fornecedor</strong> da sua empresa.",
    },
    {
        "nome": "Sincronizar produtos",
        "efeito": (
            "Com modo <strong>Produtos</strong> em <em>Importar</em> ou <em>Atualizar</em>, "
            "use <strong>Importar todos</strong> ou escolha uma <strong>categoria do Bling</strong> "
            "e clique em <strong>Importar categoria</strong>. "
            "As categorias são cadastradas automaticamente no DropNexo. "
            "O resultado aparece em <strong>Últimos logs</strong>."
        ),
    },
]
