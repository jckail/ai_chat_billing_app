import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct, desc
from datetime import datetime
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
from app.services.redis_service import redis_service
from app.services.kafka_service import kafka_service
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    await redis_service.initialize()
    await kafka_service.initialize()
    logger.info("[BILLING] Services initialized for billing API")


async def generate_invoice_line_items(invoice_id: int, thread_id: int, db: Session):
    """Generate line items for an invoice"""
    # Get all messages for the thread
    messages = db.query(UserThreadMessage).filter(
        UserThreadMessage.thread_id == thread_id
    ).all()
    
    # For each message, get its token usage
    for message in messages:
        tokens = db.query(MessageToken).filter(
            MessageToken.message_id == message.message_id
        ).all()
        
        # Get current pricing
        pricing = db.query(DimTokenPricing).filter(
            DimTokenPricing.model_id == message.model_id,
            DimTokenPricing.is_current == True
        ).first()
        
        if not pricing:
            # Use default pricing if none found
            continue
        
        # Create line items for each token record
        for token in tokens:
            # Calculate amount based on token type
            if token.token_type == "input":
                amount = token.token_count * pricing.input_token_price
            else:  # output
                amount = token.token_count * pricing.output_token_price
            
            # Create invoice line item
            line_item = UserInvoiceLineItem(
                message_id=message.message_id,
                token_id=token.token_id,
                pricing_id=pricing.pricing_id,
                amount=amount
            )
            db.add(line_item)
    
    db.commit()


@router.get("/metrics/user/{user_id}", response_model=List[BillingMetrics])
async def get_user_billing_metrics(user_id: int, db: Session = Depends(get_db)):
    """Get billing metrics for all threads of a user"""
    # Check if user exists
    user = db.query(DimUser).filter(DimUser.user_id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Try to get metrics from cache
    cached_metrics = await redis_service.get_user_metrics(user_id)
    if cached_metrics:
        logger.info(f"[BILLING] Using cached metrics for user {user_id}")
        return cached_metrics
    
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
        
        # Get token counts from MessageToken table
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
       # If no tokens found in MessageToken table, try getting them from UserThreadMessage table
    if input_tokens == 0 and output_tokens == 0:
        logger.info(f"[BILLING] No tokens found in MessageToken table, checking UserThreadMessage")
        # Get input tokens from user messages
        user_input_tokens = db.query(func.sum(UserThreadMessage.token_count)) \
            .filter(UserThreadMessage.thread_id == thread_id, 
                    UserThreadMessage.role == 'user',
                    UserThreadMessage.token_count != None) \
            .scalar() or 0
        
        # Get output tokens from assistant messages
        assistant_output_tokens = db.query(func.sum(UserThreadMessage.token_count)) \
            .filter(UserThreadMessage.thread_id == thread_id, 
                    UserThreadMessage.role == 'assistant',
                    UserThreadMessage.token_count != None) \
            .scalar() or 0
            
        input_tokens = user_input_tokens
        output_tokens = assistant_output_tokens
        logger.info(f"[BILLING] Found tokens in UserThreadMessage: input={input_tokens}, output={output_tokens}")

     
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
    
    # Cache the metrics
    if result:
        logger.info(f"[BILLING] Caching new user metrics for user {user_id}")
        asyncio.create_task(redis_service.cache_user_metrics(user_id, result))
        logger.info(f"[BILLING] Metrics cached: {len(result)} thread(s)")
    
    return result


@router.get("/metrics/thread/{thread_id}", response_model=BillingMetrics)
async def get_thread_billing_metrics(
    thread_id: int, 
    refresh: bool = False,
    db: Session = Depends(get_db)
):
    """Get billing metrics for a specific thread"""
    logger.info(f"[BILLING] Metrics requested for thread {thread_id}" + 
                f"{' (forced refresh)' if refresh else ''}")
    
    # Check if thread exists
    thread = db.query(UserThread).filter(UserThread.thread_id == thread_id).first()
    if not thread:
        logger.error(f"Thread {thread_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found"
        )
    
    # Try to get metrics from cache unless refresh is requested
    cached_metrics = None
    if refresh:
        # Force clear the cache for this thread
        logger.info(f"[BILLING] Forcing cache refresh for thread {thread_id}")
        await redis_service.force_refresh_thread_metrics(thread_id)
    else:
        cached_metrics = await redis_service.get_thread_metrics(thread_id)
        if cached_metrics:
            logger.info(f"[BILLING] Using cached metrics for thread {thread_id}: {cached_metrics}")
            return cached_metrics
    
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
    total_cost = round((input_tokens * input_price) + (output_tokens * output_price), 6)
    logger.info(f"[BILLING] Calculated total cost for thread {thread_id}: {total_cost} (input: {input_tokens}, output: {output_tokens})")
    
    # Get last activity time
    last_activity = db.query(func.max(UserThreadMessage.created_at)) \
        .filter(UserThreadMessage.thread_id == thread_id) \
        .scalar()
    
    metrics = {
        "thread_id": thread_id,
        "total_messages": message_count,
        "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens,
        "total_cost": total_cost,
        "last_activity": last_activity or thread.created_at
    }
    
    # Cache the metrics
    logger.info(f"[BILLING] Caching new metrics for thread {thread_id}: {metrics}")
    asyncio.create_task(redis_service.cache_thread_metrics(thread_id, metrics))
    
    return metrics


@router.post("/generate-invoice/thread/{thread_id}", response_model=InvoiceResponse)
async def generate_invoice_for_thread(thread_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
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
        logger.info(f"[BILLING] Returning existing invoice for thread {thread_id}")
        return existing_invoice
    
    # Get the metrics to calculate total cost
    metrics = await get_thread_billing_metrics(thread_id, db)
    if not isinstance(metrics, dict):
        metrics = metrics.dict()
        
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
    
    # Generate line items in the background
    background_tasks.add_task(
        generate_invoice_line_items,
        invoice.invoice_id,
        thread_id,
        db
    )
    
    logger.info(f"[BILLING] Created invoice {invoice.invoice_id} for thread {thread_id}")
    
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