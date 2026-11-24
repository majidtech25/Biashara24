from contextlib import asynccontextmanager
from fastapi import FastAPI,Request,Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select,text
from sqlalchemy.exc import IntegrityError
from .config import get_settings
from .migrations import upgrade
from .services.audit import request_ip
from .database import Base,SessionLocal,engine
from .services.seed_accounts import disable_default_accounts, seed_company_accounts
from .models import Category,Department,User
from .routes import admin,auth,carwash,dashboard,orders,payments,reports,stock,menu_images,operations,cash_office

settings=get_settings()
def seed():
    with SessionLocal() as db:
        if settings.environment != "production":
            seed_company_accounts(db)
        else:
            disabled = disable_default_accounts(db)
            if disabled:
                import logging
                logging.getLogger("biashara360").error(
                    "Deactivated accounts still using their default development password: %s. "
                    "Create a director with 'python -m app.ops create-admin', then set new passwords "
                    "for these accounts in staff administration before reactivating them.", ", ".join(disabled))
        for name in ("Food","Drinks"):
            if not db.scalar(select(Category).where(Category.name==name)):db.add(Category(name=name))
        for name in ("Kitchen","Barista","Pastry"):
            if not db.scalar(select(Department).where(Department.name==name)):db.add(Department(name=name))
        db.commit()
@asynccontextmanager
async def lifespan(app:FastAPI):
    upgrade(engine);seed();yield
app=FastAPI(title=settings.app_name,version="1.0.0",description="Restaurant and car-wash POS API",lifespan=lifespan)

@app.middleware("http")
async def audit_request_context(request:Request,call_next):
    token=request_ip.set(request.client.host if request.client else None)
    try:
        return await call_next(request)
    finally:
        request_ip.reset(token)
app.add_middleware(CORSMiddleware,allow_origins=settings.origins,allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
for router in (auth.router,orders.router,payments.router,stock.router,carwash.router,dashboard.router,admin.router,reports.router,menu_images.router,operations.router,cash_office.router):app.include_router(router)
@app.get("/health",tags=["System"])
def health():return {"status":"ok","service":settings.app_name}

@app.get('/ready',tags=['System'])
def ready():
    """Readiness: the database answers and its schema is at the newest revision."""
    from .migrations import current_revision, head_revision
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
            revision=current_revision(connection)
        if revision != head_revision():return JSONResponse(status_code=503,content={'status':'not_ready'})
        return {'status':'ready','schema_revision':revision}
    except Exception:
        return JSONResponse(status_code=503,content={'status':'not_ready'})
@app.exception_handler(Exception)
async def unhandled(_:Request,exc:Exception):
    import logging
    logging.getLogger("biashara360").error("Unhandled request failure", exc_info=exc)
    return JSONResponse(status_code=500,content={"detail":"Internal server error"})

@app.exception_handler(IntegrityError)
async def conflict(_:Request,exc:IntegrityError):
    return JSONResponse(status_code=409,content={"detail":"This record conflicts with an existing record or linked data."})
