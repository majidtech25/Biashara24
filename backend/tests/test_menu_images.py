"""Uploaded menu photos are turned upright, made smaller and stripped of camera details;
photos no menu item uses can be removed."""
import base64
from datetime import datetime, timedelta
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.database import SessionLocal
from app.main import app
from app.models.order import MenuImage
from test_integration import login, new_menu


def jpeg(width, height, orientation=None):
    image = Image.new("RGB", (width, height), (200, 120, 40))
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation  # camera says: rotate when showing
    exif[0x010F] = "PhoneMaker"  # camera make, should not be kept
    out = BytesIO(); image.save(out, format="JPEG", exif=exif.tobytes(), quality=70)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


def test_large_photo_is_stored_small_upright_and_without_camera_details():
    with TestClient(app) as c:
        manager = login(c, "manager@gmail.com", "manager123")
        r = c.post("/api/admin/menu-images", headers=manager, json={"data": jpeg(2000, 1000, orientation=6)})
        assert r.status_code == 201, r.text
        stored = c.get(r.json()["image_url"])
        assert stored.headers["content-type"] == "image/webp"
        with Image.open(BytesIO(stored.content)) as photo:
            assert photo.format == "WEBP" and photo.size == (400, 800)  # rotated upright and scaled to 800 px
            assert 0x010F not in photo.getexif()
        small = c.post("/api/admin/menu-images", headers=manager, json={"data": jpeg(300, 200)})
        with Image.open(BytesIO(c.get(small.json()["image_url"]).content)) as photo:
            assert photo.size == (300, 200)  # small photos are not enlarged


def test_unused_old_photos_can_be_removed():
    with TestClient(app) as c:
        director, manager = login(c), login(c, "manager@gmail.com", "manager123")
        urls = [c.post("/api/admin/menu-images", headers=manager, json={"data": jpeg(100, 100)}).json()["image_url"] for _ in range(3)]
        used, unused_old, unused_new = urls
        item = new_menu(c, manager)
        assert c.put(f"/api/admin/menu/{item['id']}", headers=manager, json={"image_url": used}).status_code == 200
        with SessionLocal() as db:
            for url in (used, unused_old):
                db.get(MenuImage, url.rsplit("/", 1)[-1]).created_at = datetime.utcnow() - timedelta(days=3)
            db.commit()
        assert c.post("/api/admin/menu-images/cleanup", headers=manager).status_code == 403
        r = c.post("/api/admin/menu-images/cleanup", headers=director)
        assert r.status_code == 200 and r.json()["removed"] >= 1
        assert c.get(used).status_code == 200
        assert c.get(unused_old).status_code == 404
        assert c.get(unused_new).status_code == 200  # uploaded today: may still be in use soon
