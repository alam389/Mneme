# Mneme FastAPI Ingestion Scaffold

This project provides a minimal FastAPI application for an ingestion pipeline.

## Structure
- app/main.py: FastAPI app entrypoint
- app/api/routes.py: API routes for health checks and ingestion
- app/ingestion/: ingestion pipeline (`service.py` = business logic, `__main__.py` = standalone CLI)
- app/models/schemas.py: request/response models

## Run locally

1. Create and activate a virtual environment
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```

3. Start the server
   ```bash
   uvicorn app.main:app --reload
   ```

4. Open the docs
   - Swagger UI: http://127.0.0.1:8000/docs
   - ReDoc: http://127.0.0.1:8000/redoc

## Example request

```bash
curl -X POST http://127.0.0.1:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"source": "demo", "payload": {"id": 1, "name": "example"}}'
```

## Run ingestion without the server

The same pipeline can be driven from the command line, which is handy for
iterating on it without booting uvicorn:

```bash
python -m app.ingestion --source demo --payload '{"id": 1, "name": "example"}'
python -m app.ingestion --source demo --file path/to/payload.json
cat payload.json | python -m app.ingestion --source demo
```
