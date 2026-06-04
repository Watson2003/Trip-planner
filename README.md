# RoadMind AI Road Trip Planner

AI-powered full-stack road trip planner with a FastAPI backend, LangGraph agents, MCP tools, ChromaDB RAG, and a Next.js 14 frontend.

## Overview

RoadMind AI helps you plan a trip from natural language or structured inputs. It can:

- Parse a trip request with an NVIDIA-hosted LLM endpoint
- Build a route with OpenRouteService
- Pull weather forecasts from OpenWeatherMap
- Estimate budget in INR and USD
- Recommend hotels, restaurants, and attractions with Geoapify-backed context
- Generate a branded multi-page PDF report
- Support real-time follow-up questions through a WebSocket chat assistant

## Architecture

```text
User
  |
  v
Next.js 14 Frontend
  |  \
  |   \-- WebSocket chat --> FastAPI /api/chat/ws
  |
  +------ REST API --------> FastAPI /api/trip/plan
                              |
                              +--> LangGraph planner -> route -> weather -> budget -> recommendation
                              |         |                |         |            |
                              |         |                |         |            +--> ChromaDB RAG + PDF
                              |         |                |         |
                              |         |                |         +--> budget estimation
                              |         |                +--> forecast lookup
                              |         +--> ORS directions/geocoding
                              +--> SQLite trips + trip_reports
```

## Repository Layout

```text
backend/
  agents/        LangGraph agents and graph
  mcp/           MCP server tools
  models/        SQLAlchemy models and Pydantic schemas
  rag/           ChromaDB setup, seed data, retriever
  routers/       FastAPI routes
  tools/         PDF report helper
  utils/         Shared config
frontend/
  app/           Next.js App Router pages
  components/    Map, weather, budget, chat, recommendations
  lib/           API helpers and demo data
```

## Setup

### 1. Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Fill in your keys in `backend/.env`:

- `NVIDIA_API_KEY`
- `GEOAPIFY_API_KEY`
- `OPENWEATHERMAP_API_KEY`
- `OPENROUTESERVICE_API_KEY`

Optional:

- `DATABASE_URL` defaults to SQLite in `backend/road_trip_planner.db`

### 2. Frontend

```powershell
cd frontend
npm install
copy .env.example .env
```

Frontend env vars:

- `BACKEND_URL` for Next.js API rewrites
- `NEXT_PUBLIC_CHAT_WS_URL` for the chat widget WebSocket

### 3. Run locally

Backend:

```powershell
cd backend
.\venv\Scripts\Activate.ps1
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```powershell
cd frontend
npm run dev
```

## Docker

The project is designed to run with Docker Compose after the environment variables are set.

```powershell
docker compose up --build
```

Services:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`

## Environment Variables

### Backend

| Variable | Required | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | No | Async SQLAlchemy database URL |
| `NVIDIA_API_KEY` | Yes | NVIDIA hosted LLM access |
| `NVIDIA_MODEL` | No | NVIDIA chat model name |
| `GEOAPIFY_API_KEY` | Yes | Hotels, restaurants, and attractions lookup |
| `OPENWEATHERMAP_API_KEY` | Yes | Weather forecast API |
| `OPENROUTESERVICE_API_KEY` | Yes | Route and geocoding API |

### Frontend

| Variable | Required | Purpose |
| --- | --- | --- |
| `BACKEND_URL` | Yes | Next.js rewrite target for `/api/*` |
| `NEXT_PUBLIC_CHAT_WS_URL` | Yes | WebSocket URL for the chat assistant |

## API Endpoints

| Method | Route | Description |
| --- | --- | --- |
| `GET` | `/health` | Health check |
| `POST` | `/api/trip/plan` | Plan a trip and return a full trip plan |
| `GET` | `/api/trip/{trip_id}` | Fetch a saved trip |
| `GET` | `/api/trip/{trip_id}/pdf` | Download the generated PDF report |
| `GET` | `/api/weather/{location}` | Fetch a 5-day weather forecast |
| `GET` | `/api/map/route` | Return GeoJSON for map rendering |
| `WebSocket` | `/api/chat/ws` | Real-time AI travel chat |

## Validation and Errors

- Trip requests reject `origin == destination`
- Missing API keys are surfaced as clear backend errors and displayed in the frontend
- The frontend includes a 404 page and a global error boundary

## PDF Report

The report generator creates a branded multi-page PDF with:

1. Trip summary
2. Route map placeholder and waypoints
3. Weather forecast table
4. Budget table in INR and USD
5. Recommendations with descriptions

Every page includes a RoadMind AI header/footer and page numbers.

## Deployment

### Render backend

1. Push the repo to GitHub.
2. Create a new Render Web Service using `backend/render.yaml`.
3. Add the backend environment variables in Render.
4. Deploy.

### Vercel frontend

1. Deploy the `frontend/` folder to Vercel.
2. Set `BACKEND_URL` and `NEXT_PUBLIC_CHAT_WS_URL` in Vercel.
3. Update `frontend/vercel.json` with your deployed backend URL.

## Notes

- The RAG store is seeded with sample Indian road trip destinations.
- The backend uses SQLite by default, so the project works without extra infrastructure.
- The frontend uses Tailwind CSS only for styling.
