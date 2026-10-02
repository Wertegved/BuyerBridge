# BuyerBridge

BuyerBridge is a B2B buyer-discovery platform for home-decor sellers in the United States. The app keeps the frontend in plain HTML, CSS, and vanilla JavaScript while the backend handles authentication, location resolution, search, and email workflows.

## Architecture

- Frontend: static HTML/CSS/JS served from the frontend folder
- API: FastAPI with PostgreSQL-backed persistence
- Auth: secure HTTP-only session cookie with PostgreSQL-backed sessions
- Discovery: OpenStreetMap/Overpass with a location resolver for US city/state inputs
- Email: SMTP-ready service layer with explicit send actions

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

## Environment variables

Copy the example configuration and fill in local values:

```bash
cp .env.example .env
```

The current project includes the location and provider settings required for Overpass and Nominatim usage.

## PostgreSQL and session model

- PostgreSQL is the persistent source of app data.
- User accounts are stored in the users table.
- Session records live in the sessions table and expire after 30 minutes.
- Session tokens are issued to the browser only as an HTTP-only cookie.

## Discovery and attribution

BuyerBridge currently relies on OpenStreetMap and Overpass because no proprietary business-discovery API is configured. Coverage varies by region, and not every business has public email or website data. Results are displayed as potential business leads rather than guaranteed buyers.

## Docker

```bash
docker compose up --build
```

This runs the FastAPI app and a PostgreSQL service.

## Notes

- The frontend remains a static app and does not introduce a framework.
- Provider-specific logic is isolated in backend service modules.
- External provider verification requires real outbound network access; live provider calls should not be treated as successful without verifying the response.
