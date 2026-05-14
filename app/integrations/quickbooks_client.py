import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

# (connect_timeout, read_timeout) in seconds. A hung QBO must not block the
# worker indefinitely; these caps bound the worker thread.
DEFAULT_TIMEOUT: tuple[float, float] = (5.0, 30.0)


@dataclass
class QBOResult:
    data: dict
    request_body: dict | None = None
    request_url: str | None = None


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
    def invoice_base_url(self) -> str:
        return f"{self.base_url}/v3/company/{self.realm_id}/invoice"

    @property
    def query_url(self) -> str:
        return f"{self.base_url}/v3/company/{self.realm_id}/query"

    # Backwards-compatible alias for older call sites.
    @property
    def _invoice_base_url(self) -> str:
        return self.invoice_base_url

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

        url = self.invoice_base_url
        r = self._session.post(url, json=body, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return QBOResult(data=r.json(), request_body=body, request_url=url)

    def update_invoice(self, invoice, changed_fields: dict) -> QBOResult:
        body = {
            "Id": invoice.external_invoice_id,
            "SyncToken": invoice.sync_token,
            "sparse": True,
            **changed_fields,
        }
        url = self.invoice_base_url
        r = self._session.post(url, json=body, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return QBOResult(data=r.json(), request_body=body, request_url=url)

    def delete_invoice(self, invoice) -> QBOResult:
        body = {"Id": invoice.external_invoice_id, "SyncToken": invoice.sync_token}
        url = self.invoice_base_url
        r = self._session.post(
            url,
            json=body,
            params={"operation": "delete"},
            timeout=DEFAULT_TIMEOUT,
        )
        r.raise_for_status()
        return QBOResult(data=r.json(), request_body=body, request_url=url)

    def void_invoice(self, invoice) -> QBOResult:
        body = {"Id": invoice.external_invoice_id, "SyncToken": invoice.sync_token}
        url = self.invoice_base_url
        r = self._session.post(
            url,
            json=body,
            params={"operation": "void"},
            timeout=DEFAULT_TIMEOUT,
        )
        r.raise_for_status()
        return QBOResult(data=r.json(), request_body=body, request_url=url)

    def read_invoice(self, qbo_invoice_id: str) -> QBOResult:
        url = f"{self.invoice_base_url}/{qbo_invoice_id}"
        r = self._session.get(url, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return QBOResult(data=r.json(), request_url=url)

    def query_invoice_by_doc_number(self, doc_number: str) -> QBOResult:
        """Query QBO for an invoice with a given DocNumber.

        Used as a pre-flight reconciliation step on outbound create retries: if a
        previous attempt got the POST to QBO but lost the response, the invoice
        already exists in QBO under our DocNumber and we must link to it instead
        of creating a duplicate.
        """
        url = self.query_url
        # QBO escapes single quotes in query strings by doubling them; DocNumber
        # is server-generated (`INV-YYYY-NNNNNNNNN`) and cannot contain quotes.
        params = {"query": f"select * from Invoice where DocNumber = '{doc_number}'"}
        r = self._session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return QBOResult(data=r.json(), request_url=url)
