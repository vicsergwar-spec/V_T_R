# V_T_R - Video Transcriptor y Resumen

Sistema completo de procesamiento de videos de clases académicas. Transcribe videos usando Whisper con GPU local y genera resúmenes inteligentes, chats individuales por clase y chat general por carpeta con Google Gemini AI.

## Características

- **Transcripción automática** con faster-Whisper usando GPU (CUDA)
- **Resúmenes inteligentes** generados por Gemini AI
- **Chat por clase** — pregunta sobre el contenido de una clase específica
- **Chat por carpeta** — chat general con el conocimiento de **todas** las clases de una materia a la vez
- **Historial de chat persistente** — los chats se conservan entre sesiones y solo se borran cuando el usuario lo decide
- **Context Caching de Gemini** — la transcripción se sube una vez al caché (dura 1 hora); los mensajes siguientes no reenvían el contenido completo, ahorrando tokens
- **Extracción de slides** — detecta y extrae los fotogramas relevantes del video (requiere Google Vision API)
- **Organización automática** de archivos por materia/carpeta y tema
- **Soporte para múltiples formatos** de video (mp4, mkv, avi, mov, webm, etc.)
- **Lanzadores automáticos** (`run.bat` / `run.sh`) — actualizan el código, instalan dependencias y arrancan el servidor con un doble clic
- **Visor de logs híbrido** — botones de rango rápido (1h, 2h, 4h, 24h, Todo) combinados con selectores manuales de hora inicio/fin y botón de copiar al portapapeles
- **Acceso remoto** — servidor escucha en `0.0.0.0` con túnel seguro vía cloudflared para consultar chats y descargar archivos desde cualquier red
- **PDF con aspect-ratio inteligente** — las imágenes de slides se renderizan con proporciones correctas (`contain`) y centrado horizontal automático
- **Sub-imágenes persistentes** — diagramas, fotos y figuras incrustadas dentro de los slides se extraen, guardan y vinculan automáticamente

---

## Requisitos del Sistema

- **Windows 11** (o Linux/macOS con `run.sh`)
- **Python 3.10+** (recomendado 3.11 o 3.12)
- **GPU NVIDIA** con soporte CUDA (mínimo 6 GB VRAM para modelo `medium`)
- **FFmpeg** instalado en el sistema
- **API Key de Gemini** (Google AI Studio) — obligatoria
- **API Key de OpenAI** (opcional, para usar Whisper en la nube sin GPU)
- **API Key de Google Vision** (opcional, para extracción de slides)
- **cloudflared** (opcional, para acceso remoto fuera de la red local)

---

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
2. Extraer en `C:\ffmpeg`
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
python -m venv .venv

# Activar en Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# Activar en Windows (CMD)
.\.venv\Scripts\activate.bat
```

### 4. Instalar PyTorch con soporte CUDA

**Importante:** Instalar PyTorch **antes** de las demás dependencias.

Para CUDA 12.x:
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

> **Nota:** Si actualizas desde una versión anterior, ejecuta:
> ```bash
> pip install --upgrade google-generativeai
> ```
> Se requiere `google-generativeai >= 0.7.0` para el Context Caching.

### 6. Configurar API Keys

1. Copiar el archivo de ejemplo:
```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

2. Editar `.env` con tus claves:
```
GEMINI_API_KEY=tu_api_key_de_gemini
OPENAI_API_KEY=tu_api_key_de_openai_opcional
GOOGLE_VISION_API_KEY=tu_api_key_de_vision_opcional
SLIDE_EXTRACTION_ENABLED=true
```

#### Obtener API Key de Gemini
1. Ir a https://aistudio.google.com/app/apikey
2. Crear o seleccionar un proyecto
3. Generar una nueva API key
4. Copiar y pegar en `.env`

#### Cambiar el modelo de Gemini
El modelo se configura en `config.py`:
```python
GEMINI_MODEL = "gemini-3-flash-preview"  # Cambia por el ID exacto de Google AI Studio
```

#### Obtener API Key de OpenAI (opcional)
1. Ir a https://platform.openai.com/api-keys
2. Crear una nueva API key
3. Copiar y pegar en `.env`

---

## Uso Rápido (Recomendado)

### Opción A — Lanzador automático (un doble clic)

| Sistema operativo | Archivo a ejecutar |
|---|---|
| Windows | `run.bat` |
| Linux / macOS | `run.sh` |

El lanzador realiza automáticamente:
1. `git pull` — descarga los últimos cambios del repositorio (si hay conexión)
2. Activa el entorno virtual (`.venv/` o `venv/`) si existe
3. `pip install -r requirements.txt` — instala/actualiza dependencias
4. Verifica que el archivo `.env` exista
5. Arranca el servidor Flask

> **Nota:** `git pull` no necesita configuración — git ya conoce la URL del repositorio desde que fue clonado (guardada en `.git/config`). Si no hay conexión, el lanzador continúa con la versión local sin interrumpirse.

### Opción B — Manual

```bash
# Activar entorno virtual
.\.venv\Scripts\activate.bat   # Windows CMD
source .venv/bin/activate       # Linux / macOS

# Iniciar el servidor
python app.py
```

El servidor inicia en **http://localhost:5000** (accesible desde la red local en `http://<IP-de-tu-PC>:5000`).

---

## Uso del Sistema

### Subir y Procesar un Video

1. Abrir http://127.0.0.1:5000 en el navegador
2. Arrastrar un video al área de upload o hacer clic para seleccionar
3. Seleccionar el modelo de Whisper:

   | Modelo | VRAM aprox. | Recomendado para |
   |---|---|---|
   | `small` | ~1–2 GB | GPUs con poca VRAM |
   | `medium` | ~3 GB | Uso general (recomendado) |
   | `large-v3` | ~4–5 GB | Máxima calidad |
   | `openai` | Sin GPU | Sin GPU local |

4. Hacer clic en **"Procesar"**
5. El sistema:
   - Extrae el audio del video con FFmpeg
   - Transcribe con faster-Whisper (GPU)
   - Genera nombre y resumen con Gemini
   - Extrae slides relevantes (si está habilitado)
   - Guarda todos los archivos

### Ver Clases Procesadas

1. Ir a la sección **"Mis Clases"**
2. Las clases se agrupan por carpeta/materia
3. Hacer clic en una tarjeta para ver el detalle (resumen, transcripción, slides)

### Chat por Clase

1. Seleccionar una clase
2. Escribir una pregunta en el chat
3. La IA responde basándose en la transcripción, resumen y slides de esa clase
4. El historial se guarda automáticamente — al volver a abrir la clase los mensajes siguen ahí
5. Para borrar el historial usar el botón **"Limpiar chat"**

### Chat por Carpeta (todas las clases)

1. En la lista de clases, cada carpeta/materia tiene un botón **"Chat"**
2. Al abrirlo, el sistema carga el contenido de **todas las clases** de esa carpeta
3. Puedes preguntar sobre temas que abarcan varias clases y la IA citará de qué clase proviene cada respuesta
4. El historial de este chat también se guarda por separado y persiste entre sesiones
5. Para borrar, usar el botón **"Limpiar chat"** dentro del chat de carpeta

### Visor de Logs del Sistema

La sección **"Logs"** permite monitorear toda la actividad del servidor en tiempo real con un sistema de filtrado híbrido:

1. **Rangos rápidos** — botones predefinidos que filtran por ventana de tiempo relativa:
   - `1h` (última hora, activo por defecto), `2h`, `4h`, `24h`, `Todo` (sin límite)
2. **Selectores manuales** — dos campos de hora (`Inicio` y `Fin`) para definir un rango absoluto preciso (ej: de 14:30 a 15:45). Funcionan en combinación con el rango rápido seleccionado
3. **Copiar Logs** — copia al portapapeles el texto plano de todos los logs visibles (ya filtrados), listo para pegar en un reporte o chat
4. **Limpiar vista** — borra los logs acumulados en memoria del navegador (no afecta al servidor)

Los logs se actualizan automáticamente cada 3 segundos mediante polling. El buffer del servidor almacena hasta 2000 entradas por sesión.

### Acceso Remoto (cloudflared)

El servidor escucha en `0.0.0.0` (todas las interfaces de red), lo que permite:

- **Red local**: acceder desde otro dispositivo en la misma red WiFi usando `http://<IP-de-tu-PC>:5000`
- **Fuera de la red local**: usar un túnel seguro con cloudflared para acceder desde cualquier lugar (ej: desde el trabajo)

#### Configurar acceso remoto con cloudflared

1. **Instalar cloudflared** en la PC donde corre V_T_R:
   - Windows: `winget install Cloudflare.cloudflared`
   - Linux: seguir la guía en https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

2. **Iniciar el túnel** desde la API del sistema:
   ```bash
   # Iniciar túnel (genera una URL pública temporal tipo https://xxx.trycloudflare.com)
   curl -X POST http://localhost:5000/api/tunnel/start

   # Verificar estado
   curl http://localhost:5000/api/tunnel/status

   # Detener túnel
   curl -X POST http://localhost:5000/api/tunnel/stop
   ```

3. **Desde el trabajo o cualquier red externa**, abre la URL generada en el navegador. Tendrás acceso completo a:
   - Consultar chats por clase y por carpeta
   - Descargar slides en PDF y Markdown
   - Ver resúmenes y transcripciones
   - Monitorear logs del servidor

> **Nota de seguridad:** la URL de cloudflared es pública pero aleatoria y temporal. Solo compártela con quien necesites. El túnel se cierra al detenerlo o al apagar el servidor.

> **Nota:** el procesamiento de video (transcripción con Whisper + GPU) solo se ejecuta en la PC local. El acceso remoto está pensado para consulta y descarga, no para subir nuevos videos.

### Renderizado de PDF con Aspect-Ratio

Al descargar los slides en formato PDF, cada imagen se renderiza respetando sus proporciones originales:

- **Aspect-ratio `contain`**: la imagen se escala para caber dentro del ancho disponible de la página sin recortarse ni deformarse
- **Centrado horizontal automático**: si la imagen es más angosta que el ancho de página, se centra visualmente
- **Control de altura máxima**: las imágenes no exceden 110mm de alto; si no caben en la página actual, se insertan en una página nueva
- **Resolución**: se asume 96 DPI para la conversión de píxeles a milímetros

### Sub-imágenes de Slides

Durante la extracción de slides, el sistema detecta automáticamente figuras, diagramas y fotos incrustadas dentro de cada fotograma:

1. **Detección**: usa análisis de contornos y diferencia de color respecto al fondo para identificar regiones visuales relevantes (entre 2% y 85% del área del frame)
2. **Extracción**: cada sub-imagen se recorta y guarda como archivo independiente en `slide_images/slide_NNN_sub_M.jpg`
3. **Descripción con IA**: si Google Vision API está configurada, cada sub-imagen recibe una descripción técnica automática
4. **Persistencia**: las sub-imágenes se guardan permanentemente junto a la clase y se vinculan en el documento generado por IA usando etiquetas `<figure>` con ruta directa
5. **Visualización**: tanto en la interfaz web como en el PDF descargable, las sub-imágenes aparecen integradas en el contexto temático donde corresponden

### Cómo funciona el Context Caching

Al iniciar cualquier sesión de chat (por clase o por carpeta), el contenido se sube al caché de Gemini (dura **1 hora**). Mientras el caché esté activo, cada mensaje solo envía el historial y la pregunta nueva, sin reenviar el contenido completo. Esto reduce el consumo de tokens significativamente.

Si el contenido es muy corto o el modelo no soporta caché, el sistema hace **fallback automático** sin interrumpir el chat. En los logs del servidor verás:
```
Caché de Gemini creado: cachedContents/...
# o en fallback:
Context caching no disponible (...), usando system_instruction estándar
```

---

## Estructura del Proyecto

```
V_T_R/
├── app.py                  # Servidor Flask y rutas de la API
├── config.py               # Configuración global (modelos, paths, API keys)
├── requirements.txt        # Dependencias de Python
├── run.bat                 # Lanzador automático para Windows
├── run.sh                  # Lanzador automático para Linux/macOS
├── .env                    # API keys (no subir al repositorio)
├── .env.example            # Plantilla para crear .env
├── services/
│   ├── audio_extractor.py  # Extracción de audio con FFmpeg
│   ├── file_manager.py     # Lectura/escritura de archivos de clases y carpetas
│   ├── gemini_service.py   # Integración con Gemini API (chat, caché, resúmenes)
│   ├── slide_extractor.py  # Extracción de slides con Google Vision
│   └── transcriber.py      # Transcripción con faster-Whisper
├── static/
│   ├── index.html          # Interfaz web (SPA)
│   ├── css/style.css       # Estilos (tema oscuro)
│   └── js/app.js           # Lógica del frontend
└── clases/                 # Datos generados (creado automáticamente)
    └── Materia_Tema/
        ├── transcripcion.jsonl         # Transcripción con timestamps
        ├── resumen.md                  # Resumen estructurado
        ├── slides.md                      # Slides crudos (Markdown con refs a imágenes)
        ├── slides_document.md             # Documento de slides generado por IA
        ├── slide_images/                  # Fotogramas extraídos + sub-imágenes
        │   ├── slide_001.jpg              # Imagen principal del slide
        │   └── slide_001_sub_1.jpg        # Sub-imagen detectada dentro del slide
        ├── chat_historial.json         # Historial de chat por clase
        ├── gemini_cache.txt            # Nombre del caché de Gemini (por clase)
        ├── folder_chat_historial.json  # Historial del chat de carpeta
        └── folder_gemini_cache.txt     # Caché de Gemini del chat de carpeta
```

### Formatos de archivos generados

**Transcripción (`transcripcion.jsonl`)** — una línea por segmento:
```json
{"timestamp_inicio": "00:00:00.000", "timestamp_fin": "00:00:05.230", "texto": "texto transcrito", "confianza": 0.95}
```

**Resumen (`resumen.md`)**:
```markdown
# Nombre de la clase
## Fecha de procesamiento
## Puntos principales
## Lo más importante para estudiar
## Tareas o pendientes mencionados
```

**Historial de chat (`chat_historial.json` / `folder_chat_historial.json`)**:
```json
[
  {"role": "user",  "content": "¿Qué es una derivada?"},
  {"role": "model", "content": "Según la clase, una derivada es..."}
]
```

---

## API REST

El backend expone los siguientes endpoints:

| Método | Endpoint | Descripción |
|---|---|---|
| `POST` | `/api/upload` | Sube y procesa un video |
| `GET` | `/api/classes` | Lista todas las clases |
| `GET` | `/api/class/<id>` | Detalle de una clase |
| `DELETE` | `/api/class/<id>` | Elimina una clase |
| `POST` | `/api/chat/<id>/start` | Inicia sesión de chat (por clase) |
| `POST` | `/api/chat/<id>/message` | Envía mensaje al chat (por clase) |
| `GET` | `/api/chat/<id>/history` | Obtiene historial (por clase) |
| `POST` | `/api/chat/<id>/clear` | Limpia historial (por clase) |
| `POST` | `/api/folder-chat/<path>/start` | Inicia sesión de chat (por carpeta) |
| `POST` | `/api/folder-chat/<path>/message` | Envía mensaje al chat (por carpeta) |
| `GET` | `/api/folder-chat/<path>/history` | Obtiene historial (por carpeta) |
| `POST` | `/api/folder-chat/<path>/clear` | Limpia historial (por carpeta) |
| `GET` | `/api/logs` | Obtiene logs en memoria (`?since=timestamp`) |
| `POST` | `/api/tunnel/start` | Inicia túnel cloudflared (devuelve URL pública) |
| `POST` | `/api/tunnel/stop` | Detiene el túnel cloudflared activo |
| `GET` | `/api/tunnel/status` | Verifica si el túnel está activo |
| `POST` | `/api/shutdown` | Apaga el equipo (`shutdown /s /f /t 0`) |
| `POST` | `/api/stop` | Detiene el servidor Flask |

---

## Solución de Problemas

### CUDA no disponible
- Verificar que los drivers de NVIDIA están actualizados
- Reinstalar PyTorch con la versión correcta de CUDA
- Reiniciar el sistema después de actualizar drivers

### FFmpeg no encontrado
- Verificar que FFmpeg está en el PATH: `ffmpeg -version`
- Reiniciar la terminal después de agregarlo al PATH

### API Key inválida
- Verificar que el archivo `.env` existe y contiene las keys correctas
- Asegurar que no hay espacios extra alrededor de los valores

### El chat no recuerda la conversación anterior
- Verificar que `chat_historial.json` existe en la carpeta de la clase
- El historial se crea al primer mensaje enviado

### Context caching no funciona
- Verificar versión: `pip show google-generativeai` (requiere >= 0.7.0)
- El caching requiere un mínimo de tokens; transcripciones muy cortas usan fallback automático
- Verificar que el modelo configurado en `config.py` soporta Context Caching en Google AI Studio

### La transcripción es muy lenta
- Usar el modelo `small` en lugar de `medium`
- Cerrar otras aplicaciones que usen la GPU
- Verificar que Whisper está usando CUDA y no CPU:
  ```python
  import torch
  print(torch.cuda.is_available())  # Debe ser True
  ```

### El chat de carpeta no carga contenido
- Verificar que la carpeta contiene clases con transcripciones procesadas
- Las clases sin transcripción se omiten automáticamente
- Revisar los logs del servidor para ver cuántas clases fueron cargadas

### run.bat o run.sh falla al hacer git pull
- El script continúa automáticamente con la versión local — no es un error crítico
- Si hay problemas de permisos en Linux: `chmod +x run.sh`

### cloudflared no encontrado
- Instalar con `winget install Cloudflare.cloudflared` (Windows) o seguir la guía oficial de Cloudflare
- Verificar que el ejecutable está en el PATH: `cloudflared --version`
- El túnel es opcional; el sistema funciona completamente sin él para uso en red local

### El PDF no muestra imágenes de slides
- Verificar que la carpeta `slide_images/` existe dentro de la clase y contiene archivos `.jpg`
- Si se procesó antes de la actualización, regenerar el documento de slides desde la vista de detalle de la clase
- Revisar los logs del servidor para errores de tipo `PDF: no se pudo insertar imagen`

---

## Tecnologías Utilizadas

- **Backend:** Flask 3.0+ (Python)
- **Transcripción:** faster-Whisper (local con CUDA) / OpenAI Whisper API (nube)
- **IA:** Google Gemini API con Context Caching
- **Audio:** FFmpeg + Pydub
- **Slides:** Google Cloud Vision API (opcional)
- **Frontend:** HTML5, CSS3, JavaScript vanilla (SPA, tema oscuro)
- **PDF:** fpdf2 con renderizado aspect-ratio contain y soporte de imágenes incrustadas
- **Túnel remoto:** cloudflared (opcional, para acceso externo seguro)
- **Almacenamiento:** Sistema de archivos (JSONL, Markdown, JSON, TXT, JPG) — sin base de datos

---

## Licencia

MIT License
