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
    classes: [],
    selectedFile: null,
    isProcessing: false,
    chatHistory: []
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

    // Upload
    uploadArea: document.getElementById('uploadArea'),
    fileInput: document.getElementById('fileInput'),
    fileSelected: document.getElementById('fileSelected'),
    fileName: document.getElementById('fileName'),
    fileSize: document.getElementById('fileSize'),
    removeFile: document.getElementById('removeFile'),
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

    // Chat
    chatMessages: document.getElementById('chatMessages'),
    chatInput: document.getElementById('chatInput'),
    sendChatBtn: document.getElementById('sendChatBtn'),
    clearChatBtn: document.getElementById('clearChatBtn'),

    // Modal
    confirmModal: document.getElementById('confirmModal'),
    modalTitle: document.getElementById('modalTitle'),
    modalMessage: document.getElementById('modalMessage'),
    modalCancel: document.getElementById('modalCancel'),
    modalConfirm: document.getElementById('modalConfirm'),

    // Toast
    toastContainer: document.getElementById('toastContainer')
};

// ============================================
// Inicialización
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initUpload();
    initDetail();
    initChat();
    initModal();
    checkSystemStatus();
    loadClasses();
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
        } else {
            elements.gpuStatus.className = 'status-dot warning';
            elements.gpuText.textContent = 'GPU no disponible (CPU)';
        }

        // Gemini Status
        if (data.gemini_configured) {
            elements.geminiStatus.className = 'status-dot success';
            elements.geminiText.textContent = 'Gemini conectado';
        } else {
            elements.geminiStatus.className = 'status-dot error';
            elements.geminiText.textContent = 'Gemini no configurado';
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
// Upload de Video
// ============================================

function initUpload() {
    // Click en area de upload
    elements.uploadArea.addEventListener('click', () => {
        elements.fileInput.click();
    });

    // Cambio de archivo
    elements.fileInput.addEventListener('change', (e) => {
        handleFileSelect(e.target.files[0]);
    });

    // Drag and drop
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
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('video/')) {
            handleFileSelect(file);
        } else {
            showToast('error', 'Archivo inválido', 'Por favor selecciona un archivo de video');
        }
    });

    // Quitar archivo
    elements.removeFile.addEventListener('click', (e) => {
        e.stopPropagation();
        clearFileSelection();
    });

    // Procesar
    elements.processBtn.addEventListener('click', processVideo);
}

function handleFileSelect(file) {
    if (!file) return;

    state.selectedFile = file;

    // Mostrar información del archivo
    elements.fileName.textContent = file.name;
    elements.fileSize.textContent = formatFileSize(file.size);

    elements.uploadArea.style.display = 'none';
    elements.fileSelected.style.display = 'flex';
    elements.processBtn.disabled = false;
}

function clearFileSelection() {
    state.selectedFile = null;
    elements.fileInput.value = '';

    elements.uploadArea.style.display = 'block';
    elements.fileSelected.style.display = 'none';
    elements.processBtn.disabled = true;
}

async function processVideo() {
    if (!state.selectedFile || state.isProcessing) return;

    state.isProcessing = true;
    elements.processBtn.disabled = true;

    // Mostrar progreso
    elements.progressContainer.style.display = 'block';
    updateProgress(0, 'Subiendo video...');

    const formData = new FormData();
    formData.append('video', state.selectedFile);
    formData.append('model', elements.modelSelect.value);

    try {
        // Simular pasos de progreso
        const progressSteps = [
            { percent: 10, text: 'Subiendo video...' },
            { percent: 25, text: 'Extrayendo audio...' },
            { percent: 50, text: 'Transcribiendo con Whisper...' },
            { percent: 75, text: 'Generando nombre y resumen con Gemini...' },
            { percent: 90, text: 'Guardando archivos...' }
        ];

        let stepIndex = 0;
        const progressInterval = setInterval(() => {
            if (stepIndex < progressSteps.length) {
                updateProgress(progressSteps[stepIndex].percent, progressSteps[stepIndex].text);
                stepIndex++;
            }
        }, 3000);

        const response = await fetch('/api/process', {
            method: 'POST',
            body: formData
        });

        clearInterval(progressInterval);

        const data = await response.json();

        if (response.ok && data.success) {
            updateProgress(100, '¡Procesamiento completado!');

            setTimeout(() => {
                showToast('success', 'Video procesado', `Clase guardada: ${data.class.name}`);
                clearFileSelection();
                elements.progressContainer.style.display = 'none';
                updateProgress(0, 'Preparando...');

                // Ir a la clase creada
                loadClasses();
                showClassDetail(data.class.id);
            }, 1000);

        } else {
            throw new Error(data.error || 'Error desconocido');
        }

    } catch (error) {
        console.error('Error processing video:', error);
        showToast('error', 'Error al procesar', error.message);
        elements.progressContainer.style.display = 'none';
    } finally {
        state.isProcessing = false;
        elements.processBtn.disabled = !state.selectedFile;
    }
}

function updateProgress(percent, text) {
    elements.progressFill.style.width = `${percent}%`;
    elements.progressText.textContent = text;
    elements.progressPercent.textContent = `${percent}%`;
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

    elements.classesGrid.innerHTML = state.classes.map(cls => `
        <div class="class-card" data-id="${cls.id}">
            <div class="class-card-header">
                <div class="class-card-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                    </svg>
                </div>
                <div class="class-card-actions">
                    <button class="btn-icon delete" data-id="${cls.id}" title="Eliminar clase">
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
                <span>${cls.created_at_formatted}</span>
            </div>
            <div class="class-card-stats">
                <div class="stat">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                    </svg>
                    <span>${cls.segment_count} segmentos</span>
                </div>
            </div>
        </div>
    `).join('');

    // Event listeners para tarjetas
    document.querySelectorAll('.class-card').forEach(card => {
        card.addEventListener('click', (e) => {
            // Ignorar si se hizo clic en el botón de eliminar
            if (e.target.closest('.btn-icon')) return;
            showClassDetail(card.dataset.id);
        });
    });

    // Event listeners para eliminar
    document.querySelectorAll('.class-card .btn-icon.delete').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            confirmDeleteClass(btn.dataset.id);
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

        // Resetear chat
        resetChat();

        // Iniciar sesión de chat
        await startChatSession(classId);

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
            elements.transcriptionContent.innerHTML = '<p class="text-muted">No hay transcripción disponible</p>';
        }

    } catch (error) {
        console.error('Error loading transcription:', error);
        elements.transcriptionContent.innerHTML = '<p class="text-muted">Error al cargar la transcripción</p>';
    }
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

async function startChatSession(classId) {
    try {
        await fetch(`/api/chat/${classId}/start`, { method: 'POST' });
    } catch (error) {
        console.error('Error starting chat session:', error);
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

function addChatMessage(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${role}`;

    if (role === 'assistant') {
        messageDiv.innerHTML = parseMarkdown(content);
    } else {
        messageDiv.textContent = content;
    }

    elements.chatMessages.appendChild(messageDiv);
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
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

    // Procesar línea por línea para mejor manejo de listas
    const lines = text.split('\n');
    let html = '';
    let inList = false;
    let inParagraph = false;

    for (let i = 0; i < lines.length; i++) {
        let line = lines[i];

        // Headers
        if (line.match(/^### /)) {
            if (inList) { html += '</ul>'; inList = false; }
            if (inParagraph) { html += '</p>'; inParagraph = false; }
            html += '<h3>' + processInline(line.substring(4)) + '</h3>';
            continue;
        }
        if (line.match(/^## /)) {
            if (inList) { html += '</ul>'; inList = false; }
            if (inParagraph) { html += '</p>'; inParagraph = false; }
            html += '<h2>' + processInline(line.substring(3)) + '</h2>';
            continue;
        }
        if (line.match(/^# /)) {
            if (inList) { html += '</ul>'; inList = false; }
            if (inParagraph) { html += '</p>'; inParagraph = false; }
            html += '<h1>' + processInline(line.substring(2)) + '</h1>';
            continue;
        }

        // Listas no ordenadas
        const ulMatch = line.match(/^\s*[-*]\s+(.*)/);
        if (ulMatch) {
            if (inParagraph) { html += '</p>'; inParagraph = false; }
            if (!inList) { html += '<ul>'; inList = true; }
            html += '<li>' + processInline(ulMatch[1]) + '</li>';
            continue;
        }

        // Listas ordenadas
        const olMatch = line.match(/^\s*\d+\.\s+(.*)/);
        if (olMatch) {
            if (inParagraph) { html += '</p>'; inParagraph = false; }
            if (!inList) { html += '<ul>'; inList = true; }
            html += '<li>' + processInline(olMatch[1]) + '</li>';
            continue;
        }

        // Cerrar lista si ya no estamos en una
        if (inList) { html += '</ul>'; inList = false; }

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
    if (inList) html += '</ul>';
    if (inParagraph) html += '</p>';

    return html;
}

function processInline(text) {
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code>$1</code>');
}
