from __future__ import annotations
from enum import Enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, Text, Enum as SQLAEnum, ForeignKey, DateTime, ARRAY, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector 
import enum
from database import Base

# --- ENUMS ---
class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    OWNER = "OWNER"   # Recruiter / Employer
    SEEKER = "SEEKER" # Job Seeker / Candidate

class ApplicationStatus(str, enum.Enum):
    """ Tracks the lifecycle of a job application """
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


# --- MODELS ---
class User(Base):
    """
    **User Table**
    Stores authentication details and basic profile info for all user types.
    """
    __tablename__ = "users"

    # Core Auth Data
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Access Control
    role: Mapped[Role] = mapped_column(SQLAEnum(Role), default=Role.SEEKER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Profile Data (Merged & Nullable)
    image_file: Mapped[str | None] = mapped_column(String(200), default="default.jpg")
    
    # Recruiter Specific
    company_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Seeker Specific
    resume_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Relationships
    # 'jobs': Jobs posted by this user (if Recruiter)
    jobs: Mapped[list["Job"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    # 'applications': Jobs this user has applied to (if Seeker)
    applications = relationship("Application", back_populates="user", cascade="all, delete-orphan")
    # 'profile': Detailed CV data (if Seeker)
    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")

    @property
    def image_path(self) -> str:
        return f"/static/profile_pics/{self.image_file}"

class UserProfile(Base):
    """
    **User Profile Table (CV Data)**
    Stores detailed data parsed from the user's uploaded Resume (PDF).
    This is separate from the User table to keep the auth table lightweight.
    """
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    # Parsed Data
    full_name = Column(String, nullable=True)
    bio = Column(String, nullable=True) # Extracted summary
    skills = Column(ARRAY(String), default=[]) # e.g. ["Python", "Docker"]
    experience_years = Column(Integer, default=0)

    # File Reference
    resume_url = Column(String, nullable=True)

    # AI BRAIN: The Vector Embedding of the user's CV
    profile_embedding = Column(Vector(384))

    # Relationship
    user = relationship("User", back_populates="profile")


class Job(Base):
    """
    **Job Table**
    Stores job listings posted by Recruiters.
    """
    __tablename__ = "jobs"

    # Basic Info
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    company: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[str] = mapped_column(String(100), nullable=False)
    salary: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False)

    # Skills 
    skills: Mapped[list|str] = mapped_column(ARRAY(String), nullable=False, default=list)
    
    # AI BRAIN: The Vector Embedding of the job description
    job_embedding: Mapped[int] = mapped_column(Vector(384), nullable=True)

    # Owner (Recruiter)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    
    # Metadata 
    job_posted: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    owner: Mapped["User"] = relationship(back_populates="jobs")
    applications = relationship("Application", back_populates="job", cascade="all, delete-orphan")


class Application(Base):
    """
    **Application Table**
    Connects a User (Seeker) to a Job.
    """
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    
    # Who applied?
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # To which job?
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    
    # Status (Pending -> Accepted/Rejected)
    status = Column(SQLAEnum(ApplicationStatus), default=ApplicationStatus.PENDING, nullable=False)
    
    # CV Snapshot 
    cv_file = Column(String, nullable=True) 
    applied_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="applications")
    job = relationship("Job", back_populates="applications")

    # Constraint: Prevent a user from applying to the same job twice
    __table_args__ = (
        UniqueConstraint('user_id', 'job_id', name='unique_application_per_user'),
    )