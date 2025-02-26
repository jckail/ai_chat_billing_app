import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List
from kafka import KafkaProducer
import uvicorn
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("event_collector")

# Kafka configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC_INFERENCE_EVENTS = "inference-events"

# Initialize FastAPI app
app = FastAPI(
    title="Event Collector Service",
    description="Service for collecting inference API events",
    version="0.1.0"
)

# Initialize Kafka producer
try:
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        acks='all',
        retries=5,
        retry_backoff_ms=500,
    )
    logger.info(f"Initialized Kafka producer connected to {KAFKA_BOOTSTRAP_SERVERS}")
except Exception as e:
    logger.error(f"Failed to initialize Kafka producer: {str(e)}")
    producer = None


class EventBase(BaseModel):
    """Base model for event data"""
    user_id: int
    model_id: int
    event_type_id: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TokenEvent(EventBase):
    """Model for token usage events"""
    message_id: int = None
    input_tokens: int = 0
    output_tokens: int = 0


class ResourceEvent(EventBase):
    """Model for resource usage events (like images)"""
    resource_type: str
    quantity: float


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    if producer is None:
        return {"status": "degraded", "kafka": "disconnected"}
    
    try:
        # Check if we can connect to Kafka
        producer.flush(timeout=5)
        return {"status": "healthy", "kafka": "connected"}
    except Exception as e:
        logger.error(f"Kafka health check failed: {str(e)}")
        return {"status": "degraded", "kafka": f"error: {str(e)}"}


@app.post("/events/token")
async def collect_token_event(event: TokenEvent):
    """Collect a token usage event"""
    if producer is None:
        raise HTTPException(
            status_code=503,
            detail="Event collector is not connected to Kafka"
        )
    
    try:
        # Convert event to dictionary
        event_dict = event.dict()
        
        # Convert timestamp to string
        event_dict["timestamp"] = event_dict["timestamp"].isoformat()
        
        # Send event to Kafka
        producer.send(
            topic=KAFKA_TOPIC_INFERENCE_EVENTS,
            value=event_dict
        )
        
        # Flush to ensure it's sent
        producer.flush()
        
        logger.info(f"Token event sent to Kafka: user_id={event.user_id}, model_id={event.model_id}")
        return {"status": "success", "event_type": "token"}
    
    except Exception as e:
        logger.error(f"Failed to send token event to Kafka: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send event: {str(e)}"
        )


@app.post("/events/resource")
async def collect_resource_event(event: ResourceEvent):
    """Collect a resource usage event"""
    if producer is None:
        raise HTTPException(
            status_code=503,
            detail="Event collector is not connected to Kafka"
        )
    
    try:
        # Convert event to dictionary
        event_dict = event.dict()
        
        # Convert timestamp to string
        event_dict["timestamp"] = event_dict["timestamp"].isoformat()
        
        # Send event to Kafka
        producer.send(
            topic=KAFKA_TOPIC_INFERENCE_EVENTS,
            value=event_dict
        )
        
        # Flush to ensure it's sent
        producer.flush()
        
        logger.info(f"Resource event sent to Kafka: user_id={event.user_id}, model_id={event.model_id}, resource_type={event.resource_type}")
        return {"status": "success", "event_type": "resource"}
    
    except Exception as e:
        logger.error(f"Failed to send resource event to Kafka: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send event: {str(e)}"
        )


@app.post("/events/batch")
async def collect_batch_events(events: List[Dict[str, Any]] = Body(...)):
    """Collect a batch of events"""
    if producer is None:
        raise HTTPException(
            status_code=503,
            detail="Event collector is not connected to Kafka"
        )
    
    try:
        # Process each event in the batch
        for event in events:
            # Ensure timestamp is a string
            if "timestamp" in event and isinstance(event["timestamp"], datetime):
                event["timestamp"] = event["timestamp"].isoformat()
            
            # Send event to Kafka
            producer.send(
                topic=KAFKA_TOPIC_INFERENCE_EVENTS,
                value=event
            )
        
        # Flush to ensure all events are sent
        producer.flush()
        
        logger.info(f"Batch of {len(events)} events sent to Kafka")
        return {"status": "success", "count": len(events)}
    
    except Exception as e:
        logger.error(f"Failed to send batch events to Kafka: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send events: {str(e)}"
        )


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    if producer is not None:
        logger.info("Closing Kafka producer")
        producer.close()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)