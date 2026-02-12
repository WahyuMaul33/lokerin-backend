from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Annotated

from database import get_db
import models
import schemas
from dependencies import get_current_user
from schemas import APIResponse, UserProfileResponse
from services.resume import analyze_resume

# Security: Limit file max 2 MB to prevent DoS
MAX_FILE_SIZE = 2 * 1024 * 1024

router = APIRouter()

@router.post("/", response_model=APIResponse[UserProfileResponse])
async def create_or_update_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)],
    force_refresh: bool = False,
    file: UploadFile = File(...), 
):
    """
    **Upload CV & Auto-Generate Profile**
    
    Parses a PDF Resume using internal tools (Regex/PyPDF).
    
    **What it does:**
    1. Extracts Text from PDF.
    2. Extracts Skills (Regex matching).
    3. Calculates Experience Years (Date heuristic).
    4. **Generates Vector Embedding** (User Brain).
    5. Saves/Updates the UserProfile in the DB.
    
    **Upsert Logic:**
    - If profile exists: Updates Skills/Vector/Years. Only updates Bio/Name if empty or `force_refresh=True`.
    - If new: Creates a fresh profile.
    """
    # 1. Validate file type
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files are allowed.")
    
    # 2. Read file content
    file_content = await file.read()

    # 3. Validate max size
    file_size = len(file_content)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is 2MB. Your file is {file_size / 1024 / 1024:.2f}MB"
        )

    # 4. Analyze with AI (Service Layer)
    analysis = analyze_resume(file_content)
    if not analysis:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not extract file from PDF")
    
    # 5. Check if profile exists (Upsert Logic)
    result = await db.execute(
        select(models.UserProfile).where(models.UserProfile.user_id == current_user.id)
    )
    existing_profile = result.scalar_one_or_none()
    
    if existing_profile:
        # UPDATE Existing Profile
        # Always update technical data (Vector, Skills, URL)
        existing_profile.profile_embedding = analysis["embedding"]
        existing_profile.resume_url = file.filename
        existing_profile.skills = analysis["skills"]
        existing_profile.experience_years = analysis["experience_years"]

        # Only overwrite human-readable text (Bio/Name) if requested or empty
        # This prevents overwriting manual edits the user might have made.
        if not existing_profile.bio or force_refresh:
            existing_profile.bio = analysis["text"][:500]
            existing_profile.full_name = analysis.get("extracted_name") or current_user.username
    
        db.add(existing_profile)
        await db.commit()
        await db.refresh(existing_profile)
        return APIResponse(
            success=True,
            message="Profile updated from CV!", 
            data=existing_profile
        )

    else:
        # CREATE New Profile
        new_profile = models.UserProfile(
            user_id=current_user.id,
            full_name=analysis.get("extracted_name") or current_user.username,
            bio=analysis["text"][:500],
            skills=analysis["skills"],
            experience_years=analysis["experience_years"],
            profile_embedding=analysis["embedding"],
            resume_url=file.filename
        )

        db.add(new_profile)
        await db.commit()
        await db.refresh(new_profile)
        return APIResponse(
            success=True,
            message="Profile created from CV!", 
            data=new_profile
        )
    
    
@router.get("/me", response_model=APIResponse[UserProfileResponse])
async def get_my_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    """
    **Get My CV Profile**
    
    Retrieves the parsed profile data (Skills, Experience, Bio) for the current user.
    """
    result = await db.execute(select(models.UserProfile).where(models.UserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found. Please upload a CV.")
        
    return APIResponse(
        success=True, 
        message="Profile found", 
        data=profile)

