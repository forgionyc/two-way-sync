from fastapi import APIRouter

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.post("")
async def create_invoice():
    return {"message": "invoice created", "status": "success"}


@router.get("/{invoice_id}")
async def read_invoice(invoice_id: str):
    return {"message": "invoice found", "status": "success", "invoice_id": invoice_id}


@router.put("/{invoice_id}")
async def update_invoice(invoice_id: str):
    return {"message": "invoice updated", "status": "success", "invoice_id": invoice_id}


@router.delete("/{invoice_id}")
async def delete_invoice(invoice_id: str):
    return {"message": "invoice deleted", "status": "success", "invoice_id": invoice_id}
