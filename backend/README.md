# FastAPI Backend

This is the FastAPI backend for the QC/QA AI Platform.

## Python version

Use **Python 3.11 or 3.12** for local development (see repo root ``.python-version`` for pyenv). **Python 3.14** may hit TLS certificate verification failures when connecting to cloud Postgres (e.g. Render) from macOS; prefer 3.12 or set ``DATABASE_SSL_INSECURE_DEV=true`` with ``APP_ENV=development`` only (see ``.env.example``).

## Setup

1. **Install Python dependencies:**
```bash
pip install -r requirements.txt
```

2. **Set up environment variables:**
Create a `.env` file in the `backend/` directory:
```env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/procore_int
PROCORE_CLIENT_ID=your_client_id
PROCORE_CLIENT_SECRET=your_client_secret
PROCORE_REDIRECT_URI=http://localhost:2000/api/procore/oauth/callback
ANTHROPIC_API_KEY=your_anthropic_key
OPENAI_API_KEY=your_openai_key
```

3. **Initialize database:**
```bash
python -c "from database import init_db; init_db()"
```

## Running the Server

### Development mode:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 2000
```

### Production mode:
```bash
uvicorn main:app --host 0.0.0.0 --port 2000
```

## API Documentation

Once the server is running, visit:
- Swagger UI: http://localhost:2000/docs
- ReDoc: http://localhost:2000/redoc

## Project Structure

```
backend/
├── main.py              # FastAPI app entry point
├── config.py            # Configuration settings
├── database.py          # Database setup
├── api/
│   └── routes/         # API route handlers
├── models/
│   ├── database.py     # SQLAlchemy models
│   └── schemas.py      # Pydantic schemas
└── services/
    └── storage.py      # Data access layer
```

