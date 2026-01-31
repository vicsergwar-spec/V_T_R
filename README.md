# V_T_R - Video Transcriptor y Resumen

Sistema completo de procesamiento de videos de clases académicas. Transcribe videos usando Whisper con GPU local y genera resúmenes inteligentes con Gemini AI.

## Características

- **Transcripción automática** con Whisper usando GPU (CUDA)
- **Resúmenes inteligentes** generados por Gemini AI
- **Chat interactivo** para hacer preguntas sobre el contenido de cada clase
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
4. Si la IA comienza a "alucinar", usar el botón "Limpiar chat"

## Estructura de Archivos Generados

Cada clase procesada se guarda en:
```
clases/
└── Materia_Tema/
    ├── transcripcion.jsonl  # Transcripción con timestamps
    └── resumen.md           # Resumen estructurado
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
- **IA:** Google Gemini API
- **Audio:** FFmpeg + Pydub
- **Frontend:** HTML5, CSS3, JavaScript vanilla

## Licencia

MIT License
