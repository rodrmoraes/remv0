FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

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

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/uploads /app/results

# Mudando para porta 5000
EXPOSE 5000

# Especificando a porta no comando
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000"]
