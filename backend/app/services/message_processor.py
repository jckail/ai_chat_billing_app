import logging
import asyncio
import json
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
import decimal
from datetime import datetime

from app.db.database import SessionLocal
from app.models.transactions import UserThreadMessage, MessageToken, ApiEvent, UserInvoiceLineItem, ResourceInvoiceLineItem, UserThread
from app.models.dimensions import DimUser, DimModel, DimEventType, DimTokenPricing, DimResourcePricing
from app.services.kafka_consumer_service import kafka_consumer_service
from app.services.redis_service import redis_service
from app.core.config import settings

logger = logging.getLogger(__name__)

async def handle_raw_message(data: Dict[str, Any], db: Optional[Session] = None):
    """Process a raw message from the Kafka topic"""
    logger.info(f"Processing raw message for thread {data.get('thread_id')}")
    
    # Update Redis cache for the thread messages
    thread_id = data.get('thread_id')
    if thread_id:
        # Get current cached messages, if any
        cached_messages = await redis_service.get_thread_messages(thread_id)
        
        if cached_messages:
            # Add new message to cache
            cached_messages.append(data)
            await redis_service.cache_thread_messages(thread_id, cached_messages)
        else:
            # Create new cache with this message
            await redis_service.cache_thread_messages(thread_id, [data])
    
    # No database operations needed as message is already stored

async def handle_llm_response(data: Dict[str, Any], db: Optional[Session] = None):
    """Process an LLM response from the Kafka topic"""
    logger.info(f"Processing LLM response for message {data.get('message_id')}")
    
    # Update Redis cache for the thread messages
    thread_id = data.get('thread_id')
    if thread_id:
        # Get current cached messages, if any
        cached_messages = await redis_service.get_thread_messages(thread_id)
        
        if cached_messages:
            # Add new message to cache
            cached_messages.append(data)
            await redis_service.cache_thread_messages(thread_id, cached_messages)
        else:
            # Create new cache with this message
            await redis_service.cache_thread_messages(thread_id, [data])
    
    # Store token usage in Redis for fast access
    if data.get('message_id') and data.get('token_usage'):
        await redis_service.update_message_tokens(
            data.get('message_id'),
            data.get('token_usage')
        )
    
    # No database operations needed as message is already stored

async def handle_token_metrics(data: Dict[str, Any], db: Optional[Session] = None):
    """Process token metrics from the Kafka topic"""
    logger.info(f"Processing token metrics for message {data.get('message_id')}")
    
    if db is None:
        db = SessionLocal()
        close_db = True
    else:
        close_db = False
    
    try:
        message_id = data.get('message_id')
        model_id = data.get('model_id')
        token_usage = data.get('token_usage', {"input_tokens": 0, "output_tokens": 0})
        
        if not message_id or not model_id:
            logger.error("Missing required data in token metrics")
            return
        
        # Get the message to check thread_id and user_id
        message = db.query(UserThreadMessage).filter(
            UserThreadMessage.message_id == message_id
        ).first()
        
        if not message:
            logger.error(f"Message not found: {message_id}")
            return
        
        # Get current token pricing
        pricing = db.query(DimTokenPricing).filter(
            DimTokenPricing.model_id == model_id,
            DimTokenPricing.is_current == True
        ).first()
        
        if not pricing:
            logger.warning(f"No pricing found for model {model_id}, using defaults")
            input_price = settings.DEFAULT_INPUT_TOKEN_PRICE
            output_price = settings.DEFAULT_OUTPUT_TOKEN_PRICE
        else:
            input_price = pricing.input_token_price
            output_price = pricing.output_token_price
        
        # Check if we need to create invoice line items
        input_tokens = token_usage.get('input_tokens', 0)
        output_tokens = token_usage.get('output_tokens', 0)

        # Update the message's token_count field directly for easier UI display
        if message.role == 'user':
            message.token_count = input_tokens
        else:
            message.token_count = output_tokens
        db.flush()

        logger.info(f"[BILLING] Token usage for message {message_id}: Input={input_tokens}, Output={output_tokens}")
        
        # Delete any existing token records for this message to avoid duplicates
        if input_tokens > 0:
            db.query(MessageToken).filter(
                MessageToken.message_id == message_id,
                MessageToken.token_type == "input"
            ).delete()
            
            # Create a new token record
            token_record = MessageToken(
                message_id=message_id,
                token_type="input",
                token_count=input_tokens
            )
            db.add(token_record)
            db.flush()  # Get the ID without committing
            
            # Create invoice line item
            if pricing:
                amount = round(input_tokens * float(input_price), 6)
                line_item = UserInvoiceLineItem(
                    message_id=message_id,
                    token_id=token_record.token_id,
                    pricing_id=pricing.pricing_id,
                    amount=amount
                )
                db.add(line_item)
        
        if output_tokens > 0:
            # Delete any existing output token records for this message
            db.query(MessageToken).filter(
                MessageToken.message_id == message_id,
                MessageToken.token_type == "output"
            ).delete()
            
            # Create a new token record
            token_record = MessageToken(
                message_id=message_id,
                token_type="output",
                token_count=output_tokens
            )
            db.add(token_record)
            db.flush()  # Get the ID without committing
            
            # Create invoice line item
            if pricing:
                amount = round(output_tokens * float(output_price), 6)
                line_item = UserInvoiceLineItem(
                    message_id=message_id,
                    token_id=token_record.token_id,
                    pricing_id=pricing.pricing_id,
                    amount=amount
                )
                db.add(line_item)
        
        # Commit changes
        db.commit()
        logger.info(f"[BILLING] Successfully stored token metrics for message {message_id}")

        # Invalidate and then immediately recalculate and update thread metrics
        logger.info(f"[BILLING] Invalidating cached metrics for thread {message.thread_id}")
        invalidate_result1 = await redis_service.delete_value('thread_metrics', message.thread_id)
        invalidate_result2 = await redis_service.delete_value('user_metrics', message.user_id)
        logger.info(f"[BILLING] Cache invalidation results - thread: {invalidate_result1}, user: {invalidate_result2}")

        # Add a small delay before recalculating to ensure DB consistency
        await asyncio.sleep(1)        
        logger.info(f"[BILLING] Recalculating metrics for thread {message.thread_id}")
        await update_thread_metrics_cache(message.thread_id, db)
        
    except Exception as e:
        logger.error(f"[BILLING] Error processing token metrics: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        db.rollback()
    finally:
        if close_db:
            db.close()

async def update_thread_metrics_cache(thread_id: int, db: Session):
    """Calculate and cache updated thread metrics"""
    try:
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
        total_cost = round((input_tokens * float(input_price)) + (output_tokens * float(output_price)), 6)
        
        # Get last activity time
        last_activity = db.query(func.max(UserThreadMessage.created_at)) \
            .filter(UserThreadMessage.thread_id == thread_id) \
            .scalar()
        
        # Get thread info
        thread = db.query(UserThread).get(thread_id)
        
        metrics = {
            "thread_id": thread_id,
            "total_messages": message_count,
            "total_input_tokens": input_tokens,
            "total_output_tokens": output_tokens,
            "total_cost": total_cost,
            "last_activity": last_activity or thread.created_at
        }
        
        # Cache the updated metrics
        logger.info(f"[BILLING] Thread metrics calculation:")
        logger.info(f"[BILLING] - Messages: {message_count}")
        logger.info(f"[BILLING] - Input tokens: {input_tokens} @ ${input_price:.6f}/token = ${input_tokens * float(input_price):.6f}")
        logger.info(f"[BILLING] - Output tokens: {output_tokens} @ ${output_price:.6f}/token = ${output_tokens * float(output_price):.6f}")
        logger.info(f"[BILLING] - Total cost: ${total_cost:.6f}")

        cache_result = await redis_service.cache_thread_metrics(thread_id, metrics)
        
        logger.info(f"[BILLING] Updated thread metrics cached (success: {cache_result}): {metrics}")
        return metrics
    
    except Exception as e:
        logger.error(f"[BILLING] Error updating thread metrics cache: {str(e)}")
        return None 
    # No finally block needed as we're just using the passed-in db session

async def handle_inference_events(data: Dict[str, Any], db: Optional[Session] = None):
    """Process inference events from the Kafka topic"""
    logger.info(f"Processing inference event for user {data.get('user_id')}")
    
    if db is None:
        db = SessionLocal()
        close_db = True
    else:
        close_db = False
    
    try:
        user_id = data.get('user_id')
        event_type_name = data.get('event_type')
        model_id = data.get('model_id')
        message_id = data.get('message_id')
        quantity = data.get('quantity', 0)
        metadata = data.get('metadata', {})
        
        if not user_id or not event_type_name or not model_id:
            logger.error("Missing required data in inference event")
            return
        
        # Get or create the event type
        event_type = db.query(DimEventType).filter(
            DimEventType.event_name == event_type_name
        ).first()
        
        if not event_type:
            logger.info(f"Creating new event type: {event_type_name}")
            event_type = DimEventType(
                event_name=event_type_name,
                description=f"API Event Type: {event_type_name}",
                unit_of_measure=metadata.get('unit_of_measure', 'units'),
                is_active=True
            )
            db.add(event_type)
            db.flush()
        
        # Create API event record
        api_event = ApiEvent(
            message_id=message_id,
            user_id=user_id,
            event_type_id=event_type.event_type_id,
            model_id=model_id,
            quantity=quantity
        )
        db.add(api_event)
        db.flush()
        
        # Get resource pricing
        pricing = db.query(DimResourcePricing).filter(
            DimResourcePricing.model_id == model_id,
            DimResourcePricing.event_type_id == event_type.event_type_id,
            DimResourcePricing.is_current == True
        ).first()
        
        # Create invoice line item if pricing exists
        if pricing:
            amount = quantity * pricing.unit_price
            line_item = ResourceInvoiceLineItem(
                event_id=api_event.event_id,
                user_id=user_id,
                resource_pricing_id=pricing.resource_pricing_id,
                quantity=quantity,
                amount=amount
            )
            db.add(line_item)
        
        # Commit changes
        db.commit()
        
        # Invalidate user metrics cache
        await redis_service.delete_value('user_metrics', user_id)
    
    except Exception as e:
        logger.error(f"Error processing inference event: {str(e)}")
        db.rollback()
    finally:
        if close_db:
            db.close()

async def handle_processed_events(data: Dict[str, Any], db: Optional[Session] = None):
    """Process events that have been fully processed"""
    logger.info(f"Handling processed event: {data.get('event_id')}")
    # For now, just log the event. Could be used for archiving or analytics.

async def initialize_message_processors():
    """Initialize Kafka consumers for message processing"""
    # Define handlers for each topic
    topic_handlers = {
        "raw_messages": handle_raw_message,
        "llm_responses": handle_llm_response,
        "token_metrics": handle_token_metrics,
        "inference_events": handle_inference_events,
        "processed_events": handle_processed_events
    }
    
    # Initialize Redis
    await redis_service.initialize()
    
    # Initialize Kafka consumers
    await kafka_consumer_service.initialize(topic_handlers)
    
    logger.info("Message processors initialized with Kafka consumers")

async def shutdown_message_processors():
    """Shut down Kafka consumers and Redis"""
    await kafka_consumer_service.close()
    await redis_service.close()
    logger.info("Message processors shut down")