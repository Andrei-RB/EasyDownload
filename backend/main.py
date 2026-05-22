import os
import asyncio
import tempfile
import uuid
from fastapi import FastAPI, HTTPException, Request, Depends, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl, field_validator
from yt_dlp import YoutubeDL
from dotenv import load_dotenv
import logging

# --- (Opcional) Importações de SaaS (Desabilitadas para Open Source Self-Hosted) ---
# import redis.asyncio as redis
# from fastapi_limiter import FastAPILimiter
# from fastapi_limiter.depends import RateLimiter
# from pyrate_limiter import Rate, Duration, Limiter

load_dotenv()
logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="BaixaVideos - Open Source",
    description="Aplicativo Self-Hosted de download de vídeos ultrarrápido.",
    docs_url=None, 
    redoc_url=None
)

# CORS liberado para funcionamento local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # Removido Strict-Transport-Security (HSTS) pois localhost não possui HTTPS
    return response

# =====================================================================
# SAAS RATE LIMITING (Desativado no modo Self-Hosted para downloads infinitos)
# Se você for colocar este projeto em produção pública, descomente isso:
# =====================================================================
# @app.on_event("startup")
# async def startup():
#     redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
#     redis_conn = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
#     await FastAPILimiter.init(redis_conn)
# 
# async def rate_limit_identifier(request: Request):
#     return request.client.host
# 
# rate = Rate(3, Duration.HOUR)
# limiter = Limiter(rate)
# rate_limit_dependency = [Depends(RateLimiter(limiter, identifier=rate_limit_identifier))]
# =====================================================================

# --- Gestão de Arquivos ---
ready_files = {}

def delete_temp_file(file_path: str):
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass

# --- WebSocket Progress Tracking ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, task_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[task_id] = websocket

    def disconnect(self, task_id: str):
        if task_id in self.active_connections:
            del self.active_connections[task_id]

    async def send_progress(self, task_id: str, message: dict):
        if task_id in self.active_connections:
            try:
                await self.active_connections[task_id].send_json(message)
            except:
                pass

manager = ConnectionManager()

@app.websocket("/ws/progress/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await manager.connect(task_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(task_id)

# --- Rotas REST ---
class DownloadRequest(BaseModel):
    url: HttpUrl
    format_type: str = "video"
    # turnstile_token: str # Desativado para Self-Hosted (Não precisamos de Anti-Bot rodando localmente)

    @field_validator("url")
    @classmethod
    def check_youtube_url(cls, v: HttpUrl):
        valid_domains = ["youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"]
        if v.host not in valid_domains:
            raise ValueError("Apenas links do YouTube são permitidos.")
        return v

    @field_validator("format_type")
    @classmethod
    def check_format(cls, v: str):
        if v not in ["video", "audio"]:
            raise ValueError("Formato inválido.")
        return v

async def process_download(task_id: str, url_str: str, format_type: str):
    temp_dir = tempfile.gettempdir()
    loop = asyncio.get_running_loop()
    
    def progress_hook(d):
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '0%').replace('%', '').strip()
            asyncio.run_coroutine_threadsafe(
                manager.send_progress(task_id, {"status": "downloading", "progress": p}),
                loop
            )
        elif d['status'] == 'finished':
            asyncio.run_coroutine_threadsafe(
                manager.send_progress(task_id, {"status": "processing", "progress": "100"}),
                loop
            )

    ydl_opts = {
        'outtmpl': os.path.join(temp_dir, f'{task_id}_%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'restrictfilenames': True,
        'noplaylist': True,
        'max_filesize': 5 * 1024 * 1024 * 1024,
        'progress_hooks': [progress_hook],
    }

    if format_type == "audio":
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
        })
    else:
        ydl_opts.update({
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
        })

    try:
        def run_dl():
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url_str, download=True)
                return ydl.prepare_filename(info)

        file_path = await asyncio.to_thread(run_dl)
        
        if format_type == "audio":
            file_path = os.path.splitext(file_path)[0] + ".mp3"

        if not os.path.exists(file_path):
            raise Exception("Erro interno.")

        ready_files[task_id] = file_path
        await manager.send_progress(task_id, {"status": "completed", "file_id": task_id})

    except Exception as e:
        logger.error(f"Erro no download {task_id}: {e}")
        await manager.send_progress(task_id, {"status": "error", "message": "Falha no download. O vídeo pode estar protegido."})


# Rota alterada: Dependência do RateLimiter removida para Self-Hosted. (Para SaaS, adicione: dependencies=rate_limit_dependency)
@app.post("/api/start_download")
async def start_download(request: DownloadRequest, background_tasks: BackgroundTasks):
    
    # --- SAAS ANTI-BOT (Desativado) ---
    # if not request.turnstile_token:
    #     raise HTTPException(status_code=403, detail="Validação Anti-Bot falhou.")
        
    task_id = str(uuid.uuid4())
    url_str = str(request.url)
    
    background_tasks.add_task(process_download, task_id, url_str, request.format_type)
    return {"task_id": task_id}


@app.get("/api/file/{file_id}")
async def get_file(file_id: str, background_tasks: BackgroundTasks):
    if file_id not in ready_files:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado ou já expirado.")
        
    file_path = ready_files.pop(file_id)
    filename = os.path.basename(file_path)
    
    background_tasks.add_task(delete_temp_file, file_path)
    
    return FileResponse(
        path=file_path,
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# --- Montar o Frontend ---
# Isso fará o FastAPI servir a página index.html quando acessarem localhost:8000
# Resolvendo o caminho de forma robusta e dinâmica (funciona tanto local quanto no Docker)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

