from pydantic import BaseModel, ConfigDict, Field, EmailStr
from typing import Optional, Generic, TypeVar
from datetime import datetime
from models import Role 

T = TypeVar('T')

# --- API RESPONSE WRAPPER --- 
class APIResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "Success"
    data: Optional[T] = None
    meta: Optional[dict] = None

# --- USER SCHEMAS ---
class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=50)

class UserCreate(UserBase):
    email: EmailStr  
    password: str = Field(min_length=8)
    role: Role = Field(default=Role.SEEKER)
    company_name: Optional[str] = None 

class UserPublic(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: Role
    image_path: str
    company_name: Optional[str] = None

class UserPrivate(UserPublic):
    email: EmailStr 

class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    email: EmailStr | None = Field(default=None, max_length=120)
    company_name: str | None = Field(default=None, max_length=100)
    image_file: str | None = Field(default=None, min_length=1, max_length=200)

class Token(BaseModel):
    access_token: str
    token_type: str

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
    title: str | None = None
    location: str | None = None
    salary: int | None = None
    description: str | None = None
    is_remote: bool | None = None

class JobResponse(JobBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company: str
    owner_id: int
    job_posted: datetime
    owner: UserPublic


# 1. Input Schema for Matching
class MatchRequest(BaseModel):
    skills: list[str]
    limit: int = 5

# 2. Output Schema (Job + Score)
class JobMatchResponse(JobResponse):
    match_score: float #Add a % score to the standard job response