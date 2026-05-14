class ConflictError(Exception):
    """Raised when a sync operation detects state divergence between local and QBO.

    The worker treats this as a terminal failure for the current job (no retries):
    the invoice has already been flagged with `sync_status='conflict'` and
    requires human review before further sync attempts.
    """

    def __init__(self, invoice_id: int, divergent_fields: list[str]):
        self.invoice_id = invoice_id
        self.divergent_fields = divergent_fields
        super().__init__(
            f"Conflict on invoice {invoice_id}: divergent fields={divergent_fields}"
        )
