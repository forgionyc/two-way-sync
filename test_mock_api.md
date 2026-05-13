# QuickBooks Mock API — Test Calls

Base URL: `http://localhost:4000/v3/company/123456789`

> Start the mock server before running: `mockoon-cli start --data quickbooks-mock.json --port 4000`

  # Simulate QBO creates invoice → GET returns SyncToken "0" → saved in DB
```bash
curl -s -X POST http://localhost:4000/simulate/qbo/invoice/created
```

  # Simulate QBO updates invoice → GET returns SyncToken "1" → "1" != "0" → update runs
```bash
curl -s -X POST http://localhost:4000/simulate/qbo/invoice/updated
```

  # Simulate QBO voided invoice 9001
```bash
curl -s -X POST http://localhost:4000/simulate/qbo/invoice/voided
```

  # Simulate QBO deleted invoice 9001
```bash
curl -s -X POST http://localhost:4000/simulate/qbo/invoice/deleted