from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from typing import List, Dict, Any
import logging
import json
import asyncio
import traceback

from app.db.database import get_db
from app.models.transactions import UserThread, UserThreadMessage, MessageToken
from app.models.dimensions import DimUser, DimModel, DimTokenPricing
from app.schemas.message import MessageCreate, MessageResponse, MessageWithCost
from app.services.anthropic_service import anthropic_service
from app.services.redis_service import redis_service
from app.services.kafka_service import kafka_service
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


async def force_refresh_metrics(thread_id: int):
    """Force refresh metrics for a thread after message processing"""
    # Wait a moment to allow token metrics to be processed
    await asyncio.sleep(2)
    
    # Clear the cache for this thread
    logger.info(f"[MESSAGING] Forcing metrics refresh for thread {thread_id}")
    result = await redis_service.force_refresh_thread_metrics(thread_id)
    
    if result:
        logger.info(f"[MESSAGING] Successfully invalidated metrics cache for thread {thread_id}")
    else:
        logger.warning(f"[MESSAGING] Failed to invalidate metrics cache for thread {thread_id}")


async def process_message_tokens(
    db: Session, 
    message_id: int, 
    token_usage: Dict[str, int], 
    model_id: int
):
    """Process and store token usage for a message"""
    # Store input tokens
    if token_usage.get("input_tokens", 0) > 0:
        input_tokens = MessageToken(
            message_id=message_id,
            token_type="input",
            token_count=token_usage["input_tokens"]
        )
        db.add(input_tokens)
    
    # Store output tokens
    if token_usage.get("output_tokens", 0) > 0:
        output_tokens = MessageToken(
            message_id=message_id,
            token_type="output",
            token_count=token_usage["output_tokens"]
        )
        db.add(output_tokens)
    
    db.commit()
    
    # Publish token metrics to Kafka with explicit logging
    logger.info(f"[MESSAGING] Publishing token metrics for message {message_id}")
    await kafka_service.publish_token_metrics({
        "message_id": message_id,
        "model_id": model_id,
        "token_usage": token_usage,
        "timestamp": str(asyncio.get_event_loop().time())
    })


async def prepare_messages_for_llm(thread_id: int, new_message_content: str, db: Session):
    """Prepare messages for the LLM API with context from thread history"""
    # Get previous messages for context (limit to last 10 for this example)
    previous_messages = (
        db.query(UserThreadMessage)
        .filter(UserThreadMessage.thread_id == thread_id)
        .order_by(UserThreadMessage.created_at)
        .limit(10)
        .all()
    )
    
    # Format messages for Anthropic API
    formatted_messages = []
    for prev_msg in previous_messages:
        formatted_messages.append({
            "role": prev_msg.role,
            "content": prev_msg.content
        })
    
    # Add current message
    formatted_messages.append({"role": "user", "content": new_message_content})
    
    return formatted_messages


@router.on_event("startup")
async def startup_event():
    """Initialize Kafka producer on startup"""
    await kafka_service.initialize()
    logger.info("Kafka service initialized for message API")



@router.post("/", response_model=MessageWithCost)
async def create_message(
    message: MessageCreate, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Create a new message and get AI response"""
    # Check if thread exists
    thread = db.query(UserThread).filter(UserThread.thread_id == message.thread_id).first()
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found"
        )
    
    # Check if user exists
    user = db.query(DimUser).filter(DimUser.user_id == message.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Check if model exists
    model = db.query(DimModel).filter(DimModel.model_id == message.model_id).first()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found"
        )
    
    # Update thread's last activity time
    thread.updated_at = db.query(func.now()).scalar()
    
    # Create user message
    user_message = UserThreadMessage(
        thread_id=message.thread_id,
        user_id=message.user_id,
        content=message.content,
        role="user",
        model_id=message.model_id
    )
    db.add(user_message)
    db.commit()
    
    # Publish raw message to Kafka
    logger.info(f"[MESSAGING] Publishing user message {user_message.message_id} to Kafka")
    await kafka_service.publish_raw_message({
        "message_id": user_message.message_id,
        "thread_id": user_message.thread_id,
        "user_id": user_message.user_id,
        "content": user_message.content,
        "role": user_message.role,
        "model_id": user_message.model_id,
        "created_at": user_message.created_at.isoformat()
    })
    db.refresh(user_message)
    
    # Get formatted messages for LLM API
    formatted_messages = await prepare_messages_for_llm(message.thread_id, message.content, db)

    # Count tokens for user input message
    input_token_count = anthropic_service.count_tokens(message.content)
    
    try:
        # Call Anthropic API
        llm_response = await anthropic_service.create_chat_completion(
            messages=formatted_messages,
            model=model.model_name
        )
        
        # Create assistant message
        assistant_message = UserThreadMessage(
            thread_id=message.thread_id,
            user_id=message.user_id,  # Using same user_id for attribution
            content=llm_response["content"],
            role="assistant",
            model_id=message.model_id
        )
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)

        logger.info(f"[MESSAGING] Publishing LLM response {assistant_message.message_id} to Kafka")
        # Publish LLM response to Kafka
        await kafka_service.publish_llm_response({
            "message_id": assistant_message.message_id,
            "thread_id": assistant_message.thread_id,
            "user_id": assistant_message.user_id,
            "content": assistant_message.content,
            "role": assistant_message.role,
            "model_id": assistant_message.model_id,
            "created_at": assistant_message.created_at.isoformat(),
            "token_usage": llm_response["token_usage"]
        })
        
        # Process tokens in background
        background_tasks.add_task(
            process_message_tokens,
            db,
            user_message.message_id,
            {"input_tokens": input_token_count, "output_tokens": 0},
            message.model_id
        )
        background_tasks.add_task(
            process_message_tokens,
            db,
            assistant_message.message_id,
            {"input_tokens": 0, "output_tokens": llm_response["token_usage"]["output_tokens"]},
            message.model_id
        )
        
        # Force refresh metrics in the background
        background_tasks.add_task(force_refresh_metrics, message.thread_id)
        
        # Get current pricing
        pricing = (
            db.query(DimTokenPricing)
            .filter(
                DimTokenPricing.model_id == message.model_id,
                DimTokenPricing.is_current == True
            )
            .first()
        )
        
        # Use default pricing if not found
        input_price = settings.DEFAULT_INPUT_TOKEN_PRICE
        output_price = settings.DEFAULT_OUTPUT_TOKEN_PRICE
        
        if pricing:
            input_price = pricing.input_token_price
            output_price = pricing.output_token_price
        
        # Calculate costs
        input_cost = input_token_count * input_price
        output_cost = llm_response["token_usage"]["output_tokens"] * output_price
        total_cost = input_cost + output_cost
        
        # Update token counts in the message records for the UI
        user_message.token_count = input_token_count
        assistant_message.token_count = llm_response["token_usage"]["output_tokens"]
        db.commit()
        
        # Return response with cost info
        return {
            "message_id": assistant_message.message_id,
            "thread_id": assistant_message.thread_id,
            "user_id": assistant_message.user_id,
            "content": assistant_message.content,
            "role": assistant_message.role,
            "created_at": assistant_message.created_at,
            "model_id": assistant_message.model_id,
            "input_tokens": input_token_count,
            "output_tokens": llm_response["token_usage"]["output_tokens"],
            "total_cost": total_cost
        }
    
    except Exception as e:
        # Handle errors with more detailed logging
        db.rollback()
        logger.error(f"Detailed error processing message: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing message. Check logs for details."
        )


@router.post("/stream", response_model=None)
async def create_message_stream(
    message: MessageCreate, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Create a new message and stream the AI response"""
    # Check if thread exists
    thread = db.query(UserThread).filter(UserThread.thread_id == message.thread_id).first()
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found"
        )
    
    # Create user message
    user_message = UserThreadMessage(
        thread_id=message.thread_id,
        user_id=message.user_id,
        content=message.content,
        role="user",
        model_id=message.model_id
    )
    db.add(user_message)
    db.commit()

    # Publish raw message to Kafka
    logger.info(f"[MESSAGING] Publishing streamed user message {user_message.message_id} to Kafka")
    await kafka_service.publish_raw_message({
        "message_id": user_message.message_id,
        "thread_id": user_message.thread_id,
        "user_id": user_message.user_id,
        "content": user_message.content,
        "role": user_message.role,
        "model_id": user_message.model_id,
        "created_at": user_message.created_at.isoformat()
    })
    db.refresh(user_message)
    
    # Get formatted messages for LLM API
    formatted_messages = await prepare_messages_for_llm(message.thread_id, message.content, db)

    # Count tokens for user input message
    input_token_count = anthropic_service.count_tokens(message.content)
    
    # Update the user message token count immediately
    user_message.token_count = input_token_count
    db.commit()
    
    # Get model
    model = db.query(DimModel).filter(DimModel.model_id == message.model_id).first()
    model_name = settings.DEFAULT_MODEL
    if model:
        model_name = model.model_name
    
    # Create a placeholder assistant message to update later
    assistant_message = UserThreadMessage(
        thread_id=message.thread_id,
        user_id=message.user_id,
        content="",  # Will be updated when streaming completes
        role="assistant",
        model_id=message.model_id
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    
    # Message ID for the background task
    assistant_message_id = assistant_message.message_id
    
    # Streaming response generator
    async def response_generator():
        full_content = ""
        token_usage = {"input_tokens": input_token_count, "output_tokens": 0}
        
        try:
            async for chunk in anthropic_service.stream_chat_completion(
                messages=formatted_messages,
                model=model_name
            ):
                # Update token usage
                token_usage = chunk["token_usage"]
                
                # Add to full content
                if "content" in chunk:
                    full_content += chunk["content"]
                
                # Yield chunk as JSON
                yield json.dumps(chunk) + "\n"
            
            # Update the assistant message with the full content
            assistant_message = db.query(UserThreadMessage).get(assistant_message_id)
            if assistant_message:
                assistant_message.content = full_content
                assistant_message.token_count = token_usage["output_tokens"]
                db.commit()

                logger.info(f"[MESSAGING] Publishing streamed LLM response {assistant_message.message_id} to Kafka")
                # Publish LLM response to Kafka
                await kafka_service.publish_llm_response({
                    "message_id": assistant_message.message_id,
                    "thread_id": assistant_message.thread_id,
                    "user_id": assistant_message.user_id,
                    "content": assistant_message.content,
                    "role": assistant_message.role,
                    "model_id": assistant_message.model_id,
                    "created_at": assistant_message.created_at.isoformat(),
                    "token_usage": token_usage
                })
            
            # Process tokens in background
            background_tasks.add_task(
                process_message_tokens,
                db,
                user_message.message_id,
                {"input_tokens": input_token_count, "output_tokens": 0},
                message.model_id
            )
            background_tasks.add_task(
                process_message_tokens,
                db,
                assistant_message_id,
                {"input_tokens": 0, "output_tokens": token_usage["output_tokens"]},
                message.model_id
            )
            
            # Force refresh metrics after message is processed
            background_tasks.add_task(force_refresh_metrics, message.thread_id)
        
        except Exception as e:
            # Handle errors
            yield json.dumps({
                "type": "error",
                "error": str(e),
                "role": "assistant",
                "content": f"Error: {str(e)}"
            }) + "\n"
    
    return StreamingResponse(
        response_generator(),
        media_type="application/x-ndjson"
    )


@router.get("/{thread_id}/history", response_model=List[MessageResponse])
async def get_thread_messages(thread_id: int, db: Session = Depends(get_db)):
    """Get all messages for a specific thread"""
    # Check if thread exists
    thread = db.query(UserThread).filter(UserThread.thread_id == thread_id).first()
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found"
        )
    
    # Get messages ordered by creation time
    messages = (
        db.query(UserThreadMessage)
        .filter(UserThreadMessage.thread_id == thread_id)
        .order_by(UserThreadMessage.created_at)
        .all()
    )
    
    return messages