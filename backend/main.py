from contextlib import asynccontextmanager
import os
import sys


for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models.database import init_db
from routers.auth import router as auth_router
from routers.debug import router as debug_router
from routers.health import router as health_router
from routers.map import router as map_router
from routers.chat import router as chat_router
from routers.itinerary import router as itinerary_router
from routers.trip import router as trip_router
from routers.trips import router as trips_router
from routers.weather import router as weather_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="AI Road Trip Planner", version="1.0.0", lifespan=lifespan)

# Get frontend URL from environment
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        FRONTEND_URL,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(debug_router)
app.include_router(auth_router, prefix="/api/auth")
app.include_router(trip_router, prefix="/api")
app.include_router(itinerary_router)
app.include_router(chat_router, prefix="/api")
app.include_router(weather_router, prefix="/api")
app.include_router(map_router, prefix="/api")
app.include_router(trips_router, prefix="/api")
