import json
import logging
import asyncio
from typing import Dict, Any, List, Callable, Coroutine, Optional
from aiokafka import AIOKafkaConsumer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal

logger = logging.getLogger(__name__)

class KafkaConsumerService:
    """Service for consuming messages from Kafka topics"""
    
    def __init__(self):
        self.bootstrap_servers = settings.KAFKA_BOOTSTRAP_SERVERS
        self.topics = {
            "raw_messages": settings.KAFKA_RAW_MESSAGES_TOPIC,
            "llm_responses": settings.KAFKA_LLM_RESPONSES_TOPIC,
            "token_metrics": settings.KAFKA_TOKEN_METRICS_TOPIC,
            "inference_events": settings.KAFKA_INFERENCE_EVENTS_TOPIC,
            "processed_events": settings.KAFKA_PROCESSED_EVENTS_TOPIC
        }
        self.consumers = {}
        self.handlers = {}
        self.stop_event = asyncio.Event()
    
    async def initialize(self, topic_handlers: Dict[str, Callable]):
        """
        Initialize Kafka consumers for specified topics
        
        Args:
            topic_handlers: Dictionary mapping topic names to handler functions
        """
        self.handlers = topic_handlers
        
        # Create a consumer for each topic with a handler
        for topic_key, handler in topic_handlers.items():
            if topic_key in self.topics:
                topic = self.topics[topic_key]
                try:
                    consumer = AIOKafkaConsumer(
                        topic,
                        bootstrap_servers=self.bootstrap_servers,
                        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                        group_id=f"billing-{topic_key}-group",
                        auto_offset_reset="latest"
                    )
                    await consumer.start()
                    self.consumers[topic_key] = consumer
                    
                    # Start background task to process messages
                    asyncio.create_task(self._consume_messages(topic_key, consumer, handler))
                    
                    logger.info(f"Started consumer for topic: {topic}")
                except Exception as e:
                    logger.error(f"Failed to initialize consumer for topic {topic}: {str(e)}")
    
    async def close(self):
        """Stop all consumers and close connections"""
        self.stop_event.set()
        
        # Stop all consumers
        for topic_key, consumer in self.consumers.items():
            await consumer.stop()
            logger.info(f"Stopped consumer for topic: {self.topics[topic_key]}")
        
        self.consumers = {}
    
    async def _consume_messages(
        self, 
        topic_key: str, 
        consumer: AIOKafkaConsumer, 
        handler: Callable[[Dict[str, Any], Optional[Session]], Coroutine[Any, Any, None]]
    ):
        """
        Consume messages from a topic and process them with the handler
        
        Args:
            topic_key: Topic key from self.topics
            consumer: Kafka consumer instance
            handler: Async function to process messages
        """
        topic = self.topics[topic_key]
        
        try:
            # Continue consuming until stop_event is set
            while not self.stop_event.is_set():
                try:
                    # Try to fetch messages with timeout
                    async for msg in consumer:
                        if self.stop_event.is_set():
                            break
                        
                        try:
                            # Create database session
                            db = SessionLocal()
                            
                            # Process message with handler
                            await handler(msg.value, db)
                            
                            # Close session
                            db.close()
                        except Exception as e:
                            logger.error(f"Error processing message from {topic}: {str(e)}")
                
                except Exception as e:
                    if not self.stop_event.is_set():
                        logger.error(f"Consumer error for {topic}: {str(e)}")
                        # Wait a bit before retrying
                        await asyncio.sleep(5)
        
        except asyncio.CancelledError:
            logger.info(f"Consumption task for {topic} was cancelled")
        
        logger.info(f"Stopped consuming from {topic}")

# Initialize a singleton instance
kafka_consumer_service = KafkaConsumerService()