from fastapi import FastAPI, HTTPException, Query
import os
from fastapi.middleware.cors import CORSMiddleware
from models import Annotation
from fastapi.responses import FileResponse
from pathlib import Path
import json
import base64
from PIL import Image
import io
from typing import List, Optional
from pydantic import BaseModel
from utils import image_to_base64,annotation_file_from_image_file, get_cached_thumbnail
import aiofiles
import hashlib

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




@app.get("/images/all")
def list_images(skip: int = 0, 
                limit: int = 200, 
                image_path: str = Query("", description="Absolute path on host to search images")):
    """
    list all images given a directory (on host)
    TODO: add caching for queried directores
    """
    path = Path(image_path).resolve()
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")
    #filter for images only  
    images = [str(p) for p in path.iterdir() if p.suffix.lower() in [".jpg", ".jpeg", ".png"]]
    return {"images": images, "total": len(images)}

@app.get("/images/single")
def get_single_img(image_path: str, thumbnail: bool = Query(False)):
    """
    takes in a absolute path for image, then returns a compressed/cached version of the image!
    """
    if not (os.path.exists(image_path)):
        raise HTTPException(status_code=404, detail="Image not found")
    if thumbnail:
        cache_path = get_cached_thumbnail(image_path)
        return FileResponse(cache_path, media_type="image/jpeg")
    return FileResponse(image_path)


@app.get("/annotation/load")
def load_annotation(image_path: str = Query("", description="Absolute path to image")):
    """
    Load existing annotation JSON for an image
    """
    json_path = annotation_file_from_image_file(image_path)
    
    if not os.path.exists(json_path):
        # Return empty annotation structure (for new images)
        if not os.path.exists(image_path):
            raise HTTPException(status_code=404, detail="Image not found")
        with Image.open(image_path) as img:
            return {
                "shapes": [],
                "imagePath": image_path,
                "imageHeight": img.height,
                "imageWidth": img.width
            }
    
    with open(json_path, 'r') as f:
        return json.load(f)

@app.get("/annotation")
def get_annotation_from_image(
        image_path: str = Query("", description="Absolute path on host to search images")
        ):
    """
    get annotation filename from image (just change the extension)
    """
    return {"ayy": annotation_file_from_image_file(image_path)}

@app.post("/annotation")
async def save_annotation(
        image_path: str,
        annotation: Annotation
        ):
    json_path = annotation_file_from_image_file(image_path)
    
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="image not found!")
    image_data = image_to_base64(image_path)
    labelme_data = {
        "version": "5.0.1",
        "flags": {},
        "shapes": [
            {
                "label": shape.label,
                "points": shape.points,
                "group_id": shape.group_id,
                "shape_type": shape.shape_type,
                "flags": shape.flags
            }
            for shape in annotation.shapes
        ],
        "imagePath": annotation.imagePath,
        "imageData": image_data,
        "imageHeight": annotation.imageHeight,
        "imageWidth": annotation.imageWidth
    }
    async with aiofiles.open(json_path, "w") as f:
        await f.write(json.dumps(labelme_data, indent=2))
    return {"status": "saved", "path": str(json_path)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", reload=True, host="0.0.0.0", port=9100)
