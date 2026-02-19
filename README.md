# V_T_R - Video Transcriptor y Resumen

Sistema completo de procesamiento de videos de clases académicas. Transcribe videos usando Whisper con GPU local y genera resúmenes inteligentes con Gemini AI.

## Características

- **Transcripción automática** con Whisper usando GPU (CUDA)
- **Resúmenes inteligentes** generados por Gemini AI
- **Chat interactivo** para hacer preguntas sobre el contenido de cada clase
- **Historial de chat persistente** — los chats se conservan entre sesiones y solo se borran cuando el usuario lo decide
- **Context Caching de Gemini** — la transcripción se sube una vez al caché de Gemini; los mensajes siguientes no reenvían la transcripción completa, ahorrando tokens
- **Organización automática** de archivos por materia y tema
- **Soporte para múltiples formatos** de video (mp4, mkv, avi, mov, etc.)
- **Interfaz web moderna** y fácil de usar

## Requisitos del Sistema

- **Windows 11**
- **Python 3.10+** (recomendado 3.11 o 3.12)
- **GPU NVIDIA** con soporte CUDA (mínimo 6GB VRAM para modelo small)
- **FFmpeg** instalado en el sistema
- **API Key de Gemini** (Google AI Studio)
- **API Key de OpenAI** (opcional, para respaldo de Whisper)

## Instalación Paso a Paso

### 1. Clonar el repositorio

```bash
git clone https://github.com/vicsergwar-spec/V_T_R.git
cd V_T_R
```

### 2. Instalar FFmpeg en Windows

#### Opción A: Usando winget (recomendado)
```powershell
winget install FFmpeg.FFmpeg
```

#### Opción B: Descarga manual
1. Descargar desde https://ffmpeg.org/download.html (Windows builds)
2. Extraer el archivo en `C:\ffmpeg`
3. Agregar `C:\ffmpeg\bin` al PATH del sistema:
   - Buscar "Variables de entorno" en el menú inicio
   - Editar la variable `Path` del sistema
   - Agregar nueva entrada: `C:\ffmpeg\bin`
   - Reiniciar la terminal

Verificar instalación:
```bash
ffmpeg -version
```

### 3. Crear y activar entorno virtual

```bash
# Crear entorno virtual
python -m venv venv

# Activar en Windows (PowerShell)
.\venv\Scripts\Activate.ps1

# Activar en Windows (CMD)
.\venv\Scripts\activate.bat
```

### 4. Instalar PyTorch con soporte CUDA

**Importante:** Instalar PyTorch ANTES de las demás dependencias.

Para CUDA 12.1 (compatible con CUDA 12.5):
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

Para CUDA 11.8:
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

Verificar que CUDA funciona:
```python
import torch
print(f"CUDA disponible: {torch.cuda.is_available()}")
print(f"GPU: {torch.cuda.get_device_name(0)}")
```

### 5. Instalar dependencias de Python

```bash
pip install -r requirements.txt
```

> **Nota:** Si ya tenías el proyecto instalado y estás actualizando, ejecuta:
> ```bash
> pip install --upgrade google-generativeai
> ```
> Se requiere `google-generativeai>=0.7.0` para que funcione el Context Caching.

### 6. Configurar API Keys

1. Copiar el archivo de ejemplo:
```bash
copy .env.example .env
```

2. Editar `.env` con tus API keys:
```
GEMINI_API_KEY=tu_api_key_de_gemini
OPENAI_API_KEY=tu_api_key_de_openai_opcional
```

#### Obtener API Key de Gemini
1. Ir a https://aistudio.google.com/app/apikey
2. Crear o seleccionar un proyecto
3. Generar una nueva API key
4. Copiar y pegar en el archivo `.env`

#### Cambiar el modelo de Gemini
El modelo se configura en `config.py`:
```python
GEMINI_MODEL = "gemini-3-flash-preview"  # Cambia aquí por el ID exacto de Google AI Studio
```

#### Obtener API Key de OpenAI (opcional)
1. Ir a https://platform.openai.com/api-keys
2. Crear una nueva API key
3. Copiar y pegar en el archivo `.env`

### 7. Ejecutar el servidor

```bash
python app.py
```

El servidor iniciará en http://127.0.0.1:5000

## Uso del Sistema

### Subir y Procesar un Video

1. Abrir http://127.0.0.1:5000 en el navegador
2. Arrastrar un video al área de upload o hacer clic para seleccionar
3. Seleccionar el modelo de Whisper (small recomendado para 6GB VRAM)
4. Hacer clic en "Procesar"
5. Esperar mientras el sistema:
   - Extrae el audio del video
   - Transcribe con Whisper
   - Genera nombre y resumen con Gemini
   - Guarda los archivos

### Ver Clases Procesadas

1. Ir a la sección "Mis Clases"
2. Las clases se muestran como tarjetas con el nombre de materia y tema
3. Hacer clic en una tarjeta para ver el detalle

### Chatear con una Clase

1. Seleccionar una clase
2. En la sección de chat, escribir una pregunta
3. La IA responderá basándose en el contenido de la transcripción
4. El historial de chat se guarda automáticamente — al volver a abrir la clase los mensajes siguen ahí
5. Para borrar el historial usar el botón **"Limpiar chat"**

### Cómo funciona el Context Caching

Al iniciar el chat de una clase por primera vez, la transcripción se sube al caché de Gemini (dura 1 hora). Mientras el caché esté activo, cada mensaje solo envía el historial y la pregunta nueva, no la transcripción completa. Esto reduce el consumo de tokens significativamente en clases largas.

Si la transcripción es muy corta o el modelo no soporta caché, el sistema hace fallback automático sin interrumpir el chat. En los logs del servidor verás si el caché está activo:
```
Caché de Gemini creado: cachedContents/...
# o en fallback:
Context caching no disponible (...), usando system_instruction estándar
```

## Estructura de Archivos Generados

Cada clase procesada se guarda en:
```
clases/
└── Materia_Tema/
    ├── transcripcion.jsonl   # Transcripción con timestamps
    ├── resumen.md            # Resumen estructurado
    ├── chat_historial.json   # Historial de chat (se crea al primer mensaje)
    └── gemini_cache.txt      # Nombre del caché de Gemini (se crea si aplica)
```

### Formato de Transcripción (JSONL)
Cada línea contiene:
```json
{"timestamp_inicio": "00:00:00.000", "timestamp_fin": "00:00:05.230", "texto": "texto transcrito", "confianza": 0.95}
```

### Formato de Resumen (Markdown)
```markdown
# Nombre de la clase
## Fecha de procesamiento
## Puntos principales
## Lo más importante para estudiar
## Tareas o pendientes mencionadas
```

### Formato del Historial de Chat (JSON)
```json
[
  {"role": "user",  "content": "¿Qué es una derivada?"},
  {"role": "model", "content": "Según la clase, una derivada es..."}
]
```

## Solución de Problemas

### Error: CUDA no disponible
- Verificar que los drivers de NVIDIA están actualizados
- Reinstalar PyTorch con la versión correcta de CUDA
- Reiniciar el sistema después de actualizar drivers

### Error: FFmpeg no encontrado
- Verificar que FFmpeg está en el PATH
- Reiniciar la terminal después de agregarlo al PATH

### Error: API Key inválida
- Verificar que el archivo `.env` existe y contiene las keys correctas
- Asegurar que no hay espacios extra alrededor de las keys

### El chat no recuerda la conversación anterior
- Verificar que `chat_historial.json` existe en la carpeta de la clase
- Si no existe, el historial se guarda al primer mensaje

### Context caching no funciona
- Verificar que `google-generativeai>=0.7.0` está instalado: `pip show google-generativeai`
- El caching requiere un mínimo de tokens; transcripciones muy cortas usan fallback automático
- Verificar que el modelo seleccionado soporta Context Caching en Google AI Studio

### La transcripción es muy lenta
- Usar el modelo "small" en lugar de "medium"
- Cerrar otras aplicaciones que usen la GPU
- Verificar que Whisper está usando CUDA y no CPU

### Whisper usa CPU en lugar de GPU
Verificar con:
```python
import whisper
model = whisper.load_model("small")
print(model.device)  # Debe mostrar 'cuda:0'
```

## Tecnologías Utilizadas

- **Backend:** Flask (Python)
- **Transcripción:** OpenAI Whisper (local con CUDA)
- **IA:** Google Gemini API (con Context Caching)
- **Audio:** FFmpeg + Pydub
- **Frontend:** HTML5, CSS3, JavaScript vanilla

## Licencia

MIT License

