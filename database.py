from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from config import settings

# tell sqlalchemy to use postgre database (where to connect)
SQLALCHEMY_DATABASE_URL = (
    f"postgresql+asyncpg://{settings.db_user}:{settings.db_password}"
    f"@{settings.db_host}:{settings.db_port}/{settings.db_name}"
)

 # Our connection to the database
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL, 
    echo=True,
    pool_pre_ping=True,
)

# create a session factory // session is transaction with the database, each request gets its own session
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
) 

class Base(DeclarativeBase):
    pass

# Dependency Generator
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
        
#Enable pgvector Extension
async def init_db():
    """ Initialize database with pgvector extension"""
    async with engine.begin() as conn:
        #enable pgvector
        await conn.execute("CREATE EXTENSION IF NOT EXIST")
        #create tables
        await conn.run_sync(Base.metadata.create_all)

