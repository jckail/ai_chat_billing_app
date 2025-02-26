from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class TokenCount(BaseModel):
    """Schema for token count information"""
    token_type: str  # 'input' or 'output'
    token_count: int


class MessageBase(BaseModel):
    """Base schema for message data"""
    content: str
    role: str  # 'user' or 'assistant'


class MessageCreate(MessageBase):
    """Schema for creating a new message"""
    thread_id: int
    user_id: int
    model_id: int


class MessageResponse(MessageBase):
    """Response schema for message information"""
    message_id: int
    thread_id: int
    user_id: int
    created_at: datetime
    model_id: int
    tokens: Optional[List[TokenCount]] = None
    
    class Config:
        orm_mode = True


class MessageWithCost(MessageResponse):
    """Message response with additional cost information"""
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0