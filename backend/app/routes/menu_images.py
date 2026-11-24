import base64
import binascii
from io import BytesIO
import warnings
from PIL import Image, UnidentifiedImageError
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from ..database import get_db
from ..middleware.auth import require_roles
from ..models.order import MenuImage
from ..schemas import MenuImageUpload

router = APIRouter(prefix="/api", tags=["Menu images"])

MAX_SIDE = 800  # pixels; menu photos are shown small on tablets and phones


def shrink(content: bytes):
    """Turn an uploaded photo the right way up, scale it to at most MAX_SIDE pixels and save it as
    WebP. This also drops camera details such as location (EXIF) from the stored file."""
    from PIL import ImageOps
    with Image.open(BytesIO(content)) as decoded:
        image = ImageOps.exif_transpose(decoded)
        image = image.convert("RGBA" if image.mode in ("RGBA", "LA", "P") else "RGB")
        image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
        out = BytesIO()
        image.save(out, format="WEBP", quality=82, method=4)
    return "image/webp", out.getvalue()


@router.post("/admin/menu-images/cleanup")
def cleanup(db: Session = Depends(get_db), actor=Depends(require_roles("director"))):
    """Remove uploaded photos no menu item uses (for example, photos replaced by newer ones).
    Photos uploaded in the last day are kept, in case a menu item is still being edited."""
    from datetime import datetime, timedelta
    from sqlalchemy import or_, select
    from ..models.order import MenuItem
    from ..services.audit import record
    used = {url.rsplit("/", 1)[-1] for url in db.scalars(select(MenuItem.image_url).where(MenuItem.image_url.like("/api/menu-images/%"))).all()}
    cutoff = datetime.utcnow() - timedelta(days=1)
    unused = [i for i in db.scalars(select(MenuImage.id).where(or_(MenuImage.created_at.is_(None), MenuImage.created_at < cutoff))).all()
              if i not in used]
    for identity in unused:
        db.delete(db.get(MenuImage, identity))
    record(db, actor, 'cleanup', 'menu_images', 0, after={'removed': len(unused)})
    db.commit()
    return {"removed": len(unused), "kept_in_use": len(used)}


@router.post("/admin/menu-images", status_code=201)
def upload(data: MenuImageUpload, db: Session = Depends(get_db), actor=Depends(require_roles("manager", "director"))):
    try:
        header, encoded = data.data.split(",", 1)
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(422, "Invalid photo data")
    types = {"data:image/jpeg;base64":"image/jpeg", "data:image/png;base64":"image/png", "data:image/webp;base64":"image/webp"}
    kind = types.get(header)
    valid = ((kind == "image/jpeg" and content.startswith(b"\xff\xd8\xff")) or
             (kind == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n")) or
             (kind == "image/webp" and content[:4] == b"RIFF" and content[8:12] == b"WEBP"))
    if not valid or not 12 <= len(content) <= 2 * 1024 * 1024:
        raise HTTPException(422, "Choose a JPEG, PNG or WebP photo up to 2 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as decoded:
                if decoded.format != {'image/png':'PNG','image/jpeg':'JPEG','image/webp':'WEBP'}[kind]:
                    raise ValueError('Image format does not match its declared type')
                if max(decoded.size) > 4096 or decoded.width * decoded.height > 16000000:
                    raise ValueError('Image dimensions exceed the supported limit')
                if getattr(decoded,'n_frames',1) != 1: raise ValueError('Choose a still photo')
                decoded.verify()
            with Image.open(BytesIO(content)) as decoded:
                decoded.load()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, 'Choose a valid still JPEG, PNG or WebP photo, at most 4096 pixels per side and 16 megapixels.')
    original = len(content)
    kind, content = shrink(content)
    photo = MenuImage(id=uuid4().hex, content_type=kind, content=content)
    from ..services.audit import record
    db.add(photo)
    # UUID identity is recorded in the payload; this audit schema uses numeric entity IDs.
    record(db, actor, 'upload', 'menu_images', 0, after={'image_id':photo.id,'content_type':kind,'bytes':len(content),'uploaded_bytes':original})
    db.commit()
    return {"image_url":"/api/menu-images/" + photo.id}

@router.get("/menu-images/{identity}")
def read(identity: str, db: Session = Depends(get_db)):
    photo = db.get(MenuImage, identity)
    if not photo: raise HTTPException(404, "Photo not found")
    return Response(photo.content, media_type=photo.content_type,
                    headers={"X-Content-Type-Options":"nosniff", "Cache-Control":"public, max-age=31536000, immutable"})
