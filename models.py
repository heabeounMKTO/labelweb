from pydantic import BaseModel
from typing import List, Optional 

class Shape(BaseModel):
    label: str
    points: List[List[float]]
    group_id: Optional[str] = None
    shape_type: str = "rectangle"
    flags: dict = {}

class Annotation(BaseModel):
    shapes: List[Shape]
    imagePath: str
    imageData: Optional[str] = None
    imageHeight: int
    imageWidth: int
