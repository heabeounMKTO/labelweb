from fastapi import FastAPI, HTTPException, Query
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




class Shape(BaseModel):
    label: str
    points: List[List[float]]
    group_id: Optional[int] = None
    shape_type: str = "rectangle"
    flags: dict = {}

class Annotation(BaseModel):
    shapes: List[Shape]
    imagePath: str
    imageData: Optional[str] = None
    imageHeight: int
    imageWidth: int
