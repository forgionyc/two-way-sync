import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class QBOResult:
    data: dict
    request_body: dict | None = None


class QuickBooksClient:
    def __init__(self, base_url: str, realm_id: str, access_token: str):
        self.base_url = base_url
        self.realm_id = realm_id
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
            }
        )

    @property
    def _invoice_base_url(self) -> str:
        return f"{self.base_url}/v3/company/{self.realm_id}/invoice"

    def create_invoice(self, invoice, items: list) -> QBOResult:
        body = {
            "DocNumber": invoice.invoice_number,
            "CustomerRef": {"value": invoice.customer.external_id},
            "TxnDate": str(invoice.issue_date),
            "Line": [
                {
                    "DetailType": "SalesItemLineDetail",
                    "Amount": float(item.amount),
                    "Description": item.description,
                    "SalesItemLineDetail": {
                        "ItemRef": {"value": item.item_id},
                        "Qty": float(item.quantity),
                        "UnitPrice": float(item.unit_price),
                    },
                }
                for item in items
            ],
        }
        if invoice.due_date:
            body["DueDate"] = str(invoice.due_date)

        r = self._session.post(self._invoice_base_url, json=body)
        r.raise_for_status()
        return QBOResult(data=r.json(), request_body=body)

    def update_invoice(self, invoice, changed_fields: dict) -> QBOResult:
        body = {
            "Id": invoice.external_invoice_id,
            "SyncToken": invoice.sync_token,
            "sparse": True,
            **changed_fields,
        }
        r = self._session.post(self._invoice_base_url, json=body)
        r.raise_for_status()
        return QBOResult(data=r.json(), request_body=body)

    def delete_invoice(self, invoice) -> QBOResult:
        body = {"Id": invoice.external_invoice_id, "SyncToken": invoice.sync_token}
        r = self._session.post(
            self._invoice_base_url, json=body, params={"operation": "delete"}
        )
        r.raise_for_status()
        return QBOResult(data=r.json(), request_body=body)

    def void_invoice(self, invoice) -> QBOResult:
        body = {"Id": invoice.external_invoice_id, "SyncToken": invoice.sync_token}
        r = self._session.post(
            self._invoice_base_url, json=body, params={"operation": "void"}
        )
        r.raise_for_status()
        return QBOResult(data=r.json(), request_body=body)

    def read_invoice(self, qbo_invoice_id: str) -> QBOResult:
        url = f"{self._invoice_base_url}/{qbo_invoice_id}"
        r = self._session.get(url)
        r.raise_for_status()
        return QBOResult(data=r.json())
