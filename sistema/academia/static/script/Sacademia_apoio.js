(function () {
    let registroID = null;
    let nivelModal = 1;
    const LIMITE_UPLOAD_MB = 2048;
    const CHUNK_SIZE = 512 * 1024; // 512 KB — passa do limite típico do Nginx

    const el = {
        id: document.getElementById("id"),
        categoria: document.getElementById("categoria"),
        titulo: document.getElementById("titulo"),
        descricao: document.getElementById("descricao"),
        duracao: document.getElementById("duracao_txt"),
        ordem: document.getElementById("ordem"),
        ativo: document.getElementById("ativo"),
        arquivo: document.getElementById("arquivo"),
        hint: document.getElementById("arquivoHint"),
        uploadNome: document.getElementById("aca_upload_nome"),
        uploadZone: document.getElementById("aca_upload_zone"),
        tituloPagina: document.getElementById("aca_titulo_pagina"),
        btnSalvar: document.getElementById("btnSalvar"),
        btnExcluir: document.getElementById("btnExcluir"),
    };
    if (!el.titulo) return;

    function idFromQuery() {
        const v = Number(new URLSearchParams(window.location.search).get("id") || 0);
        return Number.isFinite(v) && v > 0 ? v : null;
    }

    function setUploadUi({ nome, hint, hasFile }) {
        if (el.uploadNome) el.uploadNome.textContent = nome || "Selecionar arquivo MP4";
        if (el.hint) el.hint.textContent = hint || "";
        if (el.uploadZone) el.uploadZone.classList.toggle("has-file", !!hasFile);
    }

    function limparNovo() {
        el.categoria.value = "";
        el.titulo.value = "";
        el.descricao.value = "";
        el.duracao.value = "";
        el.ordem.value = "0";
        el.ativo.checked = true;
        if (el.arquivo) el.arquivo.value = "";
        if (el.tituloPagina) el.tituloPagina.textContent = "Novo vídeo-aula";
        setUploadUi({
            nome: "Selecionar arquivo MP4",
            hint: "Obrigatório ao incluir. Arraste ou clique para escolher.",
            hasFile: false,
        });
        if (el.btnExcluir) el.btnExcluir.hidden = true;
    }

    function syncArquivoSelecionado() {
        const f = el.arquivo?.files?.[0];
        if (!f) {
            setUploadUi({
                nome: "Selecionar arquivo MP4",
                hint: registroID
                    ? "Opcional: envie um MP4 para substituir o vídeo."
                    : "Obrigatório ao incluir. Arraste ou clique para escolher.",
                hasFile: false,
            });
            return;
        }
        const mb = f.size / (1024 * 1024);
        setUploadUi({
            nome: f.name,
            hint: `${mb.toFixed(1)} MB · será enviado em partes`,
            hasFile: true,
        });
    }

    async function parseJsonResposta(resp) {
        const text = await resp.text();
        try {
            return JSON.parse(text);
        } catch {
            if (resp.status === 413) {
                throw new Error(
                    "Arquivo grande demais (HTTP 413). O upload em partes deveria evitar isso — atualize o app no servidor e tente de novo."
                );
            }
            throw new Error(
                resp.status >= 400
                    ? `Falha no servidor (HTTP ${resp.status}).`
                    : "Resposta inválida do servidor."
            );
        }
    }

    async function carregar(id) {
        const resp = await fetch("/academia/apoio", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id }),
        });
        const json = await parseJsonResposta(resp);
        if (!json.success) throw new Error(json.message || "Erro ao carregar vídeo.");
        const d = json.item;
        if (!d) return;
        el.categoria.value = d.categoria || "";
        el.titulo.value = d.titulo || "";
        el.descricao.value = d.descricao || "";
        el.duracao.value = d.duracao_txt || "";
        el.ordem.value = String(d.ordem ?? 0);
        el.ativo.checked = !!d.ativo;
        if (el.tituloPagina) el.tituloPagina.textContent = "Editar vídeo-aula";
        setUploadUi({
            nome: d.nome_original ? d.nome_original : "Selecionar arquivo MP4",
            hint: d.nome_original
                ? `Arquivo atual: ${d.nome_original}. Envie um novo MP4 apenas se quiser substituir.`
                : "Opcional: envie um MP4 para substituir o vídeo.",
            hasFile: !!d.nome_original,
        });
        if (el.btnExcluir) el.btnExcluir.hidden = false;
    }

    async function enviarArquivoEmPartes(file, onProgress) {
        const totalChunks = Math.ceil(file.size / CHUNK_SIZE) || 1;
        const ini = await fetch("/academia/upload/iniciar", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                nome: file.name || "video.mp4",
                tamanho: file.size,
                total_chunks: totalChunks,
            }),
        });
        const jIni = await parseJsonResposta(ini);
        if (!jIni.success) throw new Error(jIni.message || "Falha ao iniciar upload.");

        const uploadId = jIni.upload_id;
        const chunkSize = Number(jIni.chunk_size) || CHUNK_SIZE;

        for (let i = 0; i < totalChunks; i++) {
            const start = i * chunkSize;
            const end = Math.min(file.size, start + chunkSize);
            const blob = file.slice(start, end);
            const fd = new FormData();
            fd.append("upload_id", uploadId);
            fd.append("index", String(i));
            fd.append("chunk", blob, `part_${i}.bin`);

            const r = await fetch("/academia/upload/chunk", { method: "POST", body: fd });
            const j = await parseJsonResposta(r);
            if (!j.success) throw new Error(j.message || `Falha na parte ${i + 1}/${totalChunks}.`);
            if (typeof onProgress === "function") {
                onProgress(i + 1, totalChunks);
            }
        }
        return uploadId;
    }

    async function salvar() {
        const arquivo = el.arquivo?.files?.[0] || null;
        if (arquivo) {
            const mb = arquivo.size / (1024 * 1024);
            if (mb > LIMITE_UPLOAD_MB) {
                throw new Error(
                    `Arquivo com ${mb.toFixed(0)} MB. Limite: ${LIMITE_UPLOAD_MB} MB.`
                );
            }
        }

        let uploadId = null;
        if (arquivo) {
            Swal.fire({
                title: "Enviando vídeo…",
                html: "Preparando partes…",
                allowOutsideClick: false,
                didOpen: () => Swal.showLoading(),
            });
            uploadId = await enviarArquivoEmPartes(arquivo, (atual, total) => {
                const pct = Math.round((atual / total) * 100);
                const box = Swal.getHtmlContainer();
                if (box) box.textContent = `Enviando parte ${atual} de ${total} (${pct}%)`;
            });
        }

        const fd = new FormData();
        if (registroID) fd.append("id", String(registroID));
        fd.append("categoria", el.categoria.value.trim());
        fd.append("titulo", el.titulo.value.trim());
        fd.append("descricao", el.descricao.value.trim());
        fd.append("duracao_txt", el.duracao.value.trim());
        fd.append("ordem", el.ordem.value || "0");
        fd.append("ativo", el.ativo.checked ? "1" : "0");
        if (uploadId) fd.append("upload_id", uploadId);

        if (arquivo) {
            const box = Swal.getHtmlContainer();
            if (box) box.textContent = "Finalizando cadastro…";
        }

        const resp = await fetch("/academia/salvar", { method: "POST", body: fd });
        const json = await parseJsonResposta(resp);
        if (!json.success) throw new Error(json.message || "Erro ao salvar.");
        await Swal.fire("Sucesso", "Vídeo salvo com sucesso.", "success");
        window.parent.postMessage({ grupo: "atualizarAcademia" }, "*");
        window.GlobalUtils?.fecharJanelaApoio(nivelModal);
    }

    async function inativar() {
        if (!registroID) return;
        const c = await Swal.fire({
            title: "Inativar este vídeo?",
            icon: "warning",
            showCancelButton: true,
            confirmButtonText: "Sim, inativar",
            cancelButtonText: "Cancelar",
        });
        if (!c.isConfirmed) return;
        const resp = await fetch("/academia/deletar", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: registroID }),
        });
        const json = await parseJsonResposta(resp);
        if (!json.success) throw new Error(json.message || "Erro ao inativar.");
        await Swal.fire("Sucesso", "Vídeo inativado.", "success");
        window.parent.postMessage({ grupo: "atualizarAcademia" }, "*");
        window.GlobalUtils?.fecharJanelaApoio(nivelModal);
    }

    async function iniciarApoio(id, nivel) {
        const uid = id != null && Number(id) > 0 ? Number(id) : idFromQuery();
        registroID = uid || null;
        nivelModal = nivel || 1;
        if (el.id) el.id.value = registroID || "";
        if (registroID) await carregar(registroID);
        else limparNovo();
    }

    el.arquivo?.addEventListener("change", syncArquivoSelecionado);

    if (el.uploadZone) {
        ["dragenter", "dragover"].forEach((ev) => {
            el.uploadZone.addEventListener(ev, (e) => {
                e.preventDefault();
                e.stopPropagation();
                el.uploadZone.classList.add("is-drag");
            });
        });
        ["dragleave", "drop"].forEach((ev) => {
            el.uploadZone.addEventListener(ev, (e) => {
                e.preventDefault();
                e.stopPropagation();
                el.uploadZone.classList.remove("is-drag");
            });
        });
        el.uploadZone.addEventListener("drop", (e) => {
            const files = e.dataTransfer?.files;
            if (!files?.length || !el.arquivo) return;
            const f = files[0];
            if (!/\.mp4$/i.test(f.name || "") && f.type !== "video/mp4") {
                Swal.fire("Arquivo inválido", "Envie apenas MP4.", "warning");
                return;
            }
            const dt = new DataTransfer();
            dt.items.add(f);
            el.arquivo.files = dt.files;
            syncArquivoSelecionado();
        });
    }

    el.btnSalvar?.addEventListener("click", () => {
        salvar().catch((e) => Swal.fire("Erro", e.message, "error"));
    });
    el.btnExcluir?.addEventListener("click", () => {
        inativar().catch((e) => Swal.fire("Erro", e.message, "error"));
    });

    if (window.GlobalUtils?.receberDadosApoio) {
        window.GlobalUtils.receberDadosApoio(iniciarApoio);
    } else {
        const qid = idFromQuery();
        if (qid) iniciarApoio(qid, 1).catch((e) => Swal.fire("Erro", e.message, "error"));
        else limparNovo();
    }
})();
