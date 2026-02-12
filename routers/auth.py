from datetime import UTC, timedelta, datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pwdlib import PasswordHash 
from config import settings
import models
from database import get_db
from schemas import Token

router = APIRouter()

# Password Context: Configures hashing algorithms (Argon2)
password_hash = PasswordHash.recommended()

# Defines where the user sends their credentials to get a token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/users/token")


# --- HELPERS ---

def hash_password(password: str) -> str:
    """
    Takes a plain text password (e.g., 'secret123') and returns a secure hash string.
    """
    return password_hash.hash(password)

def verify_password(plain_password: str, hashed_password:str) -> bool:
    """
    Verifies if a plain text password matches the stored hash.
    Returns True if valid, False otherwise.
    """
    return password_hash.verify(plain_password, hashed_password) 

def create_access_token(data:dict, expires_delta: timedelta | None = None) -> str:
    """ 
    **Create JWT Access Token**
    
    Encodes user data (payload) into a JSON Web Token (JWT).
    
    **Payload claims:**
    - `sub` (Subject): User ID.
    - `exp` (Expiration): When the token becomes invalid.
    """
    to_encode = data.copy()

    # Calculate expiration time
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.access_token_expire_minutes,
        )
    to_encode.update({"exp": expire})

    # Sign the token using users SECRET_KEY and Algorithm (HS256)
    encode_jwt = jwt.encode(
        to_encode,
        settings.secret_key.get_secret_value(),
        algorithm=settings.algorithm,
    )

    return encode_jwt

def verify_access_token(token:str) -> str | None:
    """ 
    **Verify JWT Token**
    
    Decodes a token to ensure it hasn't been tampered with and is not expired.
    Returns the `user_id` (sub) if valid, or None if invalid.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
            options={"require": ["exp", "sub"]}, # Force check for expiration and subject
        )
    except jwt.InvalidTokenError:
        return None
    else:
        return payload.get("sub")
    

# --- AUTH ENDPOINT ---

@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    **Login Endpoint (OAuth2 Standard)**
    
    1. Receives `username` (email) and `password` via form-data.
    2. Verifies credentials against the database.
    3. If valid, issues a JWT Bearer Token.
    
    **Note:** OAuth2PasswordRequestForm uses 'username' field, but we treat it as email.
    """
    # 1. Fetch User (Case-insensitive email search)
    result = await db.execute(
        select(models.User).where(func.lower(models.User.email) == form_data.username.lower())
    )
    user = result.scalars().first()

    # 2. Validate Credentials
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Generate token
    access_token_expire = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.id)}, # Subject is the User ID
        expires_delta=access_token_expire,
    )
    
    return Token(access_token=access_token, token_type="bearer")

