# BuyerBridge

BuyerBridge is a web application that helps home-decor sellers discover real potential business buyers, review and organize leads, and prepare targeted outreach.

Repository: [Wertegved/BuyerBridge](https://github.com/Wertegved/BuyerBridge)

## Key Features

- Account registration and login with PostgreSQL-backed sessions.
- Buyer discovery from OpenStreetMap using the Overpass API, with Photon as a fallback.
- Location resolution through Nominatim.
- Buyer result deduplication, relevance scoring, filtering, and sorting.
- Buyer details and selection, with selected recipients available to the Campaigns page during the browser session.
- Dashboard views for search, lead, and email activity.
- Campaign recipient management and message composition.
- Responsive HTML, CSS, and JavaScript frontend with selectable visual themes.

## How BuyerBridge Works

1. The seller enters product details, a buyer type, and a US location.
2. The backend resolves the location with Nominatim.
3. Buyer discovery queries the Overpass API using OpenStreetMap tags. If all configured Overpass endpoints fail, BuyerBridge makes sequential, tag-filtered Photon reverse requests around the resolved coordinates.
4. Returned businesses are mapped, deduplicated, scored, and limited before they are saved and shown to the user.
5. The seller reviews, filters, sorts, and selects buyers, then manages recipients and drafts an outreach campaign.

## Buyer Discovery and Data Integrity

OpenStreetMap is the source of buyer records. The Overpass API is the primary discovery service; Photon provides fallback results when Overpass is unavailable. Nominatim is used to resolve a location, not to discover businesses.

Buyer records are based on real returned OSM features. BuyerBridge does not generate or hardcode businesses or fabricate missing contact details. Website, phone, and email fields are only populated when available from a source or a connected service. A result is a potential lead, not a guarantee that the business will purchase a product. Coverage depends on the available OpenStreetMap data and external service availability.

## Contact Enrichment and Outreach

The backend includes a Findymail contact-enrichment service that can use a configured API key to look up contact details by business domain. It only accepts an email actually returned by Findymail. The current buyer-discovery route does not invoke this service automatically.

The Campaigns page supports managing selected recipients and composing a subject and message. The email API route currently returns an unavailable response when no provider is configured; even with provider settings present, delivery is not implemented. No email should be assumed to have been sent.

## Authentication, Sessions, and Dashboard

FastAPI handles authentication. Passwords are hashed, and random session tokens are stored as hashes in PostgreSQL. The backend uses an HttpOnly session cookie whose secure and SameSite behavior is controlled by environment settings. Sessions expire after the configured interval.

Authenticated users can review dashboard activity, browse saved buyers, filter and sort discovery results, and manage campaign recipients. Recipient selections are kept in browser `sessionStorage`; they are available to the Campaigns page during that browser session.

## Technology Stack

| Area | Technologies |
| --- | --- |
| Frontend | HTML, CSS, JavaScript |
| Backend | Python 3.12, FastAPI, SQLAlchemy, Pydantic, HTTPX |
| Database and migrations | PostgreSQL 16, Alembic |
| Buyer data | OpenStreetMap, Overpass API, Photon |
| Location resolution | Nominatim |
| Contact enrichment | Findymail service module |
| Local development and deployment | Docker, Docker Compose, Render |

## Project Structure

```text
BuyerBridge/
├── backend/
│   ├── alembic/                 # Database migrations
│   ├── app/
│   │   ├── database/            # SQLAlchemy connection and metadata
│   │   ├── models/               # Database models
│   │   ├── routes/               # Authentication, search, buyers, dashboard, email
│   │   ├── schemas/              # Request and response schemas
│   │   └── services/             # OSM search, location, contacts, email
│   ├── .env.example
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── assets/
│   ├── css/
│   ├── js/
│   ├── index.html
│   └── pages/                    # Login, signup, buyer, dashboard, campaign pages
└── docker-compose.yml
```

## Local Setup

### Prerequisites

- Docker and Docker Compose
- Python 3 for serving the static frontend

### Start PostgreSQL and the API

From the repository root:

```bash
docker compose up --build
```

The Compose configuration starts PostgreSQL and the FastAPI API. For local development it supplies local database and session settings. Do not use development settings or passwords in a production deployment.

Apply database migrations:

```bash
docker compose exec api alembic upgrade head
```

### Serve the Frontend

In a second terminal:

```bash
cd frontend
python -m http.server 5500
```

Open `http://localhost:5500`. The frontend API base URL is configured in `frontend/js/api.js`.
By default, that file points to the project's hosted API. To direct a local frontend to the local Compose API, set `API_BASE_URL` to `http://localhost:8000` in your local working copy; do not commit a local override.

For local configuration outside Docker Compose, copy `backend/.env.example` to `backend/.env` and set appropriate values. Never commit `.env` files or real credentials.

## API Endpoints

The API runs on port `8000` in the local Docker Compose setup. Interactive API documentation is available at `/docs`.

```text
GET    /health

POST   /api/auth/signup
POST   /api/auth/register
POST   /api/auth/login
GET    /api/auth/me
POST   /api/auth/logout
POST   /api/auth/forgot-password

POST   /api/search-buyers
GET    /api/buyers
GET    /api/buyers/{buyer_id}

GET    /api/dashboard
GET    /api/search-history
GET    /api/email-history
DELETE /api/dashboard/data

POST   /api/email/send
```

`/api/auth/forgot-password` currently reports that password reset is not configured. `/api/buyers/{buyer_id}` is a placeholder endpoint. Email delivery is not implemented; see [Contact Enrichment and Outreach](#contact-enrichment-and-outreach).

## Security and Environment Variables

Runtime configuration is read from environment variables (and `backend/.env` for local development). Common settings include:

```text
APP_ENV
TEST_DATABASE_URL
DATABASE_URL
FRONTEND_URL
SESSION_COOKIE_NAME
SESSION_EXPIRE_MINUTES
SESSION_COOKIE_SECURE
SESSION_COOKIE_SAME_SITE
OVERPASS_API_URL
OVERPASS_USER_AGENT
GEOCODING_API_URL
GEOCODING_USER_AGENT
BUSINESS_API_KEY
BUSINESS_API_BASE_URL
CONTACT_API_KEY
CONTACT_API_BASE_URL
FINDYMAIL_API_KEY
EMAIL_API_KEY
EMAIL_FROM
EMAIL_API_BASE_URL
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
SMTP_USE_TLS
SMTP_FROM
SMTP_FROM_NAME
```

Keep credentials in the deployment environment or a local, untracked `.env` file. Use HTTPS and enable secure cookies in production. Database access and authenticated operations are handled by the backend.

## Deployment Architecture

BuyerBridge separates the static frontend from the FastAPI backend. The frontend sends authenticated requests to the API; the API connects to PostgreSQL and to the external OpenStreetMap services for location and buyer discovery. Docker Compose provides the local PostgreSQL and API setup. Render can host the backend and PostgreSQL, with the frontend served as a static site. Production environment variables must specify the frontend origin, database connection, and secure session-cookie settings.

## Project Purpose

BuyerBridge is an internship/MVP project focused on making buyer discovery and early-stage B2B outreach workflows easier for home-decor sellers.
