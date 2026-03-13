/**
 * V_T_R - Video Transcriptor y Resumen
 * Lógica del Frontend
 */

// ============================================
// Estado de la aplicación
// ============================================

const state = {
    currentSection: 'upload',
    currentClass: null,
    currentTranscriptionSegments: null,
    currentFolder: null,   // {path, name, classCount}
    classes: [],
    collapsedFolders: new Set(),
    queue: [],          // [{file, status:'pending'|'processing'|'done'|'error', error:''}]
    isProcessing: false,
    openaiConfigured: false,
    cancelRequested: false,
    abortController: null
};

// ============================================
// Elementos del DOM
// ============================================

const elements = {
    // Navegación
    navItems: document.querySelectorAll('.nav-item'),
    sections: document.querySelectorAll('.section'),

    // Status
    gpuStatus: document.getElementById('gpuStatus'),
    gpuText: document.getElementById('gpuText'),
    geminiStatus: document.getElementById('geminiStatus'),
    geminiText: document.getElementById('geminiText'),
    vramItem: document.getElementById('vramItem'),
    vramBarFill: document.getElementById('vramBarFill'),
    vramText: document.getElementById('vramText'),

    // Upload
    uploadArea: document.getElementById('uploadArea'),
    fileInput: document.getElementById('fileInput'),
    queueList: document.getElementById('queueList'),
    queueCounter: document.getElementById('queueCounter'),
    failedHistoryPanel: document.getElementById('failedHistoryPanel'),
    shutdownCheckbox: document.getElementById('shutdownCheckbox'),
    modelSelect: document.getElementById('modelSelect'),
    processBtn: document.getElementById('processBtn'),
    progressContainer: document.getElementById('progressContainer'),
    progressFill: document.getElementById('progressFill'),
    progressText: document.getElementById('progressText'),
    progressPercent: document.getElementById('progressPercent'),

    // Clases
    classesGrid: document.getElementById('classesGrid'),
    emptyClasses: document.getElementById('emptyClasses'),

    // Detalle
    detailSection: document.getElementById('detail-section'),
    backBtn: document.getElementById('backBtn'),
    detailTitle: document.getElementById('detailTitle'),
    detailDate: document.getElementById('detailDate'),
    tabs: document.querySelectorAll('.tab'),
    tabContents: document.querySelectorAll('.tab-content'),
    summaryContent: document.getElementById('summaryContent'),
    transcriptionContent: document.getElementById('transcriptionContent'),
    transcriptionCount: document.getElementById('transcriptionCount'),
    downloadTranscriptionBtn: document.getElementById('downloadTranscriptionBtn'),
    slidesBtnTab: document.getElementById('tab-btn-slides'),
    slidesContent: document.getElementById('slidesContent'),
    slidesCount: document.getElementById('slidesCount'),
    regenerateSlidesBtn: document.getElementById('regenerateSlidesBtn'),
    downloadSlidesMdBtn: document.getElementById('downloadSlidesMdBtn'),
    downloadSlidesPdfBtn: document.getElementById('downloadSlidesPdfBtn'),

    // Carpetas
    folderSelect: document.getElementById('folderSelect'),
    newFolderBtn: document.getElementById('newFolderBtn'),
    newFolderForm: document.getElementById('newFolderForm'),
    newFolderName: document.getElementById('newFolderName'),
    newFolderParentSelect: document.getElementById('newFolderParentSelect'),
    createFolderBtn: document.getElementById('createFolderBtn'),
    cancelFolderBtn: document.getElementById('cancelFolderBtn'),

    // Chat de clase
    chatMessages: document.getElementById('chatMessages'),
    chatInput: document.getElementById('chatInput'),
    sendChatBtn: document.getElementById('sendChatBtn'),
    clearChatBtn: document.getElementById('clearChatBtn'),

    // Regenerar resumen
    regenerateSummaryBtn: document.getElementById('regenerateSummaryBtn'),

    // Knowledge & Rubrica panels (class chat)
    knowledgeToggle: document.getElementById('knowledgeToggle'),
    knowledgePanel: document.getElementById('knowledgePanel'),
    knowledgeFiles: document.getElementById('knowledgeFiles'),
    knowledgeFileInput: document.getElementById('knowledgeFileInput'),
    rubricaToggle: document.getElementById('rubricaToggle'),
    rubricaPanel: document.getElementById('rubricaPanel'),
    rubricaFiles: document.getElementById('rubricaFiles'),
    rubricaText: document.getElementById('rubricaText'),
    rubricaFileInput: document.getElementById('rubricaFileInput'),
    saveRubricaBtn: document.getElementById('saveRubricaBtn'),

    // Images panel (class chat)
    imagesToggle: document.getElementById('imagesToggle'),
    imagesPanel: document.getElementById('imagesPanel'),
    contextImageFiles: document.getElementById('contextImageFiles'),
    contextImageFileInput: document.getElementById('contextImageFileInput'),

    // Chat de carpeta
    folderChatSection: document.getElementById('folder-chat-section'),
    folderChatBackBtn: document.getElementById('folderChatBackBtn'),
    folderChatTitle: document.getElementById('folderChatTitle'),
    folderChatSubtitle: document.getElementById('folderChatSubtitle'),
    folderChatClassesBadge: document.getElementById('folderChatClassesBadge'),
    folderChatMessages: document.getElementById('folderChatMessages'),
    folderChatInput: document.getElementById('folderChatInput'),
    sendFolderChatBtn: document.getElementById('sendFolderChatBtn'),
    clearFolderChatBtn: document.getElementById('clearFolderChatBtn'),

    // Knowledge & Rubrica panels (folder chat)
    folderKnowledgeToggle: document.getElementById('folderKnowledgeToggle'),
    folderKnowledgePanel: document.getElementById('folderKnowledgePanel'),
    folderKnowledgeFiles: document.getElementById('folderKnowledgeFiles'),
    folderKnowledgeFileInput: document.getElementById('folderKnowledgeFileInput'),
    folderRubricaToggle: document.getElementById('folderRubricaToggle'),
    folderRubricaPanel: document.getElementById('folderRubricaPanel'),
    folderRubricaFiles: document.getElementById('folderRubricaFiles'),
    folderRubricaText: document.getElementById('folderRubricaText'),
    folderRubricaFileInput: document.getElementById('folderRubricaFileInput'),
    folderSaveRubricaBtn: document.getElementById('folderSaveRubricaBtn'),

    // Images panel (folder chat)
    folderImagesToggle: document.getElementById('folderImagesToggle'),
    folderImagesPanel: document.getElementById('folderImagesPanel'),
    folderContextImageFiles: document.getElementById('folderContextImageFiles'),
    folderContextImageFileInput: document.getElementById('folderContextImageFileInput'),

    // Modal confirmar
    confirmModal: document.getElementById('confirmModal'),
    modalTitle: document.getElementById('modalTitle'),
    modalMessage: document.getElementById('modalMessage'),
    modalCancel: document.getElementById('modalCancel'),
    modalConfirm: document.getElementById('modalConfirm'),

    // Modal renombrar
    renameModal: document.getElementById('renameModal'),
    renameInput: document.getElementById('renameInput'),
    renameCancelBtn: document.getElementById('renameCancelBtn'),
    renameConfirmBtn: document.getElementById('renameConfirmBtn'),

    // Logs
    logsContent: document.getElementById('logsContent'),
    logsCount: document.getElementById('logsCount'),
    clearLogsBtn: document.getElementById('clearLogsBtn'),
    copyLogsBtn: document.getElementById('copyLogsBtn'),
    logTimeStart: document.getElementById('logTimeStart'),
    logTimeEnd: document.getElementById('logTimeEnd'),

    // Toast
    toastContainer: document.getElementById('toastContainer'),

    // Cancel / Stop
    cancelProcessBtn: document.getElementById('cancelProcessBtn'),
    stopAppBtn: document.getElementById('stopAppBtn'),

    // Remoto
    remoteBadge: document.getElementById('remoteBadge'),
    remoteText: document.getElementById('remoteText')
};

// ============================================
// Inicialización
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initUpload();
    initDetail();
    initChat();
    initFolderChat();
    initModal();
    initRenameModal();
    initLogs();
    initCancelStop();
    initPanels();
    checkSystemStatus();
    loadClasses();
    startVramPolling();
    detectRemoteConnection();

    // Performance: set will-change on chat containers
    if (elements.chatMessages) elements.chatMessages.style.willChange = 'transform';
    if (elements.folderChatMessages) elements.folderChatMessages.style.willChange = 'transform';
});

// ============================================
// Navegación
// ============================================

function initNavigation() {
    elements.navItems.forEach(item => {
        item.addEventListener('click', () => {
            const section = item.dataset.section;
            navigateTo(section);
        });
    });
}

function navigateTo(section) {
    // Actualizar nav
    elements.navItems.forEach(item => {
        item.classList.toggle('active', item.dataset.section === section);
    });

    // Actualizar secciones
    elements.sections.forEach(s => {
        s.classList.remove('active');
    });

    const targetSection = document.getElementById(`${section}-section`);
    if (targetSection) {
        targetSection.classList.add('active');
    }

    state.currentSection = section;

    // Recargar clases si navegamos a esa sección
    if (section === 'classes') {
        loadClasses();
    }

    // Logs: iniciar/detener polling
    if (section === 'logs') {
        startLogsPolling();
    } else {
        stopLogsPolling();
    }
}

// ============================================
// Estado del Sistema
// ============================================

async function checkSystemStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();

        // GPU Status
        if (data.gpu_available) {
            elements.gpuStatus.className = 'status-dot success';
            elements.gpuText.textContent = data.gpu_info?.name || 'GPU disponible';
            // Mostrar VRAM inicial si el servidor la devuelve
            if (data.gpu_info?.vram_total_gb != null) {
                updateVramDisplay(data.gpu_info);
            }
        } else {
            elements.gpuStatus.className = 'status-dot warning';
            elements.gpuText.textContent = 'GPU no disponible (CPU)';
            elements.vramItem.style.display = 'none';
        }

        // Gemini Status
        if (data.gemini_configured) {
            elements.geminiStatus.className = 'status-dot success';
            elements.geminiText.textContent = 'Gemini conectado';
        } else {
            elements.geminiStatus.className = 'status-dot error';
            elements.geminiText.textContent = 'Gemini no configurado';
        }

        // OpenAI: guardar estado y deshabilitar opción si no está configurada
        state.openaiConfigured = data.openai_configured || false;
        const openaiOption = elements.modelSelect.querySelector('option[value="openai"]');
        if (openaiOption && !state.openaiConfigured) {
            openaiOption.disabled = true;
            openaiOption.textContent = 'OpenAI API (no configurada)';
        }

    } catch (error) {
        console.error('Error checking status:', error);
        elements.gpuStatus.className = 'status-dot error';
        elements.gpuText.textContent = 'Error de conexión';
        elements.geminiStatus.className = 'status-dot error';
        elements.geminiText.textContent = 'Error de conexión';
    }
}

// ============================================
// VRAM en tiempo real
// ============================================

function updateVramDisplay(stats) {
    if (!stats || !stats.vram_total_gb) {
        elements.vramItem.style.display = 'none';
        return;
    }
    elements.vramItem.style.display = 'flex';
    const pct = stats.vram_used_pct ?? 0;
    elements.vramBarFill.style.width = `${pct}%`;
    elements.vramBarFill.className = 'vram-bar-fill'
        + (pct >= 90 ? ' vram-crit' : pct >= 70 ? ' vram-warn' : '');

    // Mostrar carga GPU% y temperatura si pynvml las devuelve
    let prefix = '';
    if (stats.gpu_util_pct != null) {
        const uc = stats.gpu_util_pct >= 90 ? 'vram-crit' : stats.gpu_util_pct >= 60 ? 'vram-warn' : '';
        prefix = `<span class="gpu-stat ${uc}">GPU ${stats.gpu_util_pct}%</span>`;
        if (stats.gpu_temp_c != null) {
            const tc = stats.gpu_temp_c >= 85 ? 'vram-crit' : stats.gpu_temp_c >= 70 ? 'vram-warn' : '';
            prefix += `<span class="gpu-stat ${tc}"> · ${stats.gpu_temp_c}°C</span>`;
        }
        prefix += `<span class="gpu-stat gpu-sep"> · </span>`;
    }
    elements.vramText.innerHTML =
        prefix + `VRAM ${stats.vram_used_gb.toFixed(1)} / ${stats.vram_total_gb.toFixed(1)} GB (${pct}%)`;
}

async function fetchVramStats() {
    try {
        const res = await fetch('/api/gpu-stats');
        const data = await res.json();
        if (data.gpu_available) {
            updateVramDisplay(data);
        }
    } catch (_) { /* ignorar si el servidor está ocupado */ }
}

function startVramPolling() {
    // Primera llamada inmediata; luego cada 3 segundos
    fetchVramStats();
    setInterval(fetchVramStats, 3000);
}

function detectRemoteConnection() {
    const h = location.hostname;
    const isLocal = h === '127.0.0.1' || h === 'localhost' || h === '::1';
    if (!isLocal) {
        elements.remoteBadge.style.display = 'flex';
        elements.remoteText.textContent = `Remoto (${h})`;
    }
}

// ============================================
// Cancelar procesamiento / Cerrar programa
// ============================================

function initCancelStop() {
    elements.cancelProcessBtn.addEventListener('click', cancelProcessing);
    elements.stopAppBtn.addEventListener('click', stopApp);
}

async function cancelProcessing() {
    state.cancelRequested = true;
    elements.cancelProcessBtn.disabled = true;
    elements.cancelProcessBtn.textContent = 'Cancelando...';
    // Pedir al servidor que se detenga en el próximo checkpoint
    await fetch('/api/process/cancel', { method: 'POST' }).catch(() => {});
    // Abortar el fetch en curso (no esperar la respuesta del servidor)
    if (state.abortController) {
        state.abortController.abort();
    }
    updateProgress(0, 'Cancelado por el usuario');
    elements.cancelProcessBtn.style.display = 'none';
    elements.cancelProcessBtn.disabled = false;
    elements.cancelProcessBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="13" height="13"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Cancelar procesamiento`;
}

function stopApp() {
    showConfirmModal(
        'Cerrar programa',
        '¿Deseas cerrar el servidor y la aplicación? Se perderá el procesamiento en curso.',
        async () => {
            await fetch('/api/stop', { method: 'POST' }).catch(() => {});
            document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;color:#94a3b8;background:#0d0f14;font-size:1.1rem;">Servidor cerrado. Puedes cerrar esta ventana.</div>';
        }
    );
}

// ============================================
// Upload de Video — Cola múltiple
// ============================================

function initUpload() {
    elements.uploadArea.addEventListener('click', () => elements.fileInput.click());

    elements.fileInput.addEventListener('change', (e) => {
        addFilesToQueue(e.target.files);
        elements.fileInput.value = ''; // permite re-seleccionar los mismos archivos
    });

    elements.uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        elements.uploadArea.classList.add('drag-over');
    });
    elements.uploadArea.addEventListener('dragleave', () => {
        elements.uploadArea.classList.remove('drag-over');
    });
    elements.uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        elements.uploadArea.classList.remove('drag-over');
        const videos = [...e.dataTransfer.files].filter(f => f.type.startsWith('video/'));
        if (videos.length === 0) {
            showToast('error', 'Sin videos', 'Arrastra archivos de video');
            return;
        }
        addFilesToQueue(videos);
    });

    elements.processBtn.addEventListener('click', processQueue);

    // Nueva carpeta
    elements.newFolderBtn.addEventListener('click', () => {
        elements.newFolderForm.style.display = 'block';
        elements.newFolderName.focus();
    });
    elements.cancelFolderBtn.addEventListener('click', () => {
        elements.newFolderForm.style.display = 'none';
        elements.newFolderName.value = '';
    });
    elements.createFolderBtn.addEventListener('click', createFolder);
    elements.newFolderName.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') createFolder();
        if (e.key === 'Escape') elements.cancelFolderBtn.click();
    });

    loadFolders();
    renderFailedHistory(); // mostrar videos fallidos de la sesión anterior
}

// ── Cola ──────────────────────────────────────

function addFilesToQueue(files) {
    for (const f of [...files]) {
        if (!f.type.startsWith('video/')) continue;
        // si había un error previo con ese nombre en el historial, quitarlo
        removeFromFailedHistory(f.name);
        // evitar duplicados con mismo nombre en estado pendiente
        if (state.queue.find(q => q.file.name === f.name && q.status === 'pending')) continue;
        state.queue.push({ file: f, status: 'pending', error: '', isGpuError: false });
    }
    renderQueue();
    updateProcessBtn();
}

function removeFromQueue(index) {
    if (state.queue[index]?.status === 'pending') {
        state.queue.splice(index, 1);
        renderQueue();
        updateProcessBtn();
    }
}

function renderQueue() {
    const list = elements.queueList;
    if (state.queue.length === 0) {
        list.style.display = 'none';
        return;
    }
    list.style.display = 'flex';

    const icons   = { pending: '⏳', processing: '⚙️', done: '✓', error: '✕' };
    const labels  = { pending: 'En espera', processing: 'Procesando...', done: 'Completado' };

    const dismissSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                        </svg>`;

    list.innerHTML = '';
    state.queue.forEach((item, i) => {
        const label = item.status === 'error' ? (item.error || 'Error') : labels[item.status];

        let actions = '';
        if (item.status === 'pending') {
            actions = `<button class="queue-remove" data-idx="${i}" title="Quitar">${dismissSvg}</button>`;
        } else if (item.status === 'error') {
            actions = `<div class="queue-item-actions">
                <button class="btn-retry" data-idx="${i}" title="Reintentar">↺ Reintentar</button>
                ${item.isGpuError ? `<button class="btn-retry-openai" data-idx="${i}" title="Usar OpenAI">☁ OpenAI</button>` : ''}
                <button class="queue-remove" data-idx="${i}" title="Quitar">${dismissSvg}</button>
            </div>`;
        }

        const div = document.createElement('div');
        div.className = `queue-item ${item.status}`;
        div.innerHTML = `
            <div class="queue-item-icon">${icons[item.status]}</div>
            <div class="queue-item-info">
                <div class="queue-item-name">${item.file.name}</div>
                <div class="queue-item-meta">${formatFileSize(item.file.size)} · <span class="status-${item.status}">${label}</span></div>
            </div>
            ${actions}`;
        list.appendChild(div);
    });

    list.querySelectorAll('.queue-remove').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const idx = parseInt(btn.dataset.idx);
            state.queue.splice(idx, 1);
            renderQueue();
            updateProcessBtn();
        });
    });
    list.querySelectorAll('.btn-retry').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.dataset.idx);
            state.queue[idx].status = 'pending';
            state.queue[idx].error  = '';
            renderQueue();
            updateProcessBtn();
        });
    });
    list.querySelectorAll('.btn-retry-openai').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.dataset.idx);
            state.queue[idx].status = 'pending';
            state.queue[idx].error  = '';
            state.queue[idx].isGpuError = false;
            elements.modelSelect.value = 'openai';
            renderQueue();
            updateProcessBtn();
        });
    });
}

function updateProcessBtn() {
    const pending = state.queue.filter(q => q.status === 'pending').length;
    elements.processBtn.disabled = pending === 0 || state.isProcessing;
    elements.processBtn.querySelector('span').textContent =
        pending <= 1 ? (pending === 1 ? 'Procesar 1 video' : 'Procesar') : `Procesar ${pending} videos`;
}

// ── Procesamiento ─────────────────────────────

async function processQueue() {
    const pending = state.queue.filter(q => q.status === 'pending');
    if (pending.length === 0 || state.isProcessing) return;

    state.isProcessing = true;
    state.cancelRequested = false;
    elements.processBtn.disabled = true;
    elements.progressContainer.style.display = 'block';
    elements.cancelProcessBtn.style.display = 'flex';

    const total = pending.length;
    let num = 0;

    if (total > 1) {
        elements.queueCounter.style.display = 'block';
    }

    for (let i = 0; i < state.queue.length; i++) {
        if (state.cancelRequested) break;

        const item = state.queue[i];
        if (item.status !== 'pending') continue;

        num++;
        item.status = 'processing';
        renderQueue();

        if (total > 1) {
            elements.queueCounter.textContent = `Video ${num} de ${total}`;
        }

        updateProgress(0, 'Subiendo video...');

        try {
            await processOneVideo(item, num, total);
            item.status = 'done';
        } catch (err) {
            if (err.name === 'AbortError' || state.cancelRequested) {
                item.status = 'error';
                item.error = 'Cancelado por el usuario';
                break;
            }
            item.status = 'error';
            item.error = err.message;
            showToast('error', `Error: ${item.file.name}`, err.message);
        }
        renderQueue();
    }

    state.isProcessing = false;
    state.cancelRequested = false;
    state.abortController = null;
    elements.cancelProcessBtn.style.display = 'none';
    elements.queueCounter.style.display = 'none';
    updateProcessBtn();
    loadClasses();

    const doneCount  = state.queue.filter(q => q.status === 'done').length;
    const errorCount = state.queue.filter(q => q.status === 'error').length;

    // Guardar fallidos en historial persistente
    if (errorCount > 0) {
        saveFailedHistory();
    }

    if (doneCount > 0) {
        updateProgress(100, `¡${doneCount} clase${doneCount > 1 ? 's' : ''} creada${doneCount > 1 ? 's' : ''}!`);
        if (total === 1 && doneCount === 1) {
            const last = state.queue.find(q => q.status === 'done');
            if (last?._classId) showClassDetail(last._classId);
        }
        if (errorCount === 0) {
            setTimeout(() => {
                state.queue = [];
                renderQueue();
                elements.progressContainer.style.display = 'none';
                updateProgress(0, 'Preparando...');
            }, 2500);
        }
    }

    if (elements.shutdownCheckbox.checked) {
        updateProgress(100, 'Apagando el equipo...');
        await fetch('/api/shutdown', { method: 'POST' }).catch(() => {});
    }
}

async function processOneVideo(item, currentNum, totalNum) {
    const formData = new FormData();
    formData.append('video', item.file);
    formData.append('model', elements.modelSelect.value);
    formData.append('folder_path', elements.folderSelect.value);

    state.abortController = new AbortController();
    const startTime = Date.now();

    function elapsedStr() {
        const sec = Math.floor((Date.now() - startTime) / 1000);
        if (sec < 5) return '';
        const mm = String(Math.floor(sec / 60)).padStart(2, '0');
        const ss = String(sec % 60).padStart(2, '0');
        return ` · ${mm}:${ss}`;
    }

    let statusInterval = null;

    async function pollStatus() {
        try {
            const res = await fetch('/api/system/status');
            const data = await res.json();
            const s = data.process;
            if (s.percent > 0) {
                const detail = s.detail ? ` (${s.detail})` : '';
                let gpuTag = '';
                if (data.gpu && data.gpu.gpu_available) {
                    const g = data.gpu;
                    gpuTag = ` · GPU ${g.gpu_util_pct ?? 0}%`;
                    if (g.gpu_temp_c != null) gpuTag += ` ${g.gpu_temp_c}°C`;
                    gpuTag += ` · VRAM ${g.vram_used_gb.toFixed(1)}/${g.vram_total_gb.toFixed(1)}GB`;
                }
                updateProgress(s.percent, s.step + detail + gpuTag + elapsedStr());
            }
            // Actualizar panel VRAM del nav también
            if (data.gpu && data.gpu.gpu_available) {
                updateVramDisplay(data.gpu);
            }
        } catch (_) { /* servidor ocupado */ }
    }

    statusInterval = setInterval(pollStatus, 1500);
    pollStatus();

    try {
        const response = await fetch('/api/process', {
            method: 'POST',
            body: formData,
            signal: state.abortController.signal
        });
        clearInterval(statusInterval);

        const data = await response.json();

        if (response.ok && data.success) {
            item._classId = data.class?.id;
            showToast('success', 'Clase creada', data.class.name);
            return;
        }

        if (data.gpu_failed && data.openai_available) {
            item.isGpuError = true;
            throw new Error('Fallo en GPU — usa el botón ☁ OpenAI para reintentar en la nube.');
        }

        throw new Error(data.error || 'Error desconocido');

    } catch (err) {
        clearInterval(statusInterval);
        throw err;
    }
}

// ── Historial de errores (localStorage) ───────

const HISTORY_KEY = 'vtr_failed_videos';

function saveFailedHistory() {
    const failed = state.queue.filter(q => q.status === 'error').map(q => ({
        name:      q.file.name,
        sizeLabel: formatFileSize(q.file.size),
        error:     q.error,
        isGpuError: q.isGpuError,
        savedAt:   new Date().toISOString()
    }));
    if (failed.length === 0) return;
    // Combinar con historial anterior (sin duplicar por nombre)
    const prev = loadRawHistory().filter(p => !failed.find(f => f.name === p.name));
    localStorage.setItem(HISTORY_KEY, JSON.stringify([...prev, ...failed]));
    renderFailedHistory();
}

function loadRawHistory() {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); } catch { return []; }
}

function removeFromFailedHistory(name) {
    const updated = loadRawHistory().filter(h => h.name !== name);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(updated));
    renderFailedHistory();
}

function clearAllFailedHistory() {
    localStorage.removeItem(HISTORY_KEY);
    renderFailedHistory();
}

function renderFailedHistory() {
    const panel = elements.failedHistoryPanel;
    const history = loadRawHistory();
    if (history.length === 0) {
        panel.style.display = 'none';
        return;
    }
    panel.style.display = 'block';
    const dismissSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
    panel.innerHTML = `
        <div class="fh-header">
            <span>⚠ Videos que fallaron en la sesión anterior</span>
            <button class="fh-clear-all" id="fhClearAll">Limpiar todo</button>
        </div>
        <div class="fh-hint">Arrastra los archivos de nuevo para reintentar</div>
        <div class="fh-list">
            ${history.map(h => `
                <div class="fh-item">
                    <div class="fh-item-info">
                        <span class="fh-item-name">${h.name}</span>
                        <span class="fh-item-meta">${h.sizeLabel} · <span class="status-error">${h.error}</span></span>
                    </div>
                    <button class="fh-dismiss" data-name="${h.name}" title="Quitar">${dismissSvg}</button>
                </div>`).join('')}
        </div>`;
    panel.querySelector('#fhClearAll').addEventListener('click', clearAllFailedHistory);
    panel.querySelectorAll('.fh-dismiss').forEach(btn => {
        btn.addEventListener('click', () => removeFromFailedHistory(btn.dataset.name));
    });
}

function updateProgress(percent, text) {
    elements.progressFill.style.width = `${percent}%`;
    elements.progressText.textContent = text;
    elements.progressPercent.textContent = `${percent}%`;
}

// ============================================
// Gestión de carpetas
// ============================================

async function loadFolders() {
    try {
        const response = await fetch('/api/folders');
        const data = await response.json();
        populateFolderSelects(data.folders || []);
    } catch (error) {
        console.error('Error cargando carpetas:', error);
    }
}

function populateFolderSelects(folders) {
    const buildOptions = (includeRoot, rootLabel) => {
        const root = `<option value="">${rootLabel}</option>`;
        const opts = folders.map(f => {
            const indent = '\u00a0\u00a0'.repeat(f.depth) + (f.depth > 0 ? '└ ' : '');
            return `<option value="${escapeHtml(f.path)}">${indent}${escapeHtml(f.name)}</option>`;
        }).join('');
        return root + opts;
    };

    elements.folderSelect.innerHTML = buildOptions(true, 'Raíz (sin carpeta)');
    elements.newFolderParentSelect.innerHTML = buildOptions(true, 'En la raíz');
}

async function createFolder() {
    const name = elements.newFolderName.value.trim();
    if (!name) {
        showToast('error', 'Error', 'Escribe un nombre para la carpeta');
        return;
    }
    const parent = elements.newFolderParentSelect.value;
    const fullPath = parent ? `${parent}/${name}` : name;

    try {
        const response = await fetch('/api/folders', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: fullPath })
        });
        const data = await response.json();
        if (data.success) {
            showToast('success', 'Carpeta creada', `"${data.folder.name}" lista para usar`);
            elements.newFolderForm.style.display = 'none';
            elements.newFolderName.value = '';
            await loadFolders();
            elements.folderSelect.value = data.folder.path;
        } else {
            throw new Error(data.error || 'Error al crear carpeta');
        }
    } catch (error) {
        showToast('error', 'Error', error.message);
    }
}

// ============================================
// Lista de Clases
// ============================================

async function loadClasses() {
    try {
        const response = await fetch('/api/classes');
        const data = await response.json();

        state.classes = data.classes || [];
        renderClasses();

    } catch (error) {
        console.error('Error loading classes:', error);
        showToast('error', 'Error', 'No se pudieron cargar las clases');
    }
}

function renderClasses() {
    if (state.classes.length === 0) {
        elements.classesGrid.innerHTML = '';
        elements.emptyClasses.style.display = 'block';
        return;
    }

    elements.emptyClasses.style.display = 'none';

    const tree = buildFolderTree(state.classes);
    elements.classesGrid.innerHTML = renderFolderNode(tree, 0);
    attachClassCardListeners();
}

function buildFolderTree(classes) {
    const root = { classes: [], children: {}, path: '', name: '' };
    for (const cls of classes) {
        const folderPath = cls.folder_path || '';
        if (!folderPath) {
            root.classes.push(cls);
        } else {
            const parts = folderPath.split('/');
            let node = root;
            let currentPath = '';
            for (const part of parts) {
                currentPath = currentPath ? currentPath + '/' + part : part;
                if (!node.children[part]) {
                    node.children[part] = { classes: [], children: {}, path: currentPath, name: part };
                }
                node = node.children[part];
            }
            node.classes.push(cls);
        }
    }
    return root;
}

function countClasses(node) {
    let count = node.classes.length;
    for (const child of Object.values(node.children)) {
        count += countClasses(child);
    }
    return count;
}

function renderClassCard(cls) {
    return `<div class="class-card" data-id="${escapeHtml(cls.id)}">
            <div class="class-card-header">
                <div class="class-card-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                    </svg>
                </div>
                <div class="class-card-actions">
                    <button class="btn-icon rename" data-id="${escapeHtml(cls.id)}" data-name="${escapeHtml(cls.name.split(' · ')[0])}" title="Renombrar clase">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                        </svg>
                    </button>
                    <button class="btn-icon delete" data-id="${escapeHtml(cls.id)}" title="Eliminar clase">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        </svg>
                    </button>
                </div>
            </div>
            <h3 class="class-card-title">${escapeHtml(cls.name)}</h3>
            <div class="class-card-date">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                    <line x1="16" y1="2" x2="16" y2="6"/>
                    <line x1="8" y1="2" x2="8" y2="6"/>
                    <line x1="3" y1="10" x2="21" y2="10"/>
                </svg>
                <span>${escapeHtml(cls.created_at_formatted)}</span>
            </div>
            <div class="class-card-stats">
                <div class="stat">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                    </svg>
                    <span>${cls.segment_count} segmentos</span>
                </div>
            </div>
        </div>`;
}

function renderFolderNode(node, depth) {
    let html = '';

    // Clases sin carpeta (solo en la raíz)
    if (depth === 0 && node.classes.length > 0) {
        html += '<div class="classes-group">' + node.classes.map(renderClassCard).join('') + '</div>';
    }

    // Secciones de carpeta
    const sortedChildren = Object.entries(node.children).sort(([a], [b]) => a.localeCompare(b));
    for (const [, childNode] of sortedChildren) {
        const total = countClasses(childNode);
        const folderId = 'folder-' + childNode.path.replace(/[^a-zA-Z0-9]/g, '-');
        const isCollapsed = state.collapsedFolders.has(childNode.path);

        html += `<div class="folder-section" data-depth="${depth}">
<div class="folder-section-header" data-folderid="${folderId}" data-folderpath="${escapeHtml(childNode.path)}">
    <div class="folder-section-left">
        <svg class="folder-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
        <span class="folder-section-name">${escapeHtml(childNode.name)}</span>
        <span class="folder-class-count">${total}</span>
    </div>
    <div class="folder-section-right">
        <button class="btn-folder-chat" data-folderpath="${escapeHtml(childNode.path)}" data-foldername="${escapeHtml(childNode.name)}" data-classcount="${total}" title="Chat general de carpeta">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            <span>Chat</span>
        </button>
        <svg class="folder-toggle-arrow${isCollapsed ? ' collapsed' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
    </div>
</div>
<div class="folder-section-content${isCollapsed ? ' hidden' : ''}" id="${folderId}">
    ${childNode.classes.length > 0 ? '<div class="classes-group">' + childNode.classes.map(renderClassCard).join('') + '</div>' : ''}
    ${renderFolderNode(childNode, depth + 1)}
</div>
</div>`;
    }

    return html;
}

function attachClassCardListeners() {
    document.querySelectorAll('.class-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (e.target.closest('.btn-icon')) return;
            showClassDetail(card.dataset.id);
        });
    });

    document.querySelectorAll('.class-card .btn-icon.rename').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            showRenameModal(btn.dataset.id, btn.dataset.name);
        });
    });

    document.querySelectorAll('.class-card .btn-icon.delete').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            confirmDeleteClass(btn.dataset.id);
        });
    });

    // Botones de chat de carpeta
    document.querySelectorAll('.btn-folder-chat').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const folderPath = btn.dataset.folderpath;
            const folderName = btn.dataset.foldername;
            const classCount = parseInt(btn.dataset.classcount, 10);
            showFolderChat(folderPath, folderName, classCount);
        });
    });

    document.querySelectorAll('.folder-section-header').forEach(header => {
        header.addEventListener('click', (e) => {
            if (e.target.closest('.btn-folder-chat')) return;
            const folderId = header.dataset.folderid;
            const folderPath = header.dataset.folderpath;
            const content = document.getElementById(folderId);
            const arrow = header.querySelector('.folder-toggle-arrow');
            if (content.classList.contains('hidden')) {
                content.classList.remove('hidden');
                arrow.classList.remove('collapsed');
                state.collapsedFolders.delete(folderPath);
            } else {
                content.classList.add('hidden');
                arrow.classList.add('collapsed');
                state.collapsedFolders.add(folderPath);
            }
        });
    });
}

// ============================================
// Detalle de Clase
// ============================================

function initDetail() {
    // Botón volver
    elements.backBtn.addEventListener('click', () => {
        navigateTo('classes');
    });

    // Tabs
    elements.tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            switchTab(tabName);
        });
    });

    // Botón descargar transcripción
    elements.downloadTranscriptionBtn.addEventListener('click', downloadTranscription);

    // Botones descargar slides
    elements.downloadSlidesMdBtn.addEventListener('click',  () => downloadSlides('markdown'));
    elements.downloadSlidesPdfBtn.addEventListener('click', () => downloadSlides('pdf'));

    // Botón regenerar slides
    elements.regenerateSlidesBtn.addEventListener('click', regenerateSlidesDocument);

    // Botón regenerar resumen
    elements.regenerateSummaryBtn.addEventListener('click', regenerateSummary);
}

function switchTab(tabName) {
    elements.tabs.forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === tabName);
    });

    elements.tabContents.forEach(content => {
        content.classList.toggle('active', content.id === `tab-${tabName}`);
    });
}

async function showClassDetail(classId) {
    try {
        // Cargar información de la clase
        const response = await fetch(`/api/classes/${classId}`);
        const classData = await response.json();

        if (!response.ok) {
            throw new Error(classData.error || 'Clase no encontrada');
        }

        state.currentClass = classData;

        // Actualizar header
        elements.detailTitle.textContent = classData.name;
        elements.detailDate.textContent = classData.created_at_formatted;

        // Cargar resumen
        if (classData.summary) {
            elements.summaryContent.innerHTML = parseMarkdown(classData.summary);
        } else {
            elements.summaryContent.innerHTML = '<p class="text-muted">No hay resumen disponible</p>';
        }

        // Cargar transcripción
        await loadTranscription(classId);

        // Cargar slides si existen
        if (classData.has_slides) {
            elements.slidesBtnTab.style.display = '';
            await loadSlides(classId);
        } else {
            elements.slidesBtnTab.style.display = 'none';
            elements.slidesContent.innerHTML = '';
        }

        // Iniciar sesión de chat y restaurar historial
        await loadClassChat(classId);

        // Mostrar sección de detalle
        elements.sections.forEach(s => s.classList.remove('active'));
        elements.detailSection.classList.add('active');
        switchTab('summary');

        // Actualizar navegación
        elements.navItems.forEach(item => item.classList.remove('active'));

    } catch (error) {
        console.error('Error loading class detail:', error);
        showToast('error', 'Error', 'No se pudo cargar la clase');
    }
}

async function loadTranscription(classId) {
    try {
        const response = await fetch(`/api/classes/${classId}/transcription`);
        const data = await response.json();

        if (data.segments && data.segments.length > 0) {
            state.currentTranscriptionSegments = data.segments;
            elements.transcriptionCount.textContent = `${data.segments.length} segmentos`;
            elements.transcriptionContent.innerHTML = data.segments.map(segment => `
                <div class="transcription-segment">
                    <div class="segment-timestamp">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"/>
                            <polyline points="12 6 12 12 16 14"/>
                        </svg>
                        <span>${segment.timestamp_inicio} - ${segment.timestamp_fin}</span>
                    </div>
                    <div class="segment-text">${escapeHtml(segment.texto)}</div>
                </div>
            `).join('');
        } else {
            state.currentTranscriptionSegments = null;
            elements.transcriptionCount.textContent = '';
            elements.transcriptionContent.innerHTML = '<p class="text-muted">No hay transcripción disponible</p>';
        }

    } catch (error) {
        console.error('Error loading transcription:', error);
        state.currentTranscriptionSegments = null;
        elements.transcriptionContent.innerHTML = '<p class="text-muted">Error al cargar la transcripción</p>';
    }
}

// ============================================
// Descarga de transcripción para IA
// ============================================

function buildAiMarkdown(segments, className, date, duration) {
    const BLOCK_SECONDS = 120; // agrupar cada 2 minutos

    function toSeconds(ts) {
        if (!ts) return 0;
        const parts = ts.split(':');
        return parseInt(parts[0] || 0) * 3600 + parseInt(parts[1] || 0) * 60 + parseFloat(parts[2] || 0);
    }

    function fmtSeconds(s) {
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        const sec = s % 60;
        return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
    }

    const blocks = [];
    let currentBlock = null;
    let blockStart = -1;

    for (const seg of segments) {
        const seconds = toSeconds(seg.timestamp_inicio);
        const alignedStart = Math.floor(seconds / BLOCK_SECONDS) * BLOCK_SECONDS;
        if (currentBlock === null || alignedStart !== blockStart) {
            if (currentBlock) blocks.push(currentBlock);
            blockStart = alignedStart;
            currentBlock = { label: fmtSeconds(blockStart), texts: [] };
        }
        const text = (seg.texto || '').trim();
        if (text) currentBlock.texts.push(text);
    }
    if (currentBlock && currentBlock.texts.length > 0) blocks.push(currentBlock);

    const lines = [
        `# ${className}`,
        ``,
        `**Fecha:** ${date}  `,
        `**Duración:** ${duration}  `,
        `**Segmentos:** ${segments.length}  `,
        ``,
        `---`,
        ``
    ];

    for (const block of blocks) {
        lines.push(`[${block.label}]`);
        lines.push(block.texts.join(' '));
        lines.push(``);
    }

    return lines.join('\n');
}

// ── Slides / Presentación ─────────────────────

async function regenerateSlidesDocument() {
    if (!state.currentClass) return;
    const btn = elements.regenerateSlidesBtn;
    const origHTML = btn.innerHTML;
    btn.disabled = true;

    // Crear barra de progreso inline debajo del header de slides
    const progressEl = document.createElement('div');
    progressEl.className = 'regen-progress';
    progressEl.innerHTML = `
        <div class="regen-progress-bar"><div class="regen-progress-fill" id="regenFill"></div></div>
        <div class="regen-progress-info">
            <span class="regen-step" id="regenStep">Iniciando...</span>
            <span class="regen-eta" id="regenEta"></span>
        </div>`;
    const tabHeader = btn.closest('.slides-tab-header');
    if (tabHeader && tabHeader.nextSibling) {
        tabHeader.parentNode.insertBefore(progressEl, tabHeader.nextSibling);
    } else {
        elements.slidesContent.parentNode.insertBefore(progressEl, elements.slidesContent);
    }

    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin">
        <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
    </svg> Regenerando...`;

    try {
        const classId = state.currentClass.id;
        const url = `/api/classes/${encodeURIComponent(classId).replace(/%2F/g, '/')}/slides/regenerate`;
        const res = await fetch(url, { method: 'POST' });

        if (!res.ok) {
            const errData = await res.json();
            showToast('error', 'Error', errData.error || 'No se pudo regenerar');
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let done = false;

        while (!done) {
            const { value, done: streamDone } = await reader.read();
            done = streamDone;
            if (value) buffer += decoder.decode(value, { stream: true });

            // Parsear eventos SSE del buffer
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            let eventType = '';
            let eventData = '';
            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    eventType = line.slice(7).trim();
                } else if (line.startsWith('data: ')) {
                    eventData = line.slice(6);
                    try {
                        const data = JSON.parse(eventData);
                        const fill = document.getElementById('regenFill');
                        const step = document.getElementById('regenStep');
                        const eta = document.getElementById('regenEta');

                        if (eventType === 'progress') {
                            if (fill) fill.style.width = `${data.percent}%`;
                            if (step) step.textContent = data.step;
                            if (eta) eta.textContent = data.eta ? `ETA: ${data.eta}` : '';
                        } else if (eventType === 'done') {
                            if (fill) fill.style.width = '100%';
                            if (step) step.textContent = `Completado en ${data.elapsed}s`;
                            showToast('success', 'Regenerado', `Documento actualizado en ${data.elapsed}s`);
                            setTimeout(async () => {
                                await loadSlides(classId);
                            }, 500);
                        } else if (eventType === 'error') {
                            showToast('error', 'Error', data.error || 'Error desconocido');
                        }
                    } catch (_) { /* ignorar líneas no-JSON */ }
                    eventType = '';
                    eventData = '';
                }
            }
        }
    } catch (err) {
        showToast('error', 'Error', 'No se pudo conectar al servidor');
    } finally {
        btn.disabled = false;
        btn.innerHTML = origHTML;
        // Remover barra de progreso después de 1.5s
        setTimeout(() => { if (progressEl.parentNode) progressEl.parentNode.removeChild(progressEl); }, 1500);
    }
}

async function regenerateSummary() {
    if (!state.currentClass) return;
    const btn = elements.regenerateSummaryBtn;
    const origHTML = btn.innerHTML;
    btn.disabled = true;

    // Crear barra de progreso inline
    const progressEl = document.createElement('div');
    progressEl.className = 'regen-progress';
    progressEl.innerHTML = `
        <div class="regen-progress-bar"><div class="regen-progress-fill" id="regenSummaryFill"></div></div>
        <div class="regen-progress-info">
            <span class="regen-step" id="regenSummaryStep">Iniciando...</span>
            <span class="regen-eta" id="regenSummaryEta"></span>
        </div>`;
    elements.summaryContent.parentNode.insertBefore(progressEl, elements.summaryContent);

    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin">
        <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
    </svg> Regenerando...`;

    try {
        const classId = state.currentClass.id;
        const url = `/api/classes/${encodeURIComponent(classId).replace(/%2F/g, '/')}/summary/regenerate`;
        const res = await fetch(url, { method: 'POST' });

        if (!res.ok) {
            const errData = await res.json();
            showToast('error', 'Error', errData.error || 'No se pudo regenerar');
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let done = false;

        while (!done) {
            const { value, done: streamDone } = await reader.read();
            done = streamDone;
            if (value) buffer += decoder.decode(value, { stream: true });

            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            let eventType = '';
            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    eventType = line.slice(7).trim();
                } else if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        const fill = document.getElementById('regenSummaryFill');
                        const step = document.getElementById('regenSummaryStep');
                        const eta = document.getElementById('regenSummaryEta');

                        if (eventType === 'progress') {
                            if (fill) fill.style.width = `${data.percent}%`;
                            if (step) step.textContent = data.step;
                            if (eta) eta.textContent = data.eta ? `ETA: ${data.eta}` : '';
                        } else if (eventType === 'done') {
                            if (fill) fill.style.width = '100%';
                            if (step) step.textContent = `Completado en ${data.elapsed}s`;
                            showToast('success', 'Regenerado', `Resumen actualizado en ${data.elapsed}s`);
                            elements.summaryContent.innerHTML = parseMarkdown(data.summary);
                        } else if (eventType === 'error') {
                            showToast('error', 'Error', data.error || 'Error desconocido');
                        }
                    } catch (_) { /* ignorar */ }
                    eventType = '';
                }
            }
        }
    } catch (err) {
        showToast('error', 'Error', 'No se pudo conectar al servidor');
    } finally {
        btn.disabled = false;
        btn.innerHTML = origHTML;
        setTimeout(() => { if (progressEl.parentNode) progressEl.parentNode.removeChild(progressEl); }, 1500);
    }
}

async function loadSlides(classId) {
    try {
        const res  = await fetch(`/api/classes/${classId}/slides`);
        const data = await res.json();
        if (!res.ok || (!data.content && !data.document)) {
            elements.slidesContent.innerHTML = '<p class="text-muted">No hay slides disponibles</p>';
            return;
        }

        // Preferir documento IA si existe
        if (data.document) {
            elements.slidesCount.textContent = 'Documento generado por IA';
            elements.slidesContent.innerHTML =
                '<div class="slides-document markdown-body">' +
                parseMarkdown(data.document) +
                '</div>';
            // Renderizar bloques Mermaid
            renderMermaidBlocks(elements.slidesContent);
            return;
        }

        // Fallback: vista de tarjetas con datos en crudo
        const slides = parseSlidesMarkdown(data.content);
        elements.slidesCount.textContent = `${slides.length} slide${slides.length !== 1 ? 's' : ''}`;
        if (slides.length === 0) {
            elements.slidesContent.innerHTML = '<p class="text-muted">No se encontró contenido en los slides</p>';
            return;
        }
        const imgBase = `/api/classes/${classId}`;
        elements.slidesContent.innerHTML = slides.map(s => `
            <div class="slide-card">
                <div class="slide-card-header">
                    <span class="slide-num">Slide ${s.num}</span>
                    ${s.ts ? `<span class="slide-ts">${s.ts}</span>` : ''}
                </div>
                ${s.image ? `<div class="slide-card-image"><img src="${imgBase}/${escapeHtml(s.image)}" alt="Slide ${s.num}" loading="lazy"></div>` : ''}
                ${s.text ? `<div class="slide-card-text">${escapeHtml(s.text)}</div>` : ''}
                ${s.visual ? `<div class="slide-card-visual">
                    <span class="visual-label">Descripción visual</span>
                    <p>${escapeHtml(s.visual)}</p>
                </div>` : ''}
            </div>`).join('');
    } catch (err) {
        console.error('Error cargando slides:', err);
        elements.slidesContent.innerHTML = '<p class="text-muted">Error al cargar los slides</p>';
    }
}

function parseSlidesMarkdown(md) {
    // Normalizar saltos de línea (Windows \r\n → \n)
    md = md.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

    const slides = [];
    const headerRe = /^## Slide (\d+)\s*(?:\[([^\]]+)\])?/gm;
    let match;
    let prevEnd = 0;
    let prevSlide = null;

    while ((match = headerRe.exec(md)) !== null) {
        if (prevSlide !== null) {
            _assignSlideBody(prevSlide, md.slice(prevEnd, match.index));
            slides.push(prevSlide);
        }
        prevSlide = { num: match[1], ts: match[2] || '' };
        prevEnd = match.index + match[0].length;
    }

    if (prevSlide !== null) {
        _assignSlideBody(prevSlide, md.slice(prevEnd));
        slides.push(prevSlide);
    }

    return slides;
}

function _assignSlideBody(slide, rawBody) {
    // Eliminar separadores "---" y espacios sobrantes
    const body = rawBody.replace(/\n?---\s*\n?/g, '').trim();
    if (!body) {
        slide.text = '';
        slide.visual = '';
        slide.image = '';
        return;
    }
    const lines = body.split('\n');
    const textLines   = [];
    const visualLines = [];
    let imageRef = '';

    for (const l of lines) {
        // Capturar referencias a imágenes ![alt](path)
        const imgMatch = l.match(/^!\[.*?\]\((.+?)\)/);
        if (imgMatch) {
            if (!imageRef) imageRef = imgMatch[1];
            continue;
        }
        if (l.startsWith('> ')) {
            visualLines.push(l.slice(2));
        } else {
            textLines.push(l);
        }
    }

    slide.visual = visualLines.join('\n').trim();
    slide.image = imageRef;

    const textCandidate = textLines.join('\n').trim();
    // Fallback: si el filtrado de '> ' dejó el texto vacío pero hay contenido,
    // mostrar el cuerpo completo para no perder información.
    slide.text = textCandidate || body;
}

async function downloadSlides(format) {
    if (!state.currentClass) return;
    const btn = format === 'pdf' ? elements.downloadSlidesPdfBtn : elements.downloadSlidesMdBtn;
    const origText = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = 'Descargando...'; }
    const url = `/api/classes/${encodeURIComponent(state.currentClass.id).replace(/%2F/g, '/')}/slides/download?format=${format}`;
    try {
        const res = await fetch(url);
        if (!res.ok) {
            let msg = 'Error al descargar';
            try { msg = (await res.json()).error || msg; } catch (_) {}
            showToast('error', 'Error', msg);
            return;
        }
        const blob = await res.blob();
        const objUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = objUrl;
        const cd = res.headers.get('Content-Disposition') || '';
        const fnMatch = cd.match(/filename="([^"]+)"/);
        a.download = fnMatch ? fnMatch[1] : `slides.${format === 'pdf' ? 'pdf' : 'md'}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(objUrl);
        showToast('success', 'Descargado', `Archivo ${format.toUpperCase()} listo`);
    } catch (err) {
        showToast('error', 'Error', 'No se pudo conectar al servidor');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = origText; }
    }
}

function downloadTranscription() {
    if (!state.currentClass || !state.currentTranscriptionSegments) return;

    const segments = state.currentTranscriptionSegments;
    const className = state.currentClass.name || state.currentClass.id;
    const date = state.currentClass.created_at_formatted || '';
    const duration = segments.length > 0
        ? (segments[segments.length - 1].timestamp_fin || segments[segments.length - 1].timestamp_inicio || '')
        : '';

    const markdown = buildAiMarkdown(segments, className, date, duration);
    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${state.currentClass.id}_transcripcion.md`;
    a.click();
    URL.revokeObjectURL(url);
}

// ============================================
// Chat
// ============================================

function initChat() {
    // Enviar mensaje
    elements.sendChatBtn.addEventListener('click', sendChatMessage);

    // Enter para enviar
    elements.chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    });

    // Auto-resize textarea
    elements.chatInput.addEventListener('input', () => {
        elements.chatInput.style.height = 'auto';
        elements.chatInput.style.height = Math.min(elements.chatInput.scrollHeight, 150) + 'px';
    });

    // Limpiar chat
    elements.clearChatBtn.addEventListener('click', clearChat);
}

async function loadClassChat(classId) {
    try {
        // Iniciar sesión en el servidor (restaura historial desde disco en memoria)
        await fetch(`/api/chat/${classId}/start`, { method: 'POST' });

        // Obtener historial guardado
        const response = await fetch(`/api/chat/${classId}/history`);
        const data = await response.json();
        const history = data.history || [];

        if (history.length > 0) {
            // Usar DocumentFragment para batch DOM insertions
            elements.chatMessages.innerHTML = '';
            const fragment = document.createDocumentFragment();
            history.forEach(msg => {
                const role = msg.role === 'model' ? 'assistant' : msg.role;
                const el = _buildChatMessageElement(role, msg.content);
                fragment.appendChild(el);
            });
            elements.chatMessages.appendChild(fragment);
            requestAnimationFrame(() => {
                elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
            });
        } else {
            resetChat();
        }

        // Cargar archivos de conocimiento, rúbricas e imágenes
        await loadKnowledgeFiles(classId);
        await loadRubricaFiles(classId);
        await loadContextImages(classId);
    } catch (error) {
        console.error('Error loading chat session:', error);
        resetChat();
    }
}

async function sendChatMessage() {
    const message = elements.chatInput.value.trim();
    if (!message || !state.currentClass) return;

    // Limpiar input
    elements.chatInput.value = '';
    elements.chatInput.style.height = 'auto';

    // Ocultar mensaje de bienvenida
    const welcomeMsg = elements.chatMessages.querySelector('.chat-welcome');
    if (welcomeMsg) {
        welcomeMsg.style.display = 'none';
    }

    // Agregar mensaje del usuario
    addChatMessage('user', message);

    // Deshabilitar envío mientras se procesa
    elements.sendChatBtn.disabled = true;

    // Agregar indicador de "escribiendo"
    const typingId = addTypingIndicator();

    try {
        const response = await fetch(`/api/chat/${state.currentClass.id}/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });

        const data = await response.json();

        // Quitar indicador de "escribiendo"
        removeTypingIndicator(typingId);

        if (data.success) {
            addChatMessage('assistant', data.response);
        } else {
            throw new Error(data.error || 'Error en el chat');
        }

    } catch (error) {
        removeTypingIndicator(typingId);
        console.error('Error sending chat message:', error);
        addChatMessage('assistant', 'Lo siento, hubo un error al procesar tu mensaje. Por favor, intenta de nuevo.');
    } finally {
        elements.sendChatBtn.disabled = false;
    }
}

function _buildChatMessageElement(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${role}`;

    if (role === 'assistant') {
        messageDiv.innerHTML = parseMarkdown(content);
        // Wrap in container with copy button
        const wrapper = document.createElement('div');
        wrapper.className = 'chat-msg-wrapper';
        const copyBtn = document.createElement('button');
        copyBtn.className = 'btn-copy-chat';
        copyBtn.textContent = 'Copiar';
        copyBtn.addEventListener('click', () => {
            navigator.clipboard.writeText(content).then(() => {
                copyBtn.textContent = 'Copiado';
                setTimeout(() => { copyBtn.textContent = 'Copiar'; }, 2000);
            });
        });
        wrapper.appendChild(copyBtn);
        wrapper.appendChild(messageDiv);
        return wrapper;
    } else {
        messageDiv.textContent = content;
        return messageDiv;
    }
}

function addChatMessage(role, content) {
    const el = _buildChatMessageElement(role, content);
    elements.chatMessages.appendChild(el);
    requestAnimationFrame(() => {
        elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
    });
}

function addTypingIndicator() {
    const id = 'typing-' + Date.now();
    const typingDiv = document.createElement('div');
    typingDiv.id = id;
    typingDiv.className = 'chat-message assistant';
    typingDiv.innerHTML = '<div class="spinner"></div>';
    elements.chatMessages.appendChild(typingDiv);
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
    return id;
}

function removeTypingIndicator(id) {
    const typingDiv = document.getElementById(id);
    if (typingDiv) {
        typingDiv.remove();
    }
}

async function clearChat() {
    if (!state.currentClass) return;

    try {
        await fetch(`/api/chat/${state.currentClass.id}/clear`, { method: 'POST' });
        resetChat();
        showToast('success', 'Chat limpiado', 'El historial de conversación ha sido borrado');
    } catch (error) {
        console.error('Error clearing chat:', error);
        showToast('error', 'Error', 'No se pudo limpiar el chat');
    }
}

function resetChat() {
    elements.chatMessages.innerHTML = `
        <div class="chat-welcome">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            <h3>Chat con la Clase</h3>
            <p>Haz preguntas sobre el contenido de esta clase y obtendrás respuestas basadas en la transcripción.</p>
        </div>
    `;
    elements.chatInput.value = '';
}

// ============================================
// Chat General de Carpeta
// ============================================

function initFolderChat() {
    elements.folderChatBackBtn.addEventListener('click', () => navigateTo('classes'));

    elements.sendFolderChatBtn.addEventListener('click', sendFolderChatMessage);

    elements.folderChatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendFolderChatMessage();
        }
    });

    elements.folderChatInput.addEventListener('input', () => {
        elements.folderChatInput.style.height = 'auto';
        elements.folderChatInput.style.height = Math.min(elements.folderChatInput.scrollHeight, 150) + 'px';
    });

    elements.clearFolderChatBtn.addEventListener('click', clearFolderChat);
}

async function showFolderChat(folderPath, folderName, classCount) {
    state.currentFolder = { path: folderPath, name: folderName, classCount };

    // Actualizar UI del header
    elements.folderChatTitle.textContent = folderName.replace(/_/g, ' ');
    elements.folderChatSubtitle.textContent = `${classCount} clase${classCount !== 1 ? 's' : ''} en esta carpeta`;

    // Badge informativo
    elements.folderChatClassesBadge.innerHTML = `
        <div class="folder-chat-badge">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            <span>Carpeta: <strong>${escapeHtml(folderName.replace(/_/g, ' '))}</strong></span>
            <span class="badge-sep">·</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
            </svg>
            <span>${classCount} clase${classCount !== 1 ? 's' : ''} disponibles</span>
            <span class="badge-sep">·</span>
            <span class="badge-loading" id="folderChatLoadingBadge">Cargando conocimiento...</span>
        </div>`;

    // Mostrar sección de chat de carpeta
    elements.sections.forEach(s => s.classList.remove('active'));
    elements.folderChatSection.classList.add('active');
    elements.navItems.forEach(item => item.classList.remove('active'));

    // Resetear y cargar el chat
    resetFolderChat();
    await loadFolderChatSession(folderPath);

    // Load knowledge, rubrica and image files for folder
    await loadKnowledgeFiles(folderPath, elements.folderKnowledgeFiles);
    await loadRubricaFiles(folderPath, elements.folderRubricaFiles);
    await loadContextImages(folderPath, elements.folderContextImageFiles);
}

async function loadFolderChatSession(folderPath) {
    const loadingBadge = document.getElementById('folderChatLoadingBadge');
    try {
        // Iniciar sesión en el servidor
        const startRes = await fetch(`/api/folder-chat/${folderPath}/start`, { method: 'POST' });
        const startData = await startRes.json();

        if (!startRes.ok) {
            throw new Error(startData.error || 'Error al iniciar sesión de carpeta');
        }

        // Actualizar badge con número real de clases cargadas
        if (loadingBadge) {
            loadingBadge.textContent = startData.cached
                ? `✓ Listo (caché activo)`
                : `✓ Listo`;
            loadingBadge.classList.add('badge-ready');
        }

        // Cargar historial guardado
        const histRes = await fetch(`/api/folder-chat/${folderPath}/history`);
        const histData = await histRes.json();
        const history = histData.history || [];

        if (history.length > 0) {
            elements.folderChatMessages.innerHTML = '';
            const fragment = document.createDocumentFragment();
            history.forEach(msg => {
                const role = msg.role === 'model' ? 'assistant' : msg.role;
                const messageDiv = document.createElement('div');
                messageDiv.className = `chat-message ${role}`;
                if (role === 'assistant') {
                    messageDiv.innerHTML = parseMarkdown(msg.content);
                    const wrapper = document.createElement('div');
                    wrapper.className = 'chat-msg-wrapper';
                    const copyBtn = document.createElement('button');
                    copyBtn.className = 'btn-copy-chat';
                    copyBtn.textContent = 'Copiar';
                    copyBtn.addEventListener('click', () => {
                        navigator.clipboard.writeText(msg.content).then(() => {
                            copyBtn.textContent = 'Copiado';
                            setTimeout(() => { copyBtn.textContent = 'Copiar'; }, 2000);
                        });
                    });
                    wrapper.appendChild(copyBtn);
                    wrapper.appendChild(messageDiv);
                    fragment.appendChild(wrapper);
                } else {
                    messageDiv.textContent = msg.content;
                    fragment.appendChild(messageDiv);
                }
            });
            elements.folderChatMessages.appendChild(fragment);
            requestAnimationFrame(() => {
                elements.folderChatMessages.scrollTop = elements.folderChatMessages.scrollHeight;
            });
        }

    } catch (error) {
        console.error('Error cargando chat de carpeta:', error);
        if (loadingBadge) {
            loadingBadge.textContent = 'Error al cargar';
            loadingBadge.style.color = 'var(--error)';
        }
        showToast('error', 'Error', error.message || 'No se pudo cargar el chat de carpeta');
    }
}

async function sendFolderChatMessage() {
    const message = elements.folderChatInput.value.trim();
    if (!message || !state.currentFolder) return;

    elements.folderChatInput.value = '';
    elements.folderChatInput.style.height = 'auto';

    const welcome = elements.folderChatMessages.querySelector('.chat-welcome');
    if (welcome) welcome.style.display = 'none';

    addFolderChatMessage('user', message);
    elements.sendFolderChatBtn.disabled = true;

    const typingId = addFolderTypingIndicator();

    try {
        const res = await fetch(`/api/folder-chat/${state.currentFolder.path}/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });
        const data = await res.json();

        removeFolderTypingIndicator(typingId);

        if (data.success) {
            addFolderChatMessage('assistant', data.response);
        } else {
            throw new Error(data.error || 'Error en el chat de carpeta');
        }

    } catch (error) {
        removeFolderTypingIndicator(typingId);
        console.error('Error en chat de carpeta:', error);
        addFolderChatMessage('assistant', 'Lo siento, hubo un error al procesar tu pregunta. Por favor, intenta de nuevo.');
    } finally {
        elements.sendFolderChatBtn.disabled = false;
        elements.folderChatInput.focus();
    }
}

function addFolderChatMessage(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${role}`;

    if (role === 'assistant') {
        messageDiv.innerHTML = parseMarkdown(content);
        const wrapper = document.createElement('div');
        wrapper.className = 'chat-msg-wrapper';
        const copyBtn = document.createElement('button');
        copyBtn.className = 'btn-copy-chat';
        copyBtn.textContent = 'Copiar';
        copyBtn.addEventListener('click', () => {
            navigator.clipboard.writeText(content).then(() => {
                copyBtn.textContent = 'Copiado';
                setTimeout(() => { copyBtn.textContent = 'Copiar'; }, 2000);
            });
        });
        wrapper.appendChild(copyBtn);
        wrapper.appendChild(messageDiv);
        elements.folderChatMessages.appendChild(wrapper);
    } else {
        messageDiv.textContent = content;
        elements.folderChatMessages.appendChild(messageDiv);
    }
    requestAnimationFrame(() => {
        elements.folderChatMessages.scrollTop = elements.folderChatMessages.scrollHeight;
    });
}

function addFolderTypingIndicator() {
    const id = 'folder-typing-' + Date.now();
    const div = document.createElement('div');
    div.id = id;
    div.className = 'chat-message assistant';
    div.innerHTML = '<div class="spinner"></div>';
    elements.folderChatMessages.appendChild(div);
    elements.folderChatMessages.scrollTop = elements.folderChatMessages.scrollHeight;
    return id;
}

function removeFolderTypingIndicator(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

async function clearFolderChat() {
    if (!state.currentFolder) return;
    try {
        await fetch(`/api/folder-chat/${state.currentFolder.path}/clear`, { method: 'POST' });
        resetFolderChat();
        showToast('success', 'Chat limpiado', 'El historial de la carpeta ha sido borrado');
    } catch (error) {
        console.error('Error limpiando chat de carpeta:', error);
        showToast('error', 'Error', 'No se pudo limpiar el chat');
    }
}

function resetFolderChat() {
    elements.folderChatMessages.innerHTML = `
        <div class="chat-welcome" id="folderChatWelcome">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                <path d="M12 11v6M9 14h6" stroke-width="1.5"/>
            </svg>
            <h3>Chat General de Carpeta</h3>
            <p>Pregunta sobre cualquier clase de esta carpeta. La IA conoce las transcripciones, resúmenes y slides de todas las clases.</p>
        </div>`;
    elements.folderChatInput.value = '';
}

// ============================================
// Modal de Confirmación
// ============================================

let modalCallback = null;

function initModal() {
    elements.modalCancel.addEventListener('click', () => {
        elements.confirmModal.classList.remove('active');
        modalCallback = null;
    });

    elements.modalConfirm.addEventListener('click', () => {
        if (modalCallback) {
            modalCallback();
        }
        elements.confirmModal.classList.remove('active');
        modalCallback = null;
    });

    // Cerrar al hacer clic fuera
    elements.confirmModal.addEventListener('click', (e) => {
        if (e.target === elements.confirmModal) {
            elements.confirmModal.classList.remove('active');
            modalCallback = null;
        }
    });
}

function showConfirmModal(title, message, onConfirm) {
    elements.modalTitle.textContent = title;
    elements.modalMessage.textContent = message;
    modalCallback = onConfirm;
    elements.confirmModal.classList.add('active');
}

function confirmDeleteClass(classId) {
    const cls = state.classes.find(c => c.id === classId);
    showConfirmModal(
        'Eliminar clase',
        `¿Estás seguro de que deseas eliminar "${cls?.name || classId}"? Esta acción no se puede deshacer.`,
        () => deleteClass(classId)
    );
}

async function deleteClass(classId) {
    try {
        const response = await fetch(`/api/classes/${classId}`, { method: 'DELETE' });
        const data = await response.json();

        if (response.ok) {
            showToast('success', 'Clase eliminada', 'La clase ha sido eliminada correctamente');
            loadClasses();

            // Si estamos viendo esa clase, volver a la lista
            if (state.currentClass?.id === classId) {
                navigateTo('classes');
            }
        } else {
            throw new Error(data.error || 'Error al eliminar');
        }

    } catch (error) {
        console.error('Error deleting class:', error);
        showToast('error', 'Error', 'No se pudo eliminar la clase');
    }
}

// ============================================
// Renombrar Clase
// ============================================

let renameClassId = null;

function initRenameModal() {
    elements.renameCancelBtn.addEventListener('click', () => {
        elements.renameModal.classList.remove('active');
        renameClassId = null;
    });

    elements.renameConfirmBtn.addEventListener('click', renameClass);

    elements.renameInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') renameClass();
        if (e.key === 'Escape') {
            elements.renameModal.classList.remove('active');
            renameClassId = null;
        }
    });

    elements.renameModal.addEventListener('click', (e) => {
        if (e.target === elements.renameModal) {
            elements.renameModal.classList.remove('active');
            renameClassId = null;
        }
    });
}

function showRenameModal(classId, currentName) {
    renameClassId = classId;
    elements.renameInput.value = currentName;
    elements.renameModal.classList.add('active');
    setTimeout(() => {
        elements.renameInput.focus();
        elements.renameInput.select();
    }, 50);
}

async function renameClass() {
    if (!renameClassId) return;
    const newName = elements.renameInput.value.trim();
    if (!newName) {
        showToast('warning', 'Nombre inválido', 'El nombre no puede estar vacío');
        return;
    }

    try {
        const response = await fetch(`/api/classes/${renameClassId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName })
        });
        const data = await response.json();

        if (response.ok) {
            elements.renameModal.classList.remove('active');
            renameClassId = null;
            showToast('success', 'Clase renombrada', 'El nombre ha sido actualizado');
            loadClasses();
        } else {
            throw new Error(data.error || 'Error al renombrar');
        }
    } catch (error) {
        console.error('Error renaming class:', error);
        showToast('error', 'Error', 'No se pudo renombrar la clase');
    }
}

// ============================================
// Knowledge & Rubrica Panels
// ============================================

function initPanels() {
    // Class chat panels
    _initToggle(elements.knowledgeToggle, elements.knowledgePanel);
    _initToggle(elements.rubricaToggle, elements.rubricaPanel);
    _initToggle(elements.imagesToggle, elements.imagesPanel);

    // Folder chat panels
    _initToggle(elements.folderKnowledgeToggle, elements.folderKnowledgePanel);
    _initToggle(elements.folderRubricaToggle, elements.folderRubricaPanel);
    _initToggle(elements.folderImagesToggle, elements.folderImagesPanel);

    // Class chat: knowledge file upload
    if (elements.knowledgeFileInput) {
        elements.knowledgeFileInput.addEventListener('change', async (e) => {
            if (!state.currentClass || !e.target.files.length) return;
            for (const f of e.target.files) {
                await uploadKnowledgeFile(state.currentClass.id, f, elements.knowledgeFiles);
            }
            e.target.value = '';
        });
    }

    // Class chat: rubrica file upload
    if (elements.rubricaFileInput) {
        elements.rubricaFileInput.addEventListener('change', async (e) => {
            if (!state.currentClass || !e.target.files.length) return;
            for (const f of e.target.files) {
                await uploadRubricaFile(state.currentClass.id, f, elements.rubricaFiles);
            }
            e.target.value = '';
        });
    }

    // Class chat: context image upload
    if (elements.contextImageFileInput) {
        elements.contextImageFileInput.addEventListener('change', async (e) => {
            if (!state.currentClass || !e.target.files.length) return;
            for (const f of e.target.files) {
                await uploadContextImage(state.currentClass.id, f, elements.contextImageFiles);
            }
            e.target.value = '';
        });
    }

    // Class chat: save rubrica text
    if (elements.saveRubricaBtn) {
        elements.saveRubricaBtn.addEventListener('click', async () => {
            if (!state.currentClass) return;
            const text = elements.rubricaText.value.trim();
            if (!text) { showToast('warning', 'Vacio', 'Escribe algo en la rubrica'); return; }
            await saveRubricaText(state.currentClass.id, text, elements.rubricaFiles);
            elements.rubricaText.value = '';
        });
    }

    // Folder chat: knowledge file upload
    if (elements.folderKnowledgeFileInput) {
        elements.folderKnowledgeFileInput.addEventListener('change', async (e) => {
            if (!state.currentFolder || !e.target.files.length) return;
            for (const f of e.target.files) {
                await uploadKnowledgeFile(state.currentFolder.path, f, elements.folderKnowledgeFiles);
            }
            e.target.value = '';
        });
    }

    // Folder chat: rubrica file upload
    if (elements.folderRubricaFileInput) {
        elements.folderRubricaFileInput.addEventListener('change', async (e) => {
            if (!state.currentFolder || !e.target.files.length) return;
            for (const f of e.target.files) {
                await uploadRubricaFile(state.currentFolder.path, f, elements.folderRubricaFiles);
            }
            e.target.value = '';
        });
    }

    // Folder chat: context image upload
    if (elements.folderContextImageFileInput) {
        elements.folderContextImageFileInput.addEventListener('change', async (e) => {
            if (!state.currentFolder || !e.target.files.length) return;
            for (const f of e.target.files) {
                await uploadContextImage(state.currentFolder.path, f, elements.folderContextImageFiles);
            }
            e.target.value = '';
        });
    }

    // Folder chat: save rubrica text
    if (elements.folderSaveRubricaBtn) {
        elements.folderSaveRubricaBtn.addEventListener('click', async () => {
            if (!state.currentFolder) return;
            const text = elements.folderRubricaText.value.trim();
            if (!text) { showToast('warning', 'Vacio', 'Escribe algo en la rubrica'); return; }
            await saveRubricaText(state.currentFolder.path, text, elements.folderRubricaFiles);
            elements.folderRubricaText.value = '';
        });
    }

    // Drop zones for class chat panels
    _initDropZone(elements.knowledgePanel, elements.knowledgeFileInput);
    _initDropZone(elements.rubricaPanel, elements.rubricaFileInput);
    _initDropZone(elements.imagesPanel, elements.contextImageFileInput);

    // Drop zones for folder chat panels
    _initDropZone(elements.folderKnowledgePanel, elements.folderKnowledgeFileInput);
    _initDropZone(elements.folderRubricaPanel, elements.folderRubricaFileInput);
    _initDropZone(elements.folderImagesPanel, elements.folderContextImageFileInput);
}

function _initToggle(toggleBtn, panelEl) {
    if (!toggleBtn || !panelEl) return;
    toggleBtn.addEventListener('click', () => {
        panelEl.classList.toggle('hidden');
        toggleBtn.classList.toggle('open');
    });
}

function _initDropZone(panelBody, fileInput) {
    if (!panelBody || !fileInput) return;
    ['dragenter', 'dragover'].forEach(evt => {
        panelBody.addEventListener(evt, (e) => {
            e.preventDefault();
            e.stopPropagation();
            panelBody.classList.add('drop-zone-active');
        });
    });
    panelBody.addEventListener('dragleave', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!panelBody.contains(e.relatedTarget)) {
            panelBody.classList.remove('drop-zone-active');
        }
    });
    panelBody.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        panelBody.classList.remove('drop-zone-active');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            const dt = new DataTransfer();
            for (let i = 0; i < files.length; i++) dt.items.add(files[i]);
            fileInput.files = dt.files;
            fileInput.dispatchEvent(new Event('change'));
        }
    });
}

async function uploadKnowledgeFile(classId, file, containerEl) {
    const formData = new FormData();
    formData.append('file', file);
    try {
        const res = await fetch(`/api/chat/${classId}/knowledge`, { method: 'POST', body: formData });
        const data = await res.json();
        if (data.success) {
            showToast('success', 'Archivo subido', data.filename);
            await loadKnowledgeFiles(classId, containerEl);
        } else {
            showToast('error', 'Error', data.error || 'No se pudo subir');
        }
    } catch (err) {
        showToast('error', 'Error', 'Error de conexion');
    }
}

async function uploadRubricaFile(classId, file, containerEl) {
    const formData = new FormData();
    formData.append('file', file);
    try {
        const res = await fetch(`/api/chat/${classId}/rubrica`, { method: 'POST', body: formData });
        const data = await res.json();
        if (data.success) {
            showToast('success', 'Rubrica subida', data.filename);
            await loadRubricaFiles(classId, containerEl);
        } else {
            showToast('error', 'Error', data.error || 'No se pudo subir');
        }
    } catch (err) {
        showToast('error', 'Error', 'Error de conexion');
    }
}

async function saveRubricaText(classId, text, containerEl) {
    try {
        const res = await fetch(`/api/chat/${classId}/rubrica`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        const data = await res.json();
        if (data.success) {
            showToast('success', 'Rubrica guardada', data.filename);
            await loadRubricaFiles(classId, containerEl);
        } else {
            showToast('error', 'Error', data.error || 'No se pudo guardar');
        }
    } catch (err) {
        showToast('error', 'Error', 'Error de conexion');
    }
}

async function uploadContextImage(classId, file, containerEl) {
    const formData = new FormData();
    formData.append('file', file);
    try {
        const res = await fetch(`/api/chat/${classId}/image`, { method: 'POST', body: formData });
        const data = await res.json();
        if (data.success) {
            showToast('success', 'Imagen subida', data.filename);
            await loadContextImages(classId, containerEl);
        } else {
            showToast('error', 'Error', data.error || 'No se pudo subir');
        }
    } catch (err) {
        showToast('error', 'Error', 'Error de conexion');
    }
}

async function loadContextImages(classId, containerEl) {
    const container = containerEl || elements.contextImageFiles;
    if (!container) return;
    try {
        const res = await fetch(`/api/chat/${classId}/images`);
        const data = await res.json();
        renderFileList(data.files || [], container, classId, 'image');
    } catch (_) {}
}

async function loadKnowledgeFiles(classId, containerEl) {
    const container = containerEl || elements.knowledgeFiles;
    if (!container) return;
    try {
        const res = await fetch(`/api/chat/${classId}/knowledge`);
        const data = await res.json();
        renderFileList(data.files || [], container, classId, 'knowledge');
    } catch (_) {}
}

async function loadRubricaFiles(classId, containerEl) {
    const container = containerEl || elements.rubricaFiles;
    if (!container) return;
    try {
        const res = await fetch(`/api/chat/${classId}/rubricas`);
        const data = await res.json();
        renderFileList(data.files || [], container, classId, 'rubrica');
    } catch (_) {}
}

function renderFileList(files, container, classId, type) {
    if (files.length === 0) {
        container.innerHTML = '';
        return;
    }
    const itemClass = type === 'knowledge' ? 'knowledge-file-item'
                    : type === 'rubrica' ? 'rubrica-file-item'
                    : 'context-image-file-item';
    container.innerHTML = files.map(f => `
        <div class="${itemClass}">
            <span class="file-name">${escapeHtml(f.name)}</span>
            <button class="btn-delete-file" data-name="${escapeHtml(f.name)}" title="Eliminar">x</button>
        </div>`).join('');

    container.querySelectorAll('.btn-delete-file').forEach(btn => {
        btn.addEventListener('click', async () => {
            const filename = btn.dataset.name;
            let endpoint;
            if (type === 'knowledge') {
                endpoint = `/api/chat/${classId}/knowledge/${encodeURIComponent(filename)}`;
            } else if (type === 'rubrica') {
                endpoint = `/api/chat/${classId}/rubrica/${encodeURIComponent(filename)}`;
            } else {
                endpoint = `/api/chat/${classId}/image/${encodeURIComponent(filename)}`;
            }
            try {
                const res = await fetch(endpoint, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) {
                    if (type === 'knowledge') await loadKnowledgeFiles(classId, container);
                    else if (type === 'rubrica') await loadRubricaFiles(classId, container);
                    else await loadContextImages(classId, container);
                    showToast('success', 'Eliminado', filename);
                }
            } catch (_) {
                showToast('error', 'Error', 'No se pudo eliminar');
            }
        });
    });
}

// ============================================
// Toast Notifications
// ============================================

function showToast(type, title, message) {
    const icons = {
        success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <div class="toast-icon">${icons[type]}</div>
        <div class="toast-content">
            <div class="toast-title">${escapeHtml(title)}</div>
            <div class="toast-message">${escapeHtml(message)}</div>
        </div>
        <button class="toast-close">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
        </button>
    `;

    elements.toastContainer.appendChild(toast);

    // Cerrar toast
    const closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', () => toast.remove());

    // Auto-cerrar después de 5 segundos
    setTimeout(() => {
        if (toast.parentNode) {
            toast.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(() => toast.remove(), 300);
        }
    }, 5000);
}

// ============================================
// Utilidades
// ============================================

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function parseMarkdown(text) {
    if (!text) return '';

    // Eliminar bloque YAML frontmatter (---...---)
    text = text.replace(/^---\n[\s\S]*?\n---\n?/, '');

    // Extraer bloques de código (Mermaid y otros) antes de procesar líneas
    const codeBlocks = [];
    text = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
        const idx = codeBlocks.length;
        if (lang === 'mermaid') {
            codeBlocks.push(`<div class="mermaid">${code.trim()}</div>`);
        } else {
            codeBlocks.push(`<pre><code>${code.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</code></pre>`);
        }
        return `\x00CODEBLOCK_${idx}\x00`;
    });

    // Extraer <figure> HTML antes de procesar — resolver data-src a <img> reales
    const figureBlocks = [];
    text = text.replace(/<figure[\s\S]*?<\/figure>/g, (match) => {
        const idx = figureBlocks.length;
        // Si tiene data-src, insertar <img> real vinculada a la clase actual
        const srcMatch = match.match(/data-src="([^"]+)"/);
        if (srcMatch && state.currentClass) {
            const imgPath = srcMatch[1];
            const imgUrl = `/api/classes/${encodeURIComponent(state.currentClass.id).replace(/%2F/g, '/')}/${imgPath}`;
            const captionMatch = match.match(/<figcaption>([\s\S]*?)<\/figcaption>/);
            const caption = captionMatch ? captionMatch[1] : '';
            figureBlocks.push(
                `<figure class="slide-figure">` +
                `<img src="${imgUrl}" alt="${caption.replace(/"/g, '&quot;')}" loading="lazy">` +
                `<figcaption>${caption}</figcaption></figure>`
            );
        } else {
            figureBlocks.push(match);
        }
        return `\x00FIGURE_${idx}\x00`;
    });

    // Extraer tablas markdown antes de procesar líneas
    const tableBlocks = [];
    const tableRe = /(?:^|\n)(\|.+\|\n\|[-| :]+\|\n(?:\|.+\|\n?)*)/g;
    text = text.replace(tableRe, (match) => {
        const idx = tableBlocks.length;
        const rows = match.trim().split('\n');
        if (rows.length < 2) { tableBlocks.push(match); return `\x00TABLE_${idx}\x00`; }
        const headers = rows[0].split('|').filter(c => c.trim() !== '').map(c => `<th>${processInline(c.trim())}</th>`).join('');
        let tbody = '';
        for (let r = 2; r < rows.length; r++) {
            const cells = rows[r].split('|').filter(c => c.trim() !== '').map(c => `<td>${processInline(c.trim())}</td>`).join('');
            tbody += `<tr>${cells}</tr>`;
        }
        tableBlocks.push(`<table class="dense-table"><thead><tr>${headers}</tr></thead><tbody>${tbody}</tbody></table>`);
        return `\x00TABLE_${idx}\x00`;
    });

    // Procesar línea por línea para mejor manejo de listas
    const lines = text.split('\n');
    let html = '';
    let inList = false;
    let listTag = null; // 'ul' o 'ol'
    let inParagraph = false;

    for (let i = 0; i < lines.length; i++) {
        let line = lines[i];

        // Placeholders
        const placeholderMatch = line.trim().match(/^\x00(CODEBLOCK|FIGURE|TABLE)_(\d+)\x00$/);
        if (placeholderMatch) {
            if (inList) { html += `</${listTag}>`; inList = false; listTag = null; }
            if (inParagraph) { html += '</p>'; inParagraph = false; }
            const [, type, idx] = placeholderMatch;
            if (type === 'CODEBLOCK') html += codeBlocks[parseInt(idx)];
            else if (type === 'FIGURE') html += figureBlocks[parseInt(idx)];
            else if (type === 'TABLE') html += tableBlocks[parseInt(idx)];
            continue;
        }

        // Línea separadora ---
        if (line.trim() === '---') {
            if (inList) { html += `</${listTag}>`; inList = false; listTag = null; }
            if (inParagraph) { html += '</p>'; inParagraph = false; }
            html += '<hr>';
            continue;
        }

        // Headers
        if (line.match(/^### /)) {
            if (inList) { html += `</${listTag}>`; inList = false; listTag = null; }
            if (inParagraph) { html += '</p>'; inParagraph = false; }
            html += '<h3>' + processInline(line.substring(4)) + '</h3>';
            continue;
        }
        if (line.match(/^## /)) {
            if (inList) { html += `</${listTag}>`; inList = false; listTag = null; }
            if (inParagraph) { html += '</p>'; inParagraph = false; }
            html += '<h2>' + processInline(line.substring(3)) + '</h2>';
            continue;
        }
        if (line.match(/^# /)) {
            if (inList) { html += `</${listTag}>`; inList = false; listTag = null; }
            if (inParagraph) { html += '</p>'; inParagraph = false; }
            html += '<h1>' + processInline(line.substring(2)) + '</h1>';
            continue;
        }

        // Listas no ordenadas
        const ulMatch = line.match(/^\s*[-*]\s+(.*)/);
        if (ulMatch) {
            if (inParagraph) { html += '</p>'; inParagraph = false; }
            if (inList && listTag !== 'ul') { html += `</${listTag}>`; inList = false; }
            if (!inList) { html += '<ul>'; inList = true; listTag = 'ul'; }
            html += '<li>' + processInline(ulMatch[1]) + '</li>';
            continue;
        }

        // Listas ordenadas
        const olMatch = line.match(/^\s*\d+\.\s+(.*)/);
        if (olMatch) {
            if (inParagraph) { html += '</p>'; inParagraph = false; }
            if (inList && listTag !== 'ol') { html += `</${listTag}>`; inList = false; }
            if (!inList) { html += '<ol>'; inList = true; listTag = 'ol'; }
            html += '<li>' + processInline(olMatch[1]) + '</li>';
            continue;
        }

        // Cerrar lista si ya no estamos en una
        if (inList) { html += `</${listTag}>`; inList = false; listTag = null; }

        // Línea vacía = separador de párrafo
        if (line.trim() === '') {
            if (inParagraph) { html += '</p>'; inParagraph = false; }
            continue;
        }

        // Texto normal
        if (!inParagraph) {
            html += '<p>';
            inParagraph = true;
        } else {
            html += '<br>';
        }
        html += processInline(line);
    }

    // Cerrar etiquetas abiertas
    if (inList) html += `</${listTag}>`;
    if (inParagraph) html += '</p>';

    return html;
}

function processInline(text) {
    // Escapar HTML primero para prevenir inyección
    text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code>$1</code>');
}

function renderMermaidBlocks(container) {
    if (typeof mermaid === 'undefined') return;
    mermaid.initialize({ startOnLoad: false, theme: 'dark', themeVariables: {
        primaryColor: '#6366f1', primaryTextColor: '#f1f5f9',
        primaryBorderColor: '#818cf8', lineColor: '#94a3b8',
        secondaryColor: '#1a1e27', tertiaryColor: '#252a36',
        background: '#1d212b', mainBkg: '#1d212b', nodeBorder: '#818cf8',
    }});
    const blocks = container.querySelectorAll('.mermaid');
    blocks.forEach((block, i) => {
        const id = `mermaid-${Date.now()}-${i}`;
        try {
            mermaid.render(id, block.textContent.trim()).then(({ svg }) => {
                block.innerHTML = svg;
            }).catch(() => {
                block.innerHTML = `<pre class="mermaid-fallback">${block.textContent}</pre>`;
            });
        } catch {
            block.innerHTML = `<pre class="mermaid-fallback">${block.textContent}</pre>`;
        }
    });
}

// ============================================
// Visor de Logs
// ============================================

const logsState = {
    allLogs: [],
    lastServerTime: 0,
    interval: null,
    period: 3600   // segundos; 0 = todo
};

function initLogs() {
    document.querySelectorAll('.log-period-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.log-period-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            logsState.period = parseInt(btn.dataset.period, 10);
            renderLogs();
        });
    });

    elements.logTimeStart.addEventListener('change', renderLogs);
    elements.logTimeEnd.addEventListener('change', renderLogs);

    elements.clearLogsBtn.addEventListener('click', () => {
        logsState.allLogs = [];
        logsState.lastServerTime = Date.now() / 1000;
        renderLogs();
    });

    elements.copyLogsBtn.addEventListener('click', () => {
        const filtered = getFilteredLogs();
        const text = filtered.map(e => {
            const d = new Date(e.ts * 1000);
            const t = d.toTimeString().slice(0, 8);
            return `[${t}][${e.lvl}][${e.src}] ${e.msg}`;
        }).join('\n');
        navigator.clipboard.writeText(text).then(() => {
            showToast('Logs copiados al portapapeles', 'success');
        }).catch(() => {
            showToast('Error al copiar logs', 'error');
        });
    });
}

function startLogsPolling() {
    fetchLogs();
    logsState.interval = setInterval(fetchLogs, 3000);
}

function stopLogsPolling() {
    if (logsState.interval) {
        clearInterval(logsState.interval);
        logsState.interval = null;
    }
}

async function fetchLogs() {
    try {
        const response = await fetch(`/api/logs?since=${logsState.lastServerTime}`);
        const data = await response.json();
        if (data.logs && data.logs.length > 0) {
            logsState.allLogs.push(...data.logs);
            if (logsState.allLogs.length > 2000) {
                logsState.allLogs = logsState.allLogs.slice(-2000);
            }
        }
        if (data.server_time) {
            logsState.lastServerTime = data.server_time;
        }
        renderLogs();
    } catch (_) {
        // servidor ocupado, reintentar en próximo ciclo
    }
}

function getFilteredLogs() {
    const now = Date.now() / 1000;
    const periodCutoff = logsState.period === 0 ? 0 : now - logsState.period;
    const startVal = elements.logTimeStart.value;
    const endVal = elements.logTimeEnd.value;
    return logsState.allLogs.filter(e => {
        if (e.ts < periodCutoff) return false;
        const d = new Date(e.ts * 1000);
        const t = d.toTimeString().slice(0, 8);
        if (startVal && t < startVal) return false;
        if (endVal && t > endVal) return false;
        return true;
    });
}

function renderLogs() {
    const container = elements.logsContent;
    const filtered = getFilteredLogs();

    elements.logsCount.textContent = `${filtered.length} entradas`;

    if (filtered.length === 0) {
        container.innerHTML = '<div class="logs-empty">Sin logs en este período</div>';
        return;
    }

    const wasAtBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 20;

    container.innerHTML = filtered.map(e => {
        const d = new Date(e.ts * 1000);
        const t = d.toTimeString().slice(0, 8);
        const cls = e.lvl === 'E' || e.lvl === 'C' ? 'log-error'
                  : e.lvl === 'W' ? 'log-warning'
                  : 'log-info';
        return `<div class="log-line ${cls}">[${t}][${e.lvl}][${escapeHtml(e.src)}] ${escapeHtml(e.msg)}</div>`;
    }).join('');

    if (wasAtBottom) {
        container.scrollTop = container.scrollHeight;
    }
}
