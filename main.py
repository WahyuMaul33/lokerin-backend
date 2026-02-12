from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
from database import Base, engine
from routers import jobs, users, auth, applications, profiles

# Configure logging to track server events and errors
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    **Application Lifespan Manager**
    
    This function runs *before* the app starts receiving requests and *after* it shuts down.
    
    **Startup Logic:**
    1. Connects to the database.
    2. Enables the `vector` extension (Critical for AI features).
    3. Creates all tables if they don't exist.
    
    **Shutdown Logic:**
    1. Disposes of the database engine connection to free resources.
    """
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    **Application Lifespan Manager**
    
    This function runs *before* the app starts receiving requests and *after* it shuts down.
    
    **Startup Logic:**
    1. Connects to the database.
    2. Enables the `vector` extension (Critical for AI features).
    3. Creates all tables if they don't exist.
    
    **Shutdown Logic:**
    1. Disposes of the database engine connection to free resources.
    """
    # --- STARTUP ---
    async with engine.begin() as conn:
        # Enable pgvector extension for AI embeddings
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        
        # Create all tables defined in models.py
        await conn.run_sync(Base.metadata.create_all)
    
    yield # App runs here
    
    # --- SHUTDOWN ---
    await engine.dispose()

# Initialize FastAPI App
app = FastAPI(
    title="LokerIn API",
    version="1.0.0",
    lifespan=lifespan, # Attach the startup/shutdown logi
    docs_url="/docs", # Swagger UI URL
    redoc_url="/redoc" # ReDoc URL
)

# --- MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # WARNING: Replace "*" with specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# --- ROUTERS ---

# API Versioning
API_PREFIX = "/api/v1"

# Auth: Login, Token generation
app.include_router(auth.router, prefix=f"{API_PREFIX}/auth", tags=["Auth"])
# Users: Registration, Profile management
app.include_router(users.router, prefix=f"{API_PREFIX}/users", tags=["Users"])
# Jobs: Posting, Searching, AI Matching
app.include_router(jobs.router, prefix=f"{API_PREFIX}/jobs", tags=["Jobs"])
# User Profiles: CV Parsing, Bio
app.include_router(profiles.router, prefix=f"{API_PREFIX}", tags=["User Profiles"])
# Applications: Applying to jobs, Reviewing candidates
app.include_router(applications.router, prefix=f"{API_PREFIX}", tags=["Applications"])


# --- GLOBAL ENDPOINTS ---

@app.get("/", tags=["Health"])
async def health_check():
    """
    Health check endpoint to verify the server is running.
    """
    return {"status": "ok", "service": "LokerIn API v1"}

# --- EXCEPTION HANDLERS ---

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    Catches standard HTTP errors (404, 403, 400) and formats them as JSON.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error_code": exc.status_code, "message": exc.detail},
    )

@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    """
    Catches unexpected Database errors (500) to prevent leaking raw SQL details.
    Logs the full error on the server for debugging.
    """
    logger.error(
        f"Database error at {request.method} {request.url}: {exc}", 
        exc_info=True
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "success": False, 
            "error_code": "DB_ERROR",
            "message": "Internal Database Error"
        },
    )