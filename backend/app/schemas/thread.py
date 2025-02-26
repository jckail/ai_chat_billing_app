from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ThreadBase(BaseModel):
    """Base schema for thread data"""
    title: str
    model_id: int


class ThreadCreate(ThreadBase):
    """Schema for creating a new thread"""
    user_id: int


class ThreadUpdate(BaseModel):
    """Schema for updating a thread"""
    title: Optional[str] = None
    is_active: Optional[bool] = None


class ThreadResponse(ThreadBase):
    """Response schema for thread information"""
    thread_id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    is_active: bool
    
    class Config:
        orm_mode = True