# IdeaaS API — Test Calls

Base URL: `http://localhost:8000/invoices`

drop_db :
```bash
docker compose exec -T postgres psql -U development -d postgres -c "DROP DATABASE ideaas;"
docker compose exec -T postgres psql -U development -d postgres -c "CREATE DATABASE ideaas;"
```

migrations:
```bash
uv run alembic upgrade head
```
seed:
```
uv run python -m scripts.seed
```
> Start the fastapi server: `uv run fastapi dev`

## Create Invoice 1

```bash
curl -s -X POST http://localhost:8000/invoices \
    -H "Content-Type: application/json" \
    -d '{
      "company_id": 1,
      "customer_id": 1,
      "total_amount": "500.00",
      "issue_date": "2026-05-13",
      "due_date": "2026-06-13",
      "items": [{"item_id": "1", "description": "Consulting", "quantity": "1", "unit_price": "500.00", "amount": "500.00"}]
    }'
```

## Sparse Update

```bash
curl -s -X PUT http://localhost:8000/invoices/1 \
    -H "Content-Type: application/json" \
    -d '{"total_amount": "750.00", "due_date": "2026-07-01"}'
```
## Void Invoice

```bash
curl -s -X POST http://localhost:8000/invoices/1/void
```
# Create Invoice 2
```bash
curl -s -X POST http://localhost:8000/invoices \
    -H "Content-Type: application/json" \
    -d '{
      "company_id": 1,
      "customer_id": 1,
      "total_amount": "200.00",
      "issue_date": "2026-05-13",
      "items": [{"item_id": "1", "description": "Support", "quantity": "1", "unit_price": "200.00", "amount": "200.00"}]
    }'
```

## Delete Invoice

```bash
curl -s -X DELETE http://localhost:8000/invoices/2