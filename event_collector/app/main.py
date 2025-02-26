import os
import json
import logging
import asyncio
from fastapi import FastAPI, Request, BackgroundTasks, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime
import httpx
import uvicorn
from aiokafka import AIOKafkaProducer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment variables
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_INFERENCE_EVENTS_TOPIC = os.getenv("KAFKA_INFERENCE_EVENTS_TOPIC", "inference-events")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))
BATCH_INTERVAL_SECONDS = int(os.getenv("BATCH_INTERVAL_SECONDS", "5"))

# Create FastAPI app
app = FastAPI(
    title="Event Collector Service",
    description="Service for collecting inference API events",
    version="0.1.0"
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class APIEvent(BaseModel):
    """API event model for receiving events"""
    event_type: str
    model_id: int
    user_id: int
    message_id: Optional[int] = None
    quantity: float
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[datetime] = None

# Global state
event_queue = []
kafka_producer = None
queue_lock = asyncio.Lock()

async def get_kafka_producer():
    """Get or create Kafka producer"""
    global kafka_producer
    if kafka_producer is None:
        try:
            producer = AIOKafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            await producer.start()
            kafka_producer = producer
            logger.info(f"Kafka producer initialized with bootstrap servers: {KAFKA_BOOTSTRAP_SERVERS}")
        except Exception as e:
            logger.error(f"Failed to initialize Kafka producer: {str(e)}")
            kafka_producer = None
    
    return kafka_producer

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    # Start batch processing task
    asyncio.create_task(process_event_batches())
    logger.info("Event batch processing started")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    global kafka_producer
    if kafka_producer:
        await kafka_producer.stop()
        kafka_producer = None
        logger.info("Kafka producer stopped")

async def process_event_batches():
    """Process events in batches periodically"""
    while True:
        try:
            await asyncio.sleep(BATCH_INTERVAL_SECONDS)
            
            # Get batch of events to process
            async with queue_lock:
                if not event_queue:
                    continue
                
                # Take up to BATCH_SIZE events
                batch = event_queue[:BATCH_SIZE]
                # Remove processed events from queue
                event_queue[:] = event_queue[BATCH_SIZE:]
            
            # Process batch
            if batch:
                await process_batch(batch)
        
        except Exception as e:
            logger.error(f"Error in batch processing: {str(e)}")

async def process_batch(events: List[Dict[str, Any]]):
    """Process a batch of events"""
    producer = await get_kafka_producer()
    if not producer:
        logger.warning(f"No Kafka producer available, dropping {len(events)} events")
        return
    
    try:
        # Send each event to Kafka
        for event in events:
            # Ensure event has timestamp
            if "timestamp" not in event:
                event["timestamp"] = datetime.now().isoformat()
                
            await producer.send_and_wait(
                KAFKA_INFERENCE_EVENTS_TOPIC,
                event
            )
        
        logger.info(f"Processed batch of {len(events)} events")
    
    except Exception as e:
        logger.error(f"Failed to send batch to Kafka: {str(e)}")

@app.post("/events")
async def receive_event(event: APIEvent, background_tasks: BackgroundTasks):
    """
    Receive an inference API event
    
    This endpoint accepts events from the API and queues them for processing
    """
    # Set timestamp if not provided
    if not event.timestamp:
        event.timestamp = datetime.now()
    
    # Convert to dict for queue
    event_dict = event.dict()
    
    # Add to queue
    async with queue_lock:
        event_queue.append(event_dict)
    
    return {"status": "accepted", "queued_events": len(event_queue)}

@app.post("/events/batch")
async def receive_event_batch(events: List[APIEvent], background_tasks: BackgroundTasks):
    """
    Receive a batch of inference API events
    
    This endpoint accepts multiple events in a single request
    """
    # Set timestamps and convert to dicts
    event_dicts = []
    for event in events:
        if not event.timestamp:
            event.timestamp = datetime.now()
        event_dicts.append(event.dict())
    
    # Add to queue
    async with queue_lock:
        event_queue.extend(event_dicts)
    
    return {"status": "accepted", "queued_events": len(event_queue)}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    producer = await get_kafka_producer()
    
    return {
        "status": "healthy",
        "kafka_connected": producer is not None,
        "queued_events": len(event_queue)
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)