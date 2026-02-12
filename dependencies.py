from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from routers.auth import verify_access_token

from database import get_db
import models

# Defines the "Login" URL
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> models.User:
    """
    **Authentication Dependency**
    
    Protect any route by adding this dependency.
    1. Extracts the Bearer Token from the header.
    2. Decodes and verifies the token.
    3. Fetches the User from the database.
    
    **Returns:** The authenticated `User` object.
    **Raises:** `401 Unauthorized` if token is invalid or user missing.
    """
    # 1. Decode Token
    user_id = verify_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Convert ID safely
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # 3. Fetch User from DB
    result = await db.execute(select(models.User).where(models.User.id == user_id_int))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
        
    return user