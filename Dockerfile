FROM python:3.13-slim

WORKDIR /app

# Instalar FFmpeg (obrigatório para converter áudio e juntar vídeo/áudio no yt-dlp)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Instalar dependências
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código-fonte
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Expor porta
EXPOSE 8000

# Executar a aplicação
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
