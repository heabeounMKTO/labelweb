from pathlib import Path 
import os
from PIL import Image
import base64
import io
import hashlib



CACHE_DIR="/tmp/labelweb_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def image_to_base64(image_path: Path) -> str:
    with Image.open(image_path) as img:
        # Convert to RGB if necessary
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=95)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')


def get_cached_thumbnail(image_path: Path, size=(800, 800)) -> Path:
    cache_key = hashlib.md5(str(image_path).encode()).hexdigest()
    cache_path = CACHE_DIR / f"{cache_key}.jpg"
    
    if not cache_path.exists():
        with Image.open(image_path) as img:
            img.thumbnail(size, Image.Resampling.LANCZOS)
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            img.save(cache_path, 'JPEG', quality=85)
    
    return cache_path


def get_annotation_path(image_path: str, image_dir: str) -> Path:
    """Get annotation JSON path for an image"""
    rel_path = Path(image_path)
    json_path = image_dir / rel_path.with_suffix('.json')
    json_path.parent.mkdir(parents=True, exist_ok=True)
    return json_path
