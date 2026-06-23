import os
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from rembg import remove, new_session
import uuid
import time
from PIL import Image
import io
from pathlib import Path
import gc
import logging
from contextlib import asynccontextmanager

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache de modelos (persiste entre requisições)
sessions_cache = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa modelos na startup para evitar cold start"""
    logger.info("🚀 Iniciando RemoveBG API...")
    
    # Pré-carregar modelos principais (opcional, acelera primeira requisição)
    try:
        logger.info("Pré-carregando modelo u2net...")
        sessions_cache["u2net"] = new_session("u2net")
        logger.info("✅ u2net carregado")
    except Exception as e:
        logger.warning(f"Não foi possível pré-carregar u2net: {e}")
    
    logger.info("✅ API pronta!")
    yield
    
    # Cleanup na shutdown
    logger.info("Limpando cache de modelos...")
    sessions_cache.clear()
    gc.collect()

app = FastAPI(title="RemoveBG API Pro", version="3.0.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurações
UPLOAD_DIR = Path("/app/uploads")
RESULT_DIR = Path("/app/results")
PORT = int(os.getenv("PORT", 5000))
MAX_IMAGE_DIMENSION = int(os.getenv("MAX_IMAGE_DIMENSION", 2048))
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 10485760))
OMP_NUM_THREADS = int(os.getenv("OMP_NUM_THREADS", 4))

# Criar diretórios
UPLOAD_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

# Configurar threads
os.environ["OMP_NUM_THREADS"] = str(OMP_NUM_THREADS)

def get_session(model_name: str):
    """Gerencia cache de sessões com limite de memória"""
    
    # Se tiver mais de 3 modelos em cache, limpar os não usados
    if len(sessions_cache) > 3:
        # Manter apenas u2net (padrão) e o modelo atual
        to_keep = {"u2net", model_name}
        to_remove = [k for k in sessions_cache if k not in to_keep]
        for k in to_remove:
            del sessions_cache[k]
        gc.collect()
        logger.info(f"Cache limpo: {len(to_remove)} modelos removidos")
    
    if model_name not in sessions_cache:
        logger.info(f"🔄 Carregando modelo: {model_name}")
        try:
            sessions_cache[model_name] = new_session(model_name)
            logger.info(f"✅ Modelo {model_name} carregado")
        except Exception as e:
            logger.error(f"❌ Erro ao carregar {model_name}: {e}")
            logger.info("Usando fallback: u2net")
            if "u2net" not in sessions_cache:
                sessions_cache["u2net"] = new_session("u2net")
            return sessions_cache["u2net"]
    
    return sessions_cache[model_name]

@app.get("/")
async def root():
    return {
        "service": "RemoveBG API Pro",
        "version": "3.0.0",
        "status": "running",
        "resources": {
            "max_memory": "4GB",
            "cpus": "4",
            "max_image_dimension": MAX_IMAGE_DIMENSION,
            "max_upload_size_mb": MAX_UPLOAD_SIZE / (1024 * 1024)
        }
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "memory_models_loaded": len(sessions_cache),
        "models": list(sessions_cache.keys())
    }

@app.get("/models")
async def models():
    """Lista modelos com informações de qualidade"""
    return {
        "models": [
            {
                "name": "isnet-general-use",
                "quality": "Excelente",
                "speed": "Lento",
                "memory": "~2GB",
                "best_for": "Uso geral profissional"
            },
            {
                "name": "u2net",
                "quality": "Muito Boa",
                "speed": "Médio",
                "memory": "~1GB",
                "best_for": "Equilíbrio qualidade/velocidade"
            },
            {
                "name": "u2net_human_seg",
                "quality": "Excelente",
                "speed": "Médio",
                "memory": "~1.2GB",
                "best_for": "Fotos de pessoas"
            },
            {
                "name": "u2netp",
                "quality": "Boa",
                "speed": "Rápido",
                "memory": "~600MB",
                "best_for": "Alto volume/tempo real"
            },
            {
                "name": "u2net_cloth_seg",
                "quality": "Muito Boa",
                "speed": "Médio",
                "memory": "~1GB",
                "best_for": "Roupas e moda"
            }
        ],
        "default": "u2net",
        "cached_models": list(sessions_cache.keys())
    }

@app.post("/remove-bg/")
async def remove_bg(
    file: UploadFile = File(...),
    model: str = Form("u2net"),
    alpha_matting: bool = Form(True),
    alpha_matting_foreground_threshold: int = Form(240),
    alpha_matting_background_threshold: int = Form(10),
    alpha_matting_erode_size: int = Form(10),
    post_process_mask: bool = Form(False)
):
    """
    Remove background com parâmetros otimizados
    
    Parâmetros:
    - model: Modelo de IA (padrão: u2net)
    - alpha_matting: Bordas suaves (recomendado)
    - post_process_mask: Pós-processamento adicional
    """
    
    start_time = time.time()
    logger.info(f"📥 Nova requisição - Modelo: {model}")
    
    # Validar arquivo
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Arquivo deve ser uma imagem")
    
    # Ler arquivo
    content = await file.read()
    
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400, 
            detail=f"Arquivo muito grande. Máximo: {MAX_UPLOAD_SIZE/1024/1024:.0f}MB"
        )
    
    try:
        # Abrir e otimizar imagem
        logger.info("🖼️ Processando imagem...")
        img = Image.open(io.BytesIO(content))
        original_size = img.size
        
        # Converter para RGB
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        
        # Redimensionar se necessário
        if max(img.size) > MAX_IMAGE_DIMENSION:
            ratio = MAX_IMAGE_DIMENSION / max(img.size)
            new_size = tuple(int(dim * ratio) for dim in img.size)
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            logger.info(f"Imagem redimensionada: {original_size} -> {img.size}")
        
        # Comprimir para processamento
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG', optimize=True)
        content = img_buffer.getvalue()
        
        # Liberar imagem da memória
        del img
        gc.collect()
        
        # Carregar modelo
        session = get_session(model)
        
        # Configurar remoção
        kwargs = {
            'session': session,
            'alpha_matting': alpha_matting,
        }
        
        if alpha_matting:
            kwargs.update({
                'alpha_matting_foreground_threshold': alpha_matting_foreground_threshold,
                'alpha_matting_background_threshold': alpha_matting_background_threshold,
                'alpha_matting_erode_size': alpha_matting_erode_size,
            })
        
        if post_process_mask:
            kwargs['post_process_mask'] = True
        
        # Remover background
        logger.info("🎯 Removendo background...")
        output_data = remove(content, **kwargs)
        
        # Limpar dados de entrada
        del content
        gc.collect()
        
        # Salvar resultado
        output_filename = f"{uuid.uuid4()}.png"
        output_path = RESULT_DIR / output_filename
        
        with open(output_path, 'wb') as f:
            f.write(output_data)
        
        # Calcular tempo
        elapsed = time.time() - start_time
        logger.info(f"✅ Concluído em {elapsed:.1f}s")
        
        # Headers informativos
        headers = {
            'X-Model-Used': model,
            'X-Processing-Time': f"{elapsed:.1f}s",
            'X-Alpha-Matting': str(alpha_matting),
            'X-Image-Size': str(original_size)
        }
        
        return FileResponse(
            output_path,
            media_type="image/png",
            filename=f"no_bg_{file.filename.rsplit('.', 1)[0]}.png",
            headers=headers
        )
    
    except Exception as e:
        logger.error(f"❌ Erro: {e}")
        gc.collect()  # Limpar memória
        raise HTTPException(status_code=500, detail=f"Erro: {str(e)}")
    
    finally:
        gc.collect()  # Garantir limpeza

@app.get("/stats")
async def stats():
    """Estatísticas de uso"""
    import psutil
    process = psutil.Process()
    memory_info = process.memory_info()
    
    return {
        "memory_used_mb": memory_info.rss / (1024 * 1024),
        "memory_percent": process.memory_percent(),
        "models_cached": len(sessions_cache),
        "models": list(sessions_cache.keys()),
        "cpu_percent": process.cpu_percent()
    }

if __name__ == "__main__":
    import uvicorn
    logger.info(f"🚀 Iniciando servidor na porta {PORT}")
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=PORT,
        workers=1,  # Único worker para economizar RAM
        limit_concurrency=10,  # Máximo 10 requisições simultâneas
        timeout_keep_alive=30
    )
