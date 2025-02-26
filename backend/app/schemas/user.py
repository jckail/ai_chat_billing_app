from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    """Schema for creating a new user"""
    pass


class UserResponse(UserBase):
    """Response schema for user information"""
    user_id: int
    created_at: datetime
    
    class Config:
        orm_mode = True