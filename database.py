from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from config import settings

# 1. Create the Async Engine
engine = create_async_engine(
    settings.database_url, 
    echo=True,          # Log SQL queries to console
    pool_pre_ping=True, # Checks connection health before using it
)

# 2. Create Session Factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False, # Prevent SQLAlchemy from refreshing objects immediately after commit
    autoflush=False
) 

# 3. Base Model
class Base(DeclarativeBase):
    pass

# 4. Dependency Injection
async def get_db():
    """
    **Database Session Dependency**
    
    Creates a new database session for a request and closes it when finished.
    Usage: `db: Annotated[AsyncSession, Depends(get_db)]`
    """
    async with AsyncSessionLocal() as session:
        yield session

# 5. Database Initialization (Run on startup)
async def init_db():
    """ 
    **Initialize Database**
    
    1. Connects to the DB.
    2. Enables the `vector` extension (Critical for AI features).
    3. Creates all tables defined in `models.py`.
    """
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        
        # Create all tables (User, Job, UserProfile, etc.)
        await conn.run_sync(Base.metadata.create_all)