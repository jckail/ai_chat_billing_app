from sqlalchemy.orm import Session
from datetime import datetime

from app.db.database import SessionLocal
from app.models.dimensions import DimUser, DimModel, DimEventType, DimTokenPricing, DimResourcePricing
from app.core.config import settings


def init_models(db: Session):
    """Initialize model data"""
    # Check if models already exist
    existing_models = db.query(DimModel).count()
    if existing_models > 0:
        print("Models already initialized, skipping...")
        return
    
    # Add Claude 3.5 Haiku
    haiku = DimModel(
        model_name="claude-3-5-haiku",
        description="Fast and efficient model for chat and assistance",
        is_active=True
    )
    db.add(haiku)
    
    # Add Claude 3 Opus
    opus = DimModel(
        model_name="claude-3-opus",
        description="Most capable Claude model for complex tasks",
        is_active=True
    )
    db.add(opus)
    
    # Add Claude 3 Sonnet
    sonnet = DimModel(
        model_name="claude-3-sonnet",
        description="Balanced model for both performance and capability",
        is_active=True
    )
    db.add(sonnet)
    
    db.commit()
    print("Models initialized successfully")
    return {"haiku": haiku, "opus": opus, "sonnet": sonnet}


def init_pricing(db: Session, models):
    """Initialize pricing data"""
    # Check if pricing already exists
    existing_pricing = db.query(DimTokenPricing).count()
    if existing_pricing > 0:
        print("Pricing already initialized, skipping...")
        return
    
    # Add pricing for Claude 3.5 Haiku
    haiku_pricing = DimTokenPricing(
        model_id=models["haiku"].model_id,
        input_token_price=0.00000025,  # $0.25 per million tokens
        output_token_price=0.00000075,  # $0.75 per million tokens
        effective_from=datetime.utcnow(),
        is_current=True
    )
    db.add(haiku_pricing)
    
    # Add pricing for Claude 3 Opus
    opus_pricing = DimTokenPricing(
        model_id=models["opus"].model_id,
        input_token_price=0.000015,  # $15 per million tokens
        output_token_price=0.000075,  # $75 per million tokens
        effective_from=datetime.utcnow(),
        is_current=True
    )
    db.add(opus_pricing)
    
    # Add pricing for Claude 3 Sonnet
    sonnet_pricing = DimTokenPricing(
        model_id=models["sonnet"].model_id,
        input_token_price=0.000003,  # $3 per million tokens
        output_token_price=0.000015,  # $15 per million tokens
        effective_from=datetime.utcnow(),
        is_current=True
    )
    db.add(sonnet_pricing)
    
    db.commit()
    print("Pricing initialized successfully")


def init_event_types(db: Session):
    """Initialize event types"""
    # Check if event types already exist
    existing_types = db.query(DimEventType).count()
    if existing_types > 0:
        print("Event types already initialized, skipping...")
        return
    
    # Define event types
    event_types = [
        DimEventType(
            event_name="token_usage",
            description="Token usage for text generation",
            unit_of_measure="tokens",
            is_active=True
        ),
        DimEventType(
            event_name="image_generation",
            description="Image generation",
            unit_of_measure="images",
            is_active=True
        ),
        DimEventType(
            event_name="embedding",
            description="Text embedding generation",
            unit_of_measure="vectors",
            is_active=True
        )
    ]
    
    # Add all event types
    for event_type in event_types:
        db.add(event_type)
    
    db.commit()
    print("Event types initialized successfully")


def init_test_user(db: Session):
    """Create a test user"""
    # Check if test user already exists
    test_user = db.query(DimUser).filter(DimUser.username == "testuser").first()
    if test_user:
        print("Test user already exists, skipping...")
        return test_user
    
    # Create test user
    test_user = DimUser(
        username="testuser",
        email="test@example.com"
    )
    db.add(test_user)
    db.commit()
    db.refresh(test_user)
    print(f"Test user created with ID: {test_user.user_id}")
    return test_user


def init_db():
    """Initialize the database with seed data"""
    db = SessionLocal()
    try:
        print("Starting database initialization...")
        
        # Create models
        models = init_models(db)
        
        # Create pricing
        init_pricing(db, models)
        
        # Create event types
        init_event_types(db)
        
        # Create test user
        init_test_user(db)
        
        print("Database initialization completed successfully")
    
    except Exception as e:
        print(f"Error initializing database: {str(e)}")
    
    finally:
        db.close()


if __name__ == "__main__":
    init_db()