from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from services.ai import get_embedding
import models
from database import get_db
from schemas import JobCreate, JobResponse, JobUpdate, APIResponse, MatchRequest, JobMatchResponse
from dependencies import get_current_user
from services.ai import get_embedding

router = APIRouter()

# GET ALL JOBS
@router.get("", response_model=APIResponse[list[JobResponse]])
async def get_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    # Pagination params
    page: int = Query(1, ge=1, description="page number"), # ge= greater than or equal to
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    # Filter params
    search: Optional[str] = None,
    location: Optional[str] = None,
    is_remote: Optional[bool] = None,
    min_salary: Optional[int] = Query(None, ge=0)
    ):

    # Base Query (Filters only)
    query = select(models.Job)

    # Apply filters
    if search:
        query = query.where(
            models.Job.title.ilike(f"%{search}%") |
            models.Job.description.ilike(f"%{search}%")
        )
    if location:
        query = query.where(models.Job.location.ilike(f"%{location}%"))
    if is_remote is not None:
        query = query.where(models.Job.is_remote == is_remote)
    if min_salary:
        query = query.where(models.Job.salary >= min_salary)

    # Count Query
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_items = total_result.scalar_one()

    # Data Query
    offset = (page - 1) * limit

    data_query = (
        query.options(selectinload(models.Job.owner))
        .order_by(models.Job.job_posted.desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(data_query)
    jobs = result.scalars().all()

    # Return Everything
    total_pages = (total_items + limit - 1) // limit

    return APIResponse(
        success=True,
        message="Jobs retrieved successfully",
        data=jobs,
        meta={
            "page": page, 
            "limit": limit, 
            "total_items": total_items,
            "total_pages": total_pages,
            "count": len(jobs)
        }
    )

# CREATE JOB
@router.post("", response_model=APIResponse[JobResponse], status_code=status.HTTP_201_CREATED)
async def create_job(
    job_data: JobCreate, 
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    # Role check
    if current_user.role not in [models.Role.OWNER, models.Role.ADMIN]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only recruiters can post jobs")
    
    # Does the user have a company name? Check
    if not current_user.company_name:
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="You must set a 'Company Name' in your profile before posting jobs."
        )
    
    # Prepare the AI data
    skills_text = " ".join(job_data.skills)
    embedding = get_embedding(skills_text)

    new_job = models.Job(
        **job_data.model_dump(),
        company=current_user.company_name,
        owner_id=current_user.id,
        skills_embedding=embedding
    )

    db.add(new_job)
    await db.commit()
    await db.refresh(new_job, attribute_names=["owner"])

    return APIResponse(
        success=True, 
        message="Job posted successfully", 
        data=new_job
    )

# AI ENDPOINT
@router.post("/match", response_model=APIResponse[list[JobMatchResponse]])
async def match_jobs(
    match_data: MatchRequest,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    # A. Generate the User's Vector
    user_query = " ".join(match_data.skills)
    user_embedding = get_embedding(user_query)

    # B. The Vector Search Query (PostgreSQL Magic)
    query = (
        select(models.Job, models.Job.skills_embedding.l2_distance(user_embedding).label("distance"))
        .options(selectinload(models.Job.owner))
        .order_by(models.Job.skills_embedding.l2_distance(user_embedding))
        .limit(match_data.limit)
    )

    result = await db.execute(query)
    matches = result.all() 

    # C. Format the Response
    response_data = []
    for job, distance in matches:
        # Convert distance to a "Score" (0 to 100%)
        # L2 distance usually ranges 0 to 2 for normalized vectors.
        # This is a rough heuristic: Score = 1 / (1 + distance)
        score = 1 / (1 + distance) 
        
        # Attach score to the job object
        job_dict = job.__dict__
        job_dict["match_score"] = round(score * 100, 1) 
        
        response_data.append(job_dict)

    return APIResponse(
        success=True,
        message=f"Found {len(response_data)} jobs matching your skills",
        data=response_data
    )


# GET ONE JOB
@router.get("/{job_id}", response_model=APIResponse[JobResponse])
async def get_job(job_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(models.Job)
        .options(selectinload(models.Job.owner))
        .where(models.Job.id == job_id)
    )
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return APIResponse(
        success=True, 
        message="Job retrieved successfully",
        data=job
    )
 

# UPDATE USER PARTIAL (PATCH)
@router.patch("/{job_id}", response_model=APIResponse[JobResponse])
async def update_job(
    job_id: int,
    job_update: JobUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)],
):
    # Get the job
    result = await db.execute(select(models.Job).where(models.Job.id == job_id))
    job = result.scalars().first()

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # Only allow updating OWN profile (unless Admin)
    if job.owner_id != current_user.id and current_user.role != models.Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to edit this job")

    # Update only the field sent by the user
    update_data = job_update.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(job, key, value)
    
    await db.commit()
    await db.refresh(job, attribute_names=["owner"])
    
    return APIResponse(
        success=True, 
        message="Job updated successfully", 
        data=job
    )


# DELETE
@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT) 
async def delete_job(
    job_id: int, 
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    result = await db.execute(select(models.Job).where(models.Job.id == job_id))
    job = result.scalars().first()

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    
    # Only allow updating OWN profile (unless Admin)
    if job.owner_id != current_user.id and current_user.role != models.Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to edit this job")

    await db.delete(job)
    await db.commit()