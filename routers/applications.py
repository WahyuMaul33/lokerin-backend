from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Annotated

from database import get_db
import models
import schemas
from dependencies import get_current_user
from schemas import APIResponse

router = APIRouter(prefix="/applications", tags=["Applications"])

# --- JOB SEEKER ----

# Apply job for the seeker
@router.post("/{job_id}/apply", response_model=APIResponse[schemas.ApplicationResponse])
async def apply_to_job(
    job_id: int,
    application_data: schemas.ApplicationCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    """
    User applies to a specific Job ID.
    """
    # 1. Check if Job Exists
    result = await db.execute(select(models.Job).where(models.Job.id == job_id))
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # 2. Prevent Owner from applying to their own job 
    if job.owner_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot apply to your own job.")

    # 3. Check if User Already Applied (The Constraint)
    existing_app = await db.execute(
        select(models.Application)
        .where(models.Application.job_id == job_id)
        .where(models.Application.user_id == current_user.id)
    )
    if existing_app.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You have already applied to this job.")

    # 4. Create Application
    new_application = models.Application(
        job_id=job_id,
        user_id=current_user.id,
        cv_file=application_data.cv_file,
        status=models.ApplicationStatus.PENDING
    )

    db.add(new_application)
    await db.commit()
    await db.refresh(new_application)

    return APIResponse(
        success=True,
        message="Application submitted successfully!",
        data=new_application
    )

# See job for the the seeker
from sqlalchemy.orm import selectinload

@router.get("/me", response_model=APIResponse[list[schemas.ApplicationResponse]])
async def get_my_applications(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    """
    Seekers can see all jobs they have applied to.
    """
    query = (
        select(models.Application)
        .where(models.Application.user_id == current_user.id)
        .options(selectinload(models.Application.job))
    )
    result = await db.execute(query)
    applications = result.scalars().all()

    return APIResponse(
        success=True,
        message=f"You have applied to {len(applications)} jobs",
        data=applications
    )

# --- JOB OWNER ---

# See job application for the owner
@router.get("/{job_id}/applications", response_model=APIResponse[list[schemas.ApplicationResponse]])
async def get_job_applications(
    job_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    """
    Recruiters can see all applications for their specific job.
    """
    # 1. Verify the job exists AND belongs to the current user
    result = await db.execute(
        select(models.Job).where(models.Job.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only view applications for your own jobs.")

    # 2. Fetch applications
    app_result = await db.execute(
        select(models.Application)
        .where(models.Application.job_id == job_id)
    )
    applications = app_result.scalars().all()

    return APIResponse(
        success=True,
        message=f"Found {len(applications)} applications",
        data=applications
    )

# Update job status for owner
@router.patch("/review/{application_id}", response_model=APIResponse[schemas.ApplicationResponse])
async def review_application(
    application_id: int,
    status_update: schemas.ApplicationStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    """
    Recruiters change the status of an application.
    """
    # 1. Find application and its job
    query = (
        select(models.Application)
        .where(models.Application.id == application_id)
        .options(selectinload(models.Application.job))
    )
    result = await db.execute(query)
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # 2. Only the owner of the job can change the status
    if application.job.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not have permission to review this application.")

    # 3. Update and Save
    application.status = status_update.status
    await db.commit()
    await db.refresh(application)

    return APIResponse(
        success=True,
        message=f"Application status updated to {application.status}",
        data=application
    )