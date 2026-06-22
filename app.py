from fastapi import FastAPI, File, UploadFile
from fastapi.responses import Response
from rembg import remove, new_session
from io import BytesIO
from PIL import Image

app = FastAPI()

# modelo mais leve para VPS
session = new_session("u2netp")

@app.post("/remove-bg")
async def remove_bg(file: UploadFile = File(...)):
    input_data = await file.read()

    # otimização: resize antes do processamento
    img = Image.open(BytesIO(input_data)).convert("RGB")
    img.thumbnail((1024, 1024))

    buffer = BytesIO()
    img.save(buffer, format="PNG")

    output = remove(buffer.getvalue(), session=session)

    return Response(content=output, media_type="image/png")
