from fastapi import FastAPI, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import get_db

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        # Execute a simple query to check the connection
        db.execute(text("SELECT 1"))
        return {"status": "online", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

@app.post("/invoices")
async def create_invoice():
    return {"message": "invoice created", "status": "success"}

@app.get("/invoices/{invoice_id}")
async def read_invoice(invoice_id: str):
    return {"message": "invoice found", "status": "success", "invoice_id": invoice_id}

@app.put("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str):
    return {"message": "invoice updated", "status": "success", "invoice_id": invoice_id}

@app.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str):
    return {"message": "invoice deleted", "status": "success", "invoice_id": invoice_id}


@app.post("/webhooks/quickbooks")
async def quickbooks_webhook(request: Request):
    payload = await request.json()
    notifications = payload.get("eventNotifications", [])
    for notification in notifications:
        realm_id = notification.get("realmId")
        entities = notification.get("dataChangeEvent", {}).get("entities", [])
        for entity in entities:
            print(
                f"[QB Webhook] realmId={realm_id} "
                f"operation={entity.get('operation')} "
                f"name={entity.get('name')} "
                f"id={entity.get('id')} "
                f"lastUpdated={entity.get('lastUpdated')}"
            )
    return {"received": True}


def main():
    print("Hello from two-way-sync!")


if __name__ == "__main__":
    main()
