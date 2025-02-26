from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class InvoiceLineItemResponse(BaseModel):
    """Schema for invoice line item response"""
    line_item_id: int
    message_id: int
    token_type: str
    token_count: int
    amount: float
    created_at: datetime
    
    class Config:
        orm_mode = True


class ResourceLineItemResponse(BaseModel):
    """Schema for resource invoice line item response"""
    resource_line_item_id: int
    event_id: int
    user_id: int
    resource_type: str
    quantity: float
    amount: float
    created_at: datetime
    
    class Config:
        orm_mode = True


class InvoiceResponse(BaseModel):
    """Schema for invoice response"""
    invoice_id: int
    user_id: int
    thread_id: int
    total_amount: float
    invoice_date: datetime
    status: str
    line_items: Optional[List[InvoiceLineItemResponse]] = None
    resource_line_items: Optional[List[ResourceLineItemResponse]] = None
    
    class Config:
        orm_mode = True


class BillingMetrics(BaseModel):
    """Schema for thread billing metrics"""
    thread_id: int
    total_messages: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float
    last_activity: datetime