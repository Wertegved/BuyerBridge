# BuyerBridge

BuyerBridge is a professional B2B buyer-discovery and outreach application for home-decor sellers in the United States.

## Local development

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Backend URL: http://localhost:8000
Swagger: http://localhost:8000/docs

### Frontend

```bash
cd frontend
python -m http.server 5500
```

Frontend URL: http://localhost:5500

## Notes

- The frontend is plain HTML, CSS, and vanilla JavaScript.
- FastAPI is the backend API layer.
- PostgreSQL is configured as the application database.
- Real provider integrations are isolated in backend services. The current implementation provides safe placeholders until provider credentials and integration code are configured.
