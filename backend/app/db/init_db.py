import logging
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.db.database import SessionLocal
from app.models.dimensions import DimUser, DimModel, DimEventType, DimTokenPricing, DimResourcePricing
from app.core.config import settings

logger = logging.getLogger(__name__)

def init_db():
    """Initialize the database with seed data"""
    logger.info("Initializing database with seed data")
    
    db = SessionLocal()
    try:
        # Skip if data already exists
        if db.query(DimModel).count() > 0:
            logger.info("Database already contains seed data, skipping initialization")
            return
        
        # Create default models
        logger.info("Creating default models")
        models = [
            {
                "model_name": "claude-3-5-haiku-20241022",
                "description": "Anthropic's Claude 3.5 Haiku - fast and efficient model",
                "is_active": True
            },
            {
                "model_name": "claude-3-opus",
                "description": "Anthropic's Claude 3 Opus - high-performance model",
                "is_active": True
            },
            {
                "model_name": "claude-3-sonnet",
                "description": "Anthropic's Claude 3 Sonnet - balanced performance and cost",
                "is_active": True
            }
        ]
        
        model_map = {}  # Map model names to IDs
        
        for model_data in models:
            model = DimModel(**model_data)
            db.add(model)
            db.flush()  # Get the ID without committing
            model_map[model.model_name] = model.model_id
        
        # Create token pricing
        logger.info("Creating default token pricing")
        token_pricing = [
            {
                "model_id": model_map["claude-3-5-haiku-20241022"],
                "input_token_price": 0.00000025,  # $0.25 per million tokens
                "output_token_price": 0.00000075,  # $0.75 per million tokens
                "effective_from": datetime.now(timezone.utc),
                "is_current": True
            },
            {
                "model_id": model_map["claude-3-opus"],
                "input_token_price": 0.0000015,   # $1.50 per million tokens
                "output_token_price": 0.0000075,  # $7.50 per million tokens
                "effective_from": datetime.now(timezone.utc),
                "is_current": True
            },
            {
                "model_id": model_map["claude-3-sonnet"],
                "input_token_price": 0.00000075,  # $0.75 per million tokens
                "output_token_price": 0.0000035,  # $3.50 per million tokens
                "effective_from": datetime.now(timezone.utc),
                "is_current": True
            }
        ]
        
        for pricing_data in token_pricing:
            pricing = DimTokenPricing(**pricing_data)
            db.add(pricing)
        
        # Create event types
        logger.info("Creating default event types")
        event_types = [
            {
                "event_name": "image_generation",
                "description": "Generation of images",
                "unit_of_measure": "images",
                "is_active": True
            },
            {
                "event_name": "image_analysis",
                "description": "Analysis of images",
                "unit_of_measure": "pixels",
                "is_active": True
            },
            {
                "event_name": "audio_transcription",
                "description": "Transcription of audio to text",
                "unit_of_measure": "seconds",
                "is_active": True
            }
        ]
        
        event_type_map = {}  # Map event type names to IDs
        
        for event_type_data in event_types:
            event_type = DimEventType(**event_type_data)
            db.add(event_type)
            db.flush()  # Get the ID without committing
            event_type_map[event_type.event_name] = event_type.event_type_id
        
        # Create resource pricing
        logger.info("Creating default resource pricing")
        resource_pricing = [
            {
                "model_id": model_map["claude-3-5-haiku"],
                "event_type_id": event_type_map["image_analysis"],
                "unit_price": 0.00001,  # $0.01 per 1000 pixels
                "effective_from": datetime.now(timezone.utc),
                "is_current": True
            },
            {
                "model_id": model_map["claude-3-opus"],
                "event_type_id": event_type_map["image_analysis"],
                "unit_price": 0.00002,  # $0.02 per 1000 pixels
                "effective_from": datetime.now(timezone.utc),
                "is_current": True
            },
            {
                "model_id": model_map["claude-3-opus"],
                "event_type_id": event_type_map["image_generation"],
                "unit_price": 0.02,     # $0.02 per image
                "effective_from": datetime.now(timezone.utc),
                "is_current": True
            },
            {
                "model_id": model_map["claude-3-sonnet"],
                "event_type_id": event_type_map["audio_transcription"],
                "unit_price": 0.0001,   # $0.10 per 1000 seconds
                "effective_from": datetime.now(timezone.utc),
                "is_current": True
            }
        ]
        
        for pricing_data in resource_pricing:
            pricing = DimResourcePricing(**pricing_data)
            db.add(pricing)
        
        # Create test user
        logger.info("Creating test user")
        test_user = DimUser(
            username="testuser",
            email="test@example.com"
        )
        db.add(test_user)
        
        # Commit all changes
        db.commit()
        logger.info("Database initialization completed successfully")
    
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    # Can be run as a standalone script
    init_db()