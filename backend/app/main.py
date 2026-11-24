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
from .models import Branch,Category,Department,User
from .routes import branches,admin,auth,carwash,dashboard,orders,payments,reports,stock,menu_images,operations,cash_office,paybill

settings=get_settings()
from . import monitoring
monitoring.setup()
def seed():
    with SessionLocal() as db:
        if not db.scalar(select(Branch).limit(1)):
            db.add(Branch(name="Main branch", code="MAIN"));db.flush()
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
async def _retry_printing(every:int):
    """Retry kitchen tickets whose printer was unreachable (never ones that may have printed)."""
    import asyncio,logging
    from .services.printers_services import retry_unsent
    def once():
        with SessionLocal() as db:
            return retry_unsent(db)
    while True:
        await asyncio.sleep(every)
        try:
            await asyncio.to_thread(once)
        except Exception:
            logging.getLogger("biashara360.printers").exception("Background ticket retry failed")

@asynccontextmanager
async def lifespan(app:FastAPI):
    import asyncio,contextlib
    upgrade(engine);seed()
    every=get_settings().print_retry_seconds
    task=asyncio.create_task(_retry_printing(every)) if every>0 else None
    try:
        yield
    finally:
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):await task
app=FastAPI(title=settings.app_name,version="1.0.0",description="Restaurant and car-wash POS API",lifespan=lifespan)

@app.middleware("http")
async def audit_request_context(request:Request,call_next):
    token=request_ip.set(request.client.host if request.client else None)
    try:
        return await call_next(request)
    finally:
        request_ip.reset(token)
app.add_middleware(CORSMiddleware,allow_origins=settings.origins,allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
for router in (branches.router,auth.router,orders.router,payments.router,stock.router,carwash.router,dashboard.router,admin.router,reports.router,menu_images.router,operations.router,cash_office.router,paybill.router,paybill.callbacks):app.include_router(router)
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
