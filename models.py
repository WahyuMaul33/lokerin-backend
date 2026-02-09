from __future__ import annotations
from enum import Enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, Text, Enum as SQLAEnum, ForeignKey, DateTime, ARRAY, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector 
import enum
from database import Base

# 1. The Role Enum 
class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    OWNER = "OWNER"   # Recruiter
    SEEKER = "SEEKER" # Job Hunter

class ApplicationStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"

# 2. The User Data
class User(Base):
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
    jobs: Mapped[list["Job"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="user", cascade="all, delete-orphan")

    @property
    def image_path(self) -> str:
        return f"/static/profile_pics/{self.image_file}"

# 3. The Job Data
class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    company: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[str] = mapped_column(String(100), nullable=False)
    salary: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False)

    skills: Mapped[list|str] = mapped_column(ARRAY(String), nullable=False, default=list)
    skills_embedding: Mapped[int] = mapped_column(Vector(384), nullable=True)

    # Link to User
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    
    # Timestamps 
    job_posted: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    owner: Mapped["User"] = relationship(back_populates="jobs")
    applications = relationship("Application", back_populates="job", cascade="all, delete-orphan")

#4. Application Data
class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    
    # Who applied?
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # To which job?
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    
    # Status
    status = Column(SQLAEnum(ApplicationStatus), default=ApplicationStatus.PENDING, nullable=False)
    
    # CV File 
    cv_file = Column(String, nullable=True) 
    
    applied_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="applications")
    job = relationship("Job", back_populates="applications")

    # Prevent duplicate applications
    __table_args__ = (
        UniqueConstraint('user_id', 'job_id', name='unique_application_per_user'),
    )