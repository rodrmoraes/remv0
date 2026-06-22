from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import uuid
import time
from rembg import remove
from PIL import Image
import io
from pathlib import Path

app = FastAPI(title="RemoveBG API", version="1.0.0")

# Configuração CORS
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
MAX_FILE_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 10 * 1024 * 1024))  # 10MB

UPLOAD_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

@app.get("/")
async def root():
    return {
        "service": "RemoveBG API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "remove_background": "/remove-bg/ (POST)",
            "health": "/health (GET)"
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}

@app.post("/remove-bg/")
async def remove_background(file: UploadFile = File(...)):
    # Validar arquivo
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Arquivo deve ser uma imagem")
    
    # Verificar tamanho do arquivo
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"Arquivo muito grande. Máximo: {MAX_FILE_SIZE/1024/1024}MB")
    
    try:
        # Processar imagem
        input_image = Image.open(io.BytesIO(content))
        
        # Remover background
        output_data = remove(content)
        
        # Salvar resultado
        output_filename = f"{uuid.uuid4()}.png"
        output_path = RESULT_DIR / output_filename
        
        with open(output_path, 'wb') as f:
            f.write(output_data)
        
        # Retornar arquivo
        return FileResponse(
            output_path,
            media_type="image/png",
            filename=f"no_bg_{file.filename.rsplit('.', 1)[0]}.png"
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar imagem: {str(e)}")

@app.post("/remove-bg-base64/")
async def remove_background_base64(file: UploadFile = File(...)):
    """Endpoint que retorna base64 em vez de arquivo"""
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Arquivo deve ser uma imagem")
    
    content = await file.read()
    
    try:
        import base64
        output_data = remove(content)
        base64_data = base64.b64encode(output_data).decode('utf-8')
        
        return JSONResponse({
            "filename": file.filename,
            "base64": f"data:image/png;base64,{base64_data}"
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar imagem: {str(e)}")

# Limpeza periódica (opcional)
@app.on_event("startup")
async def startup_event():
    # Limpar arquivos antigos na inicialização
    for directory in [UPLOAD_DIR, RESULT_DIR]:
        for file in directory.glob("*"):
            if file.is_file():
                file.unlink()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
