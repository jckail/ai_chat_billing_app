import os
from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings"""
    
    # API Settings
    API_V1_PREFIX: str = "/api"
    PROJECT_NAME: str = "AI Thread Billing"
    DEBUG: bool = Field(default=False, env="DEBUG")
    
    # Database Settings
    DATABASE_URL: str = Field(
        default="sqlite:///data/billing.db", 
        env="DATABASE_URL"
    )
    
    # Redis Settings
    REDIS_URL: str = Field(
        default="redis://redis:6379/0",
        env="REDIS_URL"
    )
    
    # Kafka Settings
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="kafka:9092",
        env="KAFKA_BOOTSTRAP_SERVERS"
    )
    
    # Anthropic API Settings
    ANTHROPIC_API_KEY: str = Field(
        default="",
        env="ANTHROPIC_API_KEY"
    )
    DEFAULT_MODEL: str = "claude-3-5-haiku-20241022"
    
    # Default token pricing
    DEFAULT_INPUT_TOKEN_PRICE: float = Field(
        default=0.000001,  # $1.00 per million tokens
        env="DEFAULT_INPUT_TOKEN_PRICE"
    )
    DEFAULT_OUTPUT_TOKEN_PRICE: float = Field(
        default=0.000005,  # $5.00 per million tokens
        env="DEFAULT_OUTPUT_TOKEN_PRICE"
    )
    
    # Kafka Topics
    KAFKA_RAW_MESSAGES_TOPIC: str = "raw-messages"
    KAFKA_LLM_RESPONSES_TOPIC: str = "llm-responses"
    KAFKA_TOKEN_METRICS_TOPIC: str = "token-metrics"
    KAFKA_INFERENCE_EVENTS_TOPIC: str = "inference-events"
    KAFKA_PROCESSED_EVENTS_TOPIC: str = "processed-events"
    
    class Config:
        case_sensitive = True
        env_file = ".env"


# Create settings instance
settings = Settings()