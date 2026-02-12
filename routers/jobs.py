from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pgvector.sqlalchemy import Vector
import models
from database import get_db
from schemas import JobCreate, JobResponse, JobUpdate, APIResponse, MatchRequest, JobMatchResponse
from dependencies import get_current_user
from services.ai import get_embedding

router = APIRouter()

# --- PUBLIC/JOB SEEKER ENDPOINTS ---

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
    """
    **Search & List Jobs**
    
    Retrieves a paginated list of jobs with optional filtering.
    
    **Filters:**
    - `search`: Keywords in Title or Description (partial match).
    - `location`: City or Country (partial match).
    - `is_remote`: Boolean filter for remote jobs.
    - `min_salary`: Filters jobs offering at least this salary.
    
    **Pagination:**
    - Uses `offset/limit` logic. Returns total count and pages in metadata.
    """

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
        query.options(selectinload(models.Job.owner)) # Load Recruiter details
        .order_by(models.Job.job_posted.desc()) # Newest first
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(data_query)
    jobs = result.scalars().all()

    # Calculate Pagination Metadata
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

@router.get("/{job_id}", response_model=APIResponse[JobResponse])
async def get_job(job_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    """
    **Get Single Job Details**
    
    Fetches a specific job by ID, including the Recruiter (Owner) information.
    """
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

# --- RECRUITER ENDPOINTS ---

@router.post("", response_model=APIResponse[JobResponse], status_code=status.HTTP_201_CREATED)
async def create_job(
    job_data: JobCreate, 
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    """
    **Post a New Job (Recruiters Only)**
    
    Creates a job posting and **Automatically Generates an AI Vector**.
    
    **AI Magic:**
    - Concatenates Title + Description + Skills.
    - Uses `get_embedding` to turn text into a 384-dimensional vector.
    - Saves this vector for the "Match" feature.
    """
    # Authorization Check
    if current_user.role not in [models.Role.OWNER, models.Role.ADMIN]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only recruiters can post jobs")
    
    # Validation: Recruiter must have a Company Name
    if not current_user.company_name:
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="You must set a 'Company Name' in your profile before posting jobs."
        )
    
    # AI: Prepare Context for Embedding
    full_job_context = (
        f"Job Title: {job_data.title}. "
        f"Description: {job_data.description}. "
        f"Required Skills: {' '.join(job_data.skills)}"
    )

    # AI: Generate Vector
    embedding = get_embedding(full_job_context)

    new_job = models.Job(
        **job_data.model_dump(),
        company=current_user.company_name,
        owner_id=current_user.id,
        job_embedding=embedding # Store the "Job Brain"
    )

    db.add(new_job)
    await db.commit()
    await db.refresh(new_job, attribute_names=["owner"])

    return APIResponse(
        success=True, 
        message="Job posted successfully", 
        data=new_job
    )

@router.patch("/{job_id}", response_model=APIResponse[JobResponse])
async def update_job(
    job_id: int,
    job_update: JobUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)],
):
    """
    **Update a Job Posting**
    
    Allows recruiters to edit their own job posts.
    **Auto-Update:** If Title, Description, or Skills change, the AI Vector is re-calculated automatically.
    """
    # 1. Get the job
    result = await db.execute(select(models.Job).where(models.Job.id == job_id))
    job = result.scalars().first()

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # 2. Authorization Check
    if job.owner_id != current_user.id and current_user.role != models.Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to edit this job")

    # 3. Apply Updates
    update_data = job_update.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(job, key, value)
    
    # If any text field changed, regenerate the vector to keep search accurate.
    # We check if keys exist in the update payload.
    text_changed = any(k in update_data for k in ["title", "description", "skills"])
    
    if text_changed:
        # Construct context using the NEW values
        full_job_context = (
            f"Job Title: {job.title}. "
            f"Description: {job.description}. "
            f"Required Skills: {' '.join(job.skills)}"
        )
        
        # Generate and save new brain
        job.job_embedding = get_embedding(full_job_context)

    await db.commit()
    await db.refresh(job, attribute_names=["owner"])
    
    return APIResponse(
        success=True, 
        message="Job updated successfully", 
        data=job
    )

@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT) 
async def delete_job(
    job_id: int, 
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    """
    **Delete a Job**
    
    Permanently removes a job posting.
    """
    result = await db.execute(select(models.Job).where(models.Job.id == job_id))
    job = result.scalars().first()

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    
    # Ownership Check
    if job.owner_id != current_user.id and current_user.role != models.Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to edit this job")

    await db.delete(job)
    await db.commit()


# --- AI ENDPOINT ---

@router.post("/match", response_model=APIResponse[list[JobMatchResponse]])
async def match_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    match_data: MatchRequest,
):
    """
    **Manual AI Search (Keyword Match)**
    
    Generates a vector *on-the-fly* from user-provided keywords and finds matching jobs.
    Useful for a "Smart Search Bar".
    """
    # A. Generate the User's Vector from input keywords
    user_query = " ".join(match_data.skills)
    user_embedding = get_embedding(user_query)

    # B. The Vector Search Query (PostgreSQL)
    # Uses L2 Distance (Euclidean) to find closest vectors
    query = (
        select(models.Job, models.Job.job_embedding.l2_distance(user_embedding).label("distance"))
        .options(selectinload(models.Job.owner))
        .order_by(models.Job.job_embedding.l2_distance(user_embedding))
        .limit(match_data.limit)
    )

    result = await db.execute(query)
    matches = result.all() 

    # C. Format the Response with Match Score
    response_data = []
    for job, distance in matches:
        # Convert L2 distance to 0-100% score
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


@router.get("/match", response_model=APIResponse[list[JobMatchResponse]])
async def match_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[AsyncSession, Depends(get_current_user)],
    limit: int = 5
):
    """
    **Auto-Match (Resume Match)**
    
    The core feature of Lokerin. 
    Matches the user's stored **CV Vector** against all **Job Vectors** in the database.
    """
    # 1. Get User Profile
    result = await db.execute(
        select(models.UserProfile).where(models.UserProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile or profile.profile_embedding is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must upload a CV first so we can match you!"
        )
    
    # 2. Vector Search Query (Cosine Similarity)
    query = (
        select(
            models.Job,
            models.Job.job_embedding.cosine_distance(profile.profile_embedding).label("distance")
        )
        .options(selectinload(models.Job.owner))
        .order_by("distance") # Smallest distance = Best match
        .limit(limit)
    )

    result = await db.execute(query)
    matched_jobs = result.all()

    # 3. Calculate Scores
    response_data = []
    for job, distance in matched_jobs:
        # Cosine Distance is 0 to 2. 
        # 0 = Perfect Match, 1 = No Match, 2 = Opposite.
        # Formula: Score = 1 - Distance (clamped to 0%)
        raw_score = 1 - distance
        match_percentage = max(0, min(100, raw_score*100))
    
    job_data = JobMatchResponse(
        **job.__dict__,
        match_score=round(match_percentage, 1)
    )
    response_data.append(job_data)

    return APIResponse(
        success=True,
        message=f"Found {len(response_data)} jobs matching your profiles!",
        data=response_data
    )



 
