from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct, desc
from typing import List, Dict, Any

from app.db.database import get_db
from app.models.transactions import (
    UserThread, 
    UserThreadMessage, 
    MessageToken, 
    UserInvoice,
    UserInvoiceLineItem,
    ResourceInvoiceLineItem
)
from app.models.dimensions import DimUser, DimModel, DimTokenPricing
from app.schemas.billing import (
    InvoiceResponse, 
    InvoiceLineItemResponse,
    BillingMetrics
)
from app.core.config import settings

router = APIRouter()


@router.get("/metrics/user/{user_id}", response_model=List[BillingMetrics])
def get_user_billing_metrics(user_id: int, db: Session = Depends(get_db)):
    """Get billing metrics for all threads of a user"""
    # Check if user exists
    user = db.query(DimUser).filter(DimUser.user_id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Get all threads for this user
    threads = db.query(UserThread).filter(UserThread.user_id == user_id).all()
    thread_ids = [thread.thread_id for thread in threads]
    
    if not thread_ids:
        return []
    
    # Collect metrics for each thread
    result = []
    for thread_id in thread_ids:
        # Get message count
        message_count = db.query(func.count(UserThreadMessage.message_id)) \
            .filter(UserThreadMessage.thread_id == thread_id) \
            .scalar() or 0
        
        # Get token counts
        token_metrics = db.query(
                MessageToken.token_type,
                func.sum(MessageToken.token_count).label('token_count')
            ) \
            .join(UserThreadMessage, UserThreadMessage.message_id == MessageToken.message_id) \
            .filter(UserThreadMessage.thread_id == thread_id) \
            .group_by(MessageToken.token_type) \
            .all()
        
        # Initialize token counts
        input_tokens = 0
        output_tokens = 0
        
        # Process token metrics
        for token_type, count in token_metrics:
            if token_type == "input":
                input_tokens = count
            elif token_type == "output":
                output_tokens = count
        
        # Get the latest pricing
        pricing = db.query(DimTokenPricing) \
            .filter(DimTokenPricing.is_current == True) \
            .order_by(desc(DimTokenPricing.effective_from)) \
            .first()
        
        # Use default pricing if not found
        input_price = settings.DEFAULT_INPUT_TOKEN_PRICE
        output_price = settings.DEFAULT_OUTPUT_TOKEN_PRICE
        
        if pricing:
            input_price = pricing.input_token_price
            output_price = pricing.output_token_price
        
        # Calculate cost
        total_cost = (input_tokens * input_price) + (output_tokens * output_price)
        
        # Get last activity time
        last_activity = db.query(func.max(UserThreadMessage.created_at)) \
            .filter(UserThreadMessage.thread_id == thread_id) \
            .scalar()
        
        # Get thread info
        thread = db.query(UserThread).get(thread_id)
        
        # Add metrics to result
        result.append({
            "thread_id": thread_id,
            "total_messages": message_count,
            "total_input_tokens": input_tokens,
            "total_output_tokens": output_tokens,
            "total_cost": total_cost,
            "last_activity": last_activity or thread.created_at
        })
    
    return result


@router.get("/metrics/thread/{thread_id}", response_model=BillingMetrics)
def get_thread_billing_metrics(thread_id: int, db: Session = Depends(get_db)):
    """Get billing metrics for a specific thread"""
    # Check if thread exists
    thread = db.query(UserThread).filter(UserThread.thread_id == thread_id).first()
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found"
        )
    
    # Get message count
    message_count = db.query(func.count(UserThreadMessage.message_id)) \
        .filter(UserThreadMessage.thread_id == thread_id) \
        .scalar() or 0
    
    # Get token counts
    token_metrics = db.query(
            MessageToken.token_type,
            func.sum(MessageToken.token_count).label('token_count')
        ) \
        .join(UserThreadMessage, UserThreadMessage.message_id == MessageToken.message_id) \
        .filter(UserThreadMessage.thread_id == thread_id) \
        .group_by(MessageToken.token_type) \
        .all()
    
    # Initialize token counts
    input_tokens = 0
    output_tokens = 0
    
    # Process token metrics
    for token_type, count in token_metrics:
        if token_type == "input":
            input_tokens = count
        elif token_type == "output":
            output_tokens = count
    
    # Get the latest pricing
    pricing = db.query(DimTokenPricing) \
        .filter(DimTokenPricing.is_current == True) \
        .order_by(desc(DimTokenPricing.effective_from)) \
        .first()
    
    # Use default pricing if not found
    input_price = settings.DEFAULT_INPUT_TOKEN_PRICE
    output_price = settings.DEFAULT_OUTPUT_TOKEN_PRICE
    
    if pricing:
        input_price = pricing.input_token_price
        output_price = pricing.output_token_price
    
    # Calculate cost
    total_cost = (input_tokens * input_price) + (output_tokens * output_price)
    
    # Get last activity time
    last_activity = db.query(func.max(UserThreadMessage.created_at)) \
        .filter(UserThreadMessage.thread_id == thread_id) \
        .scalar()
    
    return {
        "thread_id": thread_id,
        "total_messages": message_count,
        "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens,
        "total_cost": total_cost,
        "last_activity": last_activity or thread.created_at
    }


@router.post("/generate-invoice/thread/{thread_id}", response_model=InvoiceResponse)
def generate_invoice_for_thread(thread_id: int, db: Session = Depends(get_db)):
    """Generate an invoice for a specific thread"""
    # Check if thread exists
    thread = db.query(UserThread).filter(UserThread.thread_id == thread_id).first()
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found"
        )
    
    # Check if invoice already exists for this thread
    existing_invoice = db.query(UserInvoice) \
        .filter(UserInvoice.thread_id == thread_id) \
        .first()
    
    if existing_invoice:
        # Return existing invoice
        return existing_invoice
    
    # Get the metrics to calculate total cost
    metrics = get_thread_billing_metrics(thread_id, db)
    
    # Create a new invoice
    invoice = UserInvoice(
        user_id=thread.user_id,
        thread_id=thread_id,
        total_amount=metrics["total_cost"],
        status="pending"
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    
    # TODO: In a real implementation, we would generate line items
    # for each message and token usage, but for this POC, we'll skip that step
    
    return invoice


@router.get("/invoices/user/{user_id}", response_model=List[InvoiceResponse])
def get_user_invoices(user_id: int, db: Session = Depends(get_db)):
    """Get all invoices for a user"""
    # Check if user exists
    user = db.query(DimUser).filter(DimUser.user_id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Get all invoices for this user
    invoices = db.query(UserInvoice) \
        .filter(UserInvoice.user_id == user_id) \
        .order_by(desc(UserInvoice.invoice_date)) \
        .all()
    
    return invoices