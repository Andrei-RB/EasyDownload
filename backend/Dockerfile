# Usa uma imagem oficial leve do Python baseada em Debian (slim) para maior segurança e menor superfície de ataque
FROM python:3.14-slim

# Configurações de ambiente seguro para o Python
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Instalação do ffmpeg (necessário para processamento de mídia do yt-dlp) sem pacotes desnecessários
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Criação de usuário sem privilégios de root (Sandboxing essencial)
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --gid 1001 appuser

WORKDIR /app

# Instala dependências
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia a aplicação
COPY main.py .

# Altera o dono da pasta para o appuser
RUN chown -R appuser:appgroup /app

# Troca para o usuário restrito (No-Root)
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
