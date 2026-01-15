from fastapi import FastAPI, HTTPException, Query
import os
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
import json
import base64
from PIL import Image
import io
from typing import List, Optional
from pydantic import BaseModel
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




@app.get("/images")
def list_images(skip: int = 0, 
                limit: int = 200, 
                image_path: str = Query("", description="Absolute path on host to search images")):
    """
    list all images given a directory (on host)
    """
    path = Path(image_path).resolve()
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")
    
    # Only return image files (basic filter)
    images = [str(p) for p in path.iterdir() if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".gif"]]

    return {"images": images, "total": len(images)}


@app.get("/annotation")
def get_annotation_from_image(
        image_path: str = Query("", description="Absolute path on host to search images")
        ):
    """
    get annotation filename from image (just change the extension)
    """
    return {"ayy": os.path.splitext(image_path)[0] + ".json"}

@app.post("/annotation")
def save_annotation(
        annotation_path: str
        ):
    pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", reload=True, host="0.0.0.0", port=9100)
