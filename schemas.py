from pydantic import BaseModel, ConfigDict, Field, EmailStr
from typing import Optional, Generic, TypeVar, List
from datetime import datetime
from models import Role, ApplicationStatus

# Generic Type Variable for the API Response wrapper
T = TypeVar('T')

# --- GENERIC API RESPONSE ---
class APIResponse(BaseModel, Generic[T]):
    """
    Standard Wrapper for all API responses.
    """
    success: bool = True
    message: str = "Success"
    data: Optional[T] = None
    meta: Optional[dict] = None

# --- USER SCHEMAS ---
class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=50)

class UserCreate(UserBase):
    """ Schema for Registration Request """
    email: EmailStr  
    password: str = Field(min_length=8)
    role: Role = Field(default=Role.SEEKER)
    company_name: Optional[str] = None 

class UserPublic(UserBase):
    """ Public User Data (Safe to share) """
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: Role
    image_path: str
    company_name: Optional[str] = None

class UserPrivate(UserPublic):
    """ Private User Data (Includes sensitive info like email) """
    email: EmailStr 

class UserUpdate(BaseModel):
    """ Schema for Profile Updates (all fields optional) """
    username: str | None = Field(default=None, min_length=3, max_length=50)
    email: EmailStr | None = Field(default=None, max_length=120)
    company_name: str | None = Field(default=None, max_length=100)
    image_file: str | None = Field(default=None, min_length=1, max_length=200)

class Token(BaseModel):
    """ Schema for JWT Token Response """
    access_token: str
    token_type: str


# --- USER PROFILE (CV) SCHEMAS ---
class UserProfileBase(BaseModel):
    full_name: Optional[str] = None
    bio: Optional[str] = None
    skills: List[str] = None
    experience_years: Optional[int] = 0

class UserProfileCreate(UserProfileBase):
    pass

class UserProfileResponse(UserProfileBase):
    """ Response schema for CV data """
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    resume_url: Optional[str] = None

# --- JOB SCHEMAS ---
class JobBase(BaseModel):
    title: str = Field(min_length=5, max_length=100)
    location: str = Field(min_length=1, max_length=100)
    salary: int = Field(gt=0, description="Salary in IDR") 
    description: str = Field(min_length=20) 
    is_remote: bool = Field(default=False)
    skills: list[str] = Field( 
        min_length=1,
        description="Required skills (e.g., ['Python', 'FastAPI', 'PostgreSQL'])"
    )

class JobCreate(JobBase):
    """ Schema for Posting a Job """
    model_config = ConfigDict(
    json_schema_extra={
        "example": {
            "title": "Senior Backend Engineer",
            "location": "Jakarta, Indonesia",
            "salary": 20000000,
            "description": "We are looking for an experienced backend engineer...",
            "is_remote": False,
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"]
        }
    }
)

class JobUpdate(BaseModel):
    """ Schema for Editing a Job """   
    title: str | None = None
    location: str | None = None
    salary: int | None = None
    description: str | None = None
    is_remote: bool | None = None

class JobResponse(JobBase):
    """ Schema for Viewing a Job """
    model_config = ConfigDict(from_attributes=True)
    id: int
    company: str
    owner_id: int
    job_posted: datetime
    owner: UserPublic

# --- AI MATCHING SCHEMAS ---

class MatchRequest(BaseModel):
    """ Input for 'Manual AI Search' endpoint """
    skills: list[str]
    limit: int = 5

class JobMatchResponse(JobResponse):
    match_score: float 


# --- APPLICATION SCHEMAS ---

class ApplicationCreate(BaseModel):
    """ Schema for Applying to a Job """
    cv_file: Optional[str] = None 
    cover_letter: Optional[str] = None 

class ApplicationResponse(BaseModel):
    """ Schema for Viewing an Application """
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: int
    job_id: int
    status: ApplicationStatus  
    cv_file: Optional[str] = None
    applied_at: datetime
    
    # Optional: uncomment this to see Job details inside the Application response
    #job: JobBase 

class ApplicationStatusUpdate(BaseModel):
    """ Schema for Recruiters to Accept/Reject candidates """
    status: ApplicationStatus