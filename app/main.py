import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.invoices import router as invoices_router
from app.api.webhooks import router as webhooks_router
from app.core.logging import setup_logging
from app.db.session import get_db
from app.workers.sync_worker import sync_worker

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(sync_worker())
    logger.info("Sync worker task started")
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("Sync worker task stopped")


app = FastAPI(lifespan=lifespan)

app.include_router(invoices_router)
app.include_router(webhooks_router)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "online", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Database connection failed: {str(e)}"
        )
