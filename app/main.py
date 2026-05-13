from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.invoices import router as invoices_router
from app.api.webhooks import router as webhooks_router
from app.db.session import get_db

app = FastAPI()

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
