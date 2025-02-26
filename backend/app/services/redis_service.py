import json
import logging
from typing import Dict, Any, List, Optional, Union, TypeVar
from datetime import datetime
import decimal
import redis.asyncio as redis
from pydantic import BaseModel
import asyncio

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar('T')

def json_serializer(obj):
    """Custom JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, decimal.Decimal):
        return float(obj)
    elif hasattr(obj, '__dict__'):
        return obj.__dict__
    elif hasattr(obj, 'dict') and callable(getattr(obj, 'dict')):
        return obj.dict()
    else:
        # Let the base class raise the TypeError
        raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')

class RedisService:
    """Service for interacting with Redis cache"""
    
    def __init__(self):
        self.redis_url = settings.REDIS_URL
        self.client = None
        self.prefix = "billing:"
        self.default_ttl = 3600  # Default TTL in seconds (1 hour)
        
        # TTL values for different types of data
        self.ttl_config = {
            "thread_messages": 3600 * 24,      # 24 hours
            "token_metrics": 3600 * 24 * 7,    # 7 days
            "user_metrics": 3600 * 24 * 7,     # 7 days
            "thread_metrics": 3600 * 24 * 7,   # 7 days
            "model_info": 3600 * 24 * 30,      # 30 days
        }
    
    async def initialize(self):
        """Initialize Redis connection"""
        if self.client is None:
            try:
                self.client = redis.Redis.from_url(self.redis_url, decode_responses=True)
                # Check connection
                await self.client.ping()
                logger.info(f"Redis client initialized with connection to {self.redis_url}")
            except Exception as e:
                logger.error(f"Failed to initialize Redis client: {str(e)}")
                self.client = None
    
    async def close(self):
        """Close Redis connection"""
        if self.client is not None:
            await self.client.close()
            self.client = None
    
    def _get_key(self, key_type: str, key_id: Union[str, int]) -> str:
        """Generate a Redis key with prefix"""
        return f"{self.prefix}{key_type}:{key_id}"
    
    async def set_value(self, key_type: str, key_id: Union[str, int], 
                        value: Union[str, dict, list, BaseModel], ttl: Optional[int] = None) -> bool:
        """
        Set a value in Redis
        
        Args:
            key_type: Type of data being stored (for prefix)
            key_id: Unique identifier
            value: Value to store (can be string, dict, list, or Pydantic model)
            ttl: Time-to-live in seconds, or None for default TTL
            
        Returns:
            bool: True if successful, False otherwise
        """
        if self.client is None:
            await self.initialize()
            if self.client is None:
                return False
        
        # Get the full Redis key
        key = self._get_key(key_type, key_id)
        
        # Process value
        if isinstance(value, BaseModel):
            value = value.dict()
        
        if isinstance(value, (dict, list)):
            value = json.dumps(value, default=json_serializer)
        
        # Determine TTL
        if ttl is None:
            ttl = self.ttl_config.get(key_type, self.default_ttl)
        
        try:
            await self.client.set(key, value, ex=ttl)
            return True
        except Exception as e:
            logger.error(f"Redis error setting {key}: {str(e)}")
            return False
    
    async def get_value(self, key_type: str, key_id: Union[str, int], 
                        as_json: bool = False) -> Optional[Union[str, dict, list]]:
        """
        Get a value from Redis
        
        Args:
            key_type: Type of data being retrieved (for prefix)
            key_id: Unique identifier
            as_json: Whether to parse the result as JSON
            
        Returns:
            The value, or None if not found or error
        """
        if self.client is None:
            await self.initialize()
            if self.client is None:
                return None
        
        # Get the full Redis key
        key = self._get_key(key_type, key_id)
        
        try:
            value = await self.client.get(key)
            
            if value is None:
                return None
            
            if as_json:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to decode JSON for {key}")
                    return value
            
            return value
        
        except Exception as e:
            logger.error(f"Redis error getting {key}: {str(e)}")
            return None
    
    async def delete_value(self, key_type: str, key_id: Union[str, int]) -> bool:
        """Delete a value from Redis"""
        if self.client is None:
            await self.initialize()
            if self.client is None:
                return False
        
        key = self._get_key(key_type, key_id)
        
        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis error deleting {key}: {str(e)}")
            return False
    
    async def cache_thread_messages(self, thread_id: int, messages: List[Dict[str, Any]]) -> bool:
        """Cache thread messages for quick access"""
        return await self.set_value(
            key_type="thread_messages",
            key_id=thread_id,
            value=messages,
            ttl=self.ttl_config["thread_messages"]
        )
    
    async def get_thread_messages(self, thread_id: int) -> Optional[List[Dict[str, Any]]]:
        """Get cached thread messages"""
        return await self.get_value(
            key_type="thread_messages",
            key_id=thread_id,
            as_json=True
        )
    
    async def cache_thread_metrics(self, thread_id: int, metrics: Dict[str, Any]) -> bool:
        """Cache thread billing metrics"""
        return await self.set_value(
            key_type="thread_metrics",
            key_id=thread_id,
            value=metrics,
            ttl=self.ttl_config["thread_metrics"]
        )
    
    async def get_thread_metrics(self, thread_id: int) -> Optional[Dict[str, Any]]:
        """Get cached thread metrics"""
        return await self.get_value(
            key_type="thread_metrics",
            key_id=thread_id,
            as_json=True
        )
    
    async def cache_user_metrics(self, user_id: int, metrics: List[Dict[str, Any]]) -> bool:
        """Cache user billing metrics"""
        return await self.set_value(
            key_type="user_metrics",
            key_id=user_id,
            value=metrics,
            ttl=self.ttl_config["user_metrics"]
        )
    
    async def get_user_metrics(self, user_id: int) -> Optional[List[Dict[str, Any]]]:
        """Get cached user metrics"""
        return await self.get_value(
            key_type="user_metrics",
            key_id=user_id,
            as_json=True
        )
    
    async def update_message_tokens(self, message_id: int, token_data: Dict[str, Any]) -> bool:
        """Update token count for a message"""
        return await self.set_value(
            key_type="message_tokens",
            key_id=message_id,
            value=token_data,
            ttl=self.ttl_config["token_metrics"]
        )

# Initialize a singleton instance
redis_service = RedisService()