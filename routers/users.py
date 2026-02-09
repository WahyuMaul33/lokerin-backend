from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import models
from .auth import hash_password 
from database import get_db
from dependencies import get_current_user 

from schemas import (
    UserCreate, 
    UserPrivate, 
    UserPublic, 
    UserUpdate, 
    JobResponse,  
    APIResponse,
) 

router = APIRouter()

# 1. REGISTER (Public)
@router.post("", response_model=APIResponse[UserPrivate], status_code=status.HTTP_201_CREATED)
async def create_user(
    user: UserCreate, 
    db: Annotated[AsyncSession, Depends(get_db)]
):
    # Check Username
    result = await db.execute(
        select(models.User).where(func.lower(models.User.username) == user.username.lower())
    )
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Username already exists")

    # Check Email
    result = await db.execute(
        select(models.User).where(func.lower(models.User.email) == user.email.lower())
    )
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Only recruiters (OWNER) should have a company name.
    user_company = None
    if user.role == models.Role.OWNER:
        user_company = user.company_name

    # Create User
    new_user = models.User(
        username=user.username,
        email=user.email.lower(),
        hashed_password=hash_password(user.password), 
        role=user.role,               
        company_name=user_company 
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return APIResponse(
        success=True, 
        message=f"User registered successfully as {user.role}", 
        data=new_user
    )
    

# 2. GET CURRENT USER PROFILE
@router.get("/me", response_model=APIResponse[UserPrivate])
async def get_current_user_profile(
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    """
    Get the currently authenticated user's profile.
    Requires valid JWT token in Authorization header.
    """
    return APIResponse(
        success=True, 
        message="Profile retrieved successfully", 
        data=current_user
    )

# 3. GET USER BY ID (Public)
@router.get("/{user_id}", response_model=APIResponse[UserPublic])
async def get_user(
    user_id: int, 
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    
    if not user:
         raise HTTPException(status_code=404, detail="User not found")
    
    return APIResponse(
        success=True, 
        message="user retrieved successfully", 
        data=user
    )

# 4. GET USER'S JOBS
@router.get("/{user_id}/job_posts", response_model=APIResponse[list[JobResponse]])
async def get_user_job_posts(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    # Check if user exists first
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="User not found")

    # Fetch Jobs
    result = await db.execute(
        select(models.Job)
        .options(selectinload(models.Job.owner))
        .where(models.Job.owner_id == user_id)
        .order_by(models.Job.job_posted.desc()),
    )
    jobs = result.scalars().all()
    
    return APIResponse(
        success=True, 
        message="User jobs retrieved successfully", 
        data=jobs
    )

# UPDATE USER ME
@router.patch("/me", response_model=APIResponse[UserPrivate])
async def update_user_me(
    user_update: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    """
    Update current user's profile (Username, Email, Company Name, etc.)
    """
    # 1. Update fields if they are provided
    if user_update.username:
        current_user.username = user_update.username
    if user_update.email:
        current_user.email = user_update.email
    
    # This is the important one for you now! 
    if user_update.company_name:
        current_user.company_name = user_update.company_name
        
    if user_update.image_file:
        current_user.image_file = user_update.image_file

    # 2. Save to DB
    await db.commit()
    await db.refresh(current_user)

    return APIResponse(
        success=True,
        message="Profile updated successfully",
        data=current_user
    )


# 6. UPDATE USER
@router.patch("/{user_id}", response_model=APIResponse[UserPrivate])
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)],
):
    # Only allow updating OWN profile (unless Admin)
    if current_user.id != user_id and current_user.role != models.Role.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to update this profile")

    # Fetch User
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check Username Duplication
    if user_update.username and user_update.username.lower() != user.username.lower():
        result = await db.execute(
            select(models.User).where(func.lower(models.User.username) == user_update.username.lower())
        )
        if result.scalars().first():
            raise HTTPException(status_code=400, detail="Username already exists")

    # Check Email Duplication
    if user_update.email and user_update.email.lower() != user.email.lower():
        result = await db.execute(
            select(models.User).where(func.lower(models.User.email) == user_update.email.lower())
        )
        if result.scalars().first():
            raise HTTPException(status_code=400, detail="Email already registered")

    # Apply Updates
    update_data = user_update.model_dump(exclude_unset=True, exclude={'password'})
    for key, value in update_data.items():
        if key == 'email':
            setattr(user, key, value.lower())
        else:
            setattr(user, key, value)

    await db.commit()
    await db.refresh(user)
    
    return APIResponse(
        success=True, 
        message="Profile updated successfully", 
        data=user
    )

# 7. DELETE USER (Protected)
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int, 
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)] 
):
    # Only allow updating OWN profile (unless Admin)
    if current_user.id != user_id and current_user.role != models.Role.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to delete this account")

    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(user)
    await db.commit()