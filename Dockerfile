FROM python:3.10-slim

# Evita prompts durante instalação
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libglib2.0-0 \
    ffmpeg \
    libgdk-pixbuf2.0-0 \
    libgtk2.0-0 \
    libopenexr-dev \
    && rm -rf /var/lib/apt/lists/*

# Cria diretório da aplicação
WORKDIR /app

# Copia e instala dependências Python primeiro (para cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY . .

# Cria diretórios para upload e resultados
RUN mkdir -p /app/uploads /app/results

# Expõe a porta (ajuste conforme necessidade)
EXPOSE 8000

# Comando para iniciar a aplicação
CMD ["python", "app.py"]
