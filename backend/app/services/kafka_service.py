import json
import logging
from typing import Dict, Any, List, Optional
from aiokafka import AIOKafkaProducer
import asyncio

from app.core.config import settings

logger = logging.getLogger(__name__)

class KafkaService:
    """Service for interacting with Kafka"""
    
    def __init__(self):
        self.producer = None
        self.bootstrap_servers = settings.KAFKA_BOOTSTRAP_SERVERS
        self.topics = {
            "raw_messages": settings.KAFKA_RAW_MESSAGES_TOPIC,
            "llm_responses": settings.KAFKA_LLM_RESPONSES_TOPIC,
            "token_metrics": settings.KAFKA_TOKEN_METRICS_TOPIC,
            "inference_events": settings.KAFKA_INFERENCE_EVENTS_TOPIC,
            "processed_events": settings.KAFKA_PROCESSED_EVENTS_TOPIC
        }
    
    async def initialize(self):
        """Initialize the Kafka producer"""
        if self.producer is None:
            try:
                self.producer = AIOKafkaProducer(
                    bootstrap_servers=self.bootstrap_servers,
                    value_serializer=lambda v: json.dumps(v).encode('utf-8')
                )
                await self.producer.start()
                logger.info(f"Kafka producer initialized with bootstrap servers: {self.bootstrap_servers}")
            except Exception as e:
                logger.error(f"Failed to initialize Kafka producer: {str(e)}")
                # Allow service to function without Kafka for development
                self.producer = None
    
    async def close(self):
        """Close the Kafka producer"""
        if self.producer is not None:
            await self.producer.stop()
            self.producer = None
    
    async def publish_raw_message(self, message_data: Dict[str, Any]):
        """Publish a raw user message to Kafka"""
        return await self._publish_message(
            topic=self.topics["raw_messages"],
            data=message_data
        )
    
    async def publish_llm_response(self, response_data: Dict[str, Any]):
        """Publish an LLM response to Kafka"""
        return await self._publish_message(
            topic=self.topics["llm_responses"],
            data=response_data
        )
    
    async def publish_token_metrics(self, metrics_data: Dict[str, Any]):
        """Publish token usage metrics to Kafka"""
        return await self._publish_message(
            topic=self.topics["token_metrics"],
            data=metrics_data
        )
    
    async def publish_inference_event(self, event_data: Dict[str, Any]):
        """Publish an inference API event to Kafka"""
        return await self._publish_message(
            topic=self.topics["inference_events"],
            data=event_data
        )
    
    async def _publish_message(self, topic: str, data: Dict[str, Any]) -> bool:
        """
        Publish a message to a Kafka topic
        
        Args:
            topic: Kafka topic name
            data: Message data as dictionary
            
        Returns:
            bool: True if successful, False otherwise
        """
        if self.producer is None:
            try:
                await self.initialize()
            except Exception as e:
                logger.error(f"Failed to initialize Kafka producer: {str(e)}")
                return False
        
        try:
            if self.producer is not None:
                # Add timestamp to data
                data["timestamp"] = asyncio.get_event_loop().time()
                
                # Send message to Kafka
                await self.producer.send_and_wait(topic, data)
                logger.debug(f"Published message to {topic}")
                return True
            else:
                # Log message content when Kafka is not available
                logger.info(f"Would publish to {topic}: {data}")
                return False
        except Exception as e:
            logger.error(f"Failed to publish message to {topic}: {str(e)}")
            return False

# Initialize a singleton instance
kafka_service = KafkaService()