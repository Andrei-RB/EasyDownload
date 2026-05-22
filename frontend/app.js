// --- Proteções anti-DevTools Básicas (Camada 1 de Segurança) ---
document.addEventListener('contextmenu', e => e.preventDefault()); // Bloqueia clique-direito
document.onkeydown = function(e) {
    // Bloqueia F12, Ctrl+Shift+I, Ctrl+Shift+J, Ctrl+U
    if (e.keyCode === 123 || 
        (e.ctrlKey && e.shiftKey && (e.keyCode === 73 || e.keyCode === 74)) || 
        (e.ctrlKey && e.keyCode === 85)) {
        return false;
    }
};

// URLs da API se adaptam automaticamente ao servidor (Docker/Localhost)
const API_URL = `${window.location.protocol}//${window.location.host}/api`;
const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${WS_PROTOCOL}//${window.location.host}/ws/progress`;

const elements = {
    urlInput: document.getElementById("youtube-url"),
    btnDownload: document.getElementById("download-btn"),
    btnText: document.querySelector(".btn-text"),
    spinner: document.querySelector(".spinner"),
    progressContainer: document.getElementById("progress-container"),
    statusText: document.getElementById("status-text"),
    percentageText: document.getElementById("percentage"),
    progressBarFill: document.getElementById("progress-bar-fill")
};

function getSelectedFormat() {
    return document.querySelector('input[name="format"]:checked').value;
}

function setUIState(isDownloading) {
    elements.btnDownload.disabled = isDownloading;
    if (isDownloading) {
        elements.btnText.classList.add("hidden");
        elements.spinner.classList.remove("hidden");
        elements.progressContainer.classList.remove("hidden");
        updateProgress("0", "Iniciando...");
    } else {
        elements.btnText.classList.remove("hidden");
        elements.spinner.classList.add("hidden");
    }
}

function updateProgress(percent, status) {
    elements.percentageText.innerText = `${percent}%`;
    elements.progressBarFill.style.width = `${percent}%`;
    if (status) elements.statusText.innerText = status;
}

// Inicia o processo
elements.btnDownload.addEventListener("click", async () => {
    const url = elements.urlInput.value.trim();
    if (!url) {
        alert("Por favor, cole um link do YouTube válido.");
        return;
    }

    // --- [MODO SAAS] Captura o token do Turnstile ---
    // const turnstileResponse = document.querySelector('[name="cf-turnstile-response"]');
    // const token = turnstileResponse ? turnstileResponse.value : "dev_bypass_token"; 

    setUIState(true);

    try {
        // 1. Avisa o backend para começar o download e pega o ID da tarefa
        const res = await fetch(`${API_URL}/start_download`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                url: url, 
                format_type: getSelectedFormat()
                // turnstile_token: token // Desativado para Self-Hosted
            })
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Erro ao iniciar o download.");
        }

        const data = await res.json();
        const taskId = data.task_id;

        // 2. Conecta no WebSocket para ver o progresso real-time
        connectWebSocket(taskId);

    } catch (error) {
        alert(error.message);
        setUIState(false);
    }
});

function connectWebSocket(taskId) {
    const ws = new WebSocket(`${WS_URL}/${taskId}`);

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.status === "downloading") {
            updateProgress(data.progress, "Baixando do YouTube...");
        } 
        else if (data.status === "processing") {
            updateProgress("100", "Processando qualidade máxima...");
        }
        else if (data.status === "completed") {
            updateProgress("100", "Concluído!");
            ws.close();
            
            // 3. Aciona o download nativo do navegador para a máquina do usuário
            // Isso abre a janela "Salvar Como..." dependendo da configuração do navegador
            window.location.href = `${API_URL}/file/${data.file_id}`;
            
            setTimeout(() => {
                setUIState(false);
                elements.progressContainer.classList.add("hidden");
            }, 3000);
        }
        else if (data.status === "error") {
            alert(data.message);
            ws.close();
            setUIState(false);
            elements.progressContainer.classList.add("hidden");
        }
    };

    ws.onerror = () => {
        alert("Erro na conexão em tempo real.");
        setUIState(false);
    };
}
