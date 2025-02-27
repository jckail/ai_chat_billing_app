from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.db.database import engine, get_db
from app.models import dimensions, transactions  # Import models to create tables
from app.db.init_db import init_db
from app.db.update_models import update_model_names
from app.db.add_token_count_column import add_token_count_column
from app.api import users, threads, messages, billing, websockets
from app.services.message_processor import initialize_message_processors, shutdown_message_processors
import logging

def setup_database():
    """Create tables and initialize with seed data"""
    print("Setting up database...")
    
    # Create all tables
    dimensions.Base.metadata.create_all(bind=engine)
    transactions.Base.metadata.create_all(bind=engine)
    
    # Initialize seed data
    init_db()

    # Update model names to ensure correct date suffixes
    update_model_names()

    # Add token_count column to UserThreadMessage table if it doesn't exist
    add_token_count_column()

# Initialize FastAPI app
app = FastAPI(
    title="AI Thread Billing API",
    description="API for tracking and billing AI chat thread interactions",
    version="0.1.0"
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development only, restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up database on startup
setup_database()

# Include API routers
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(threads.router, prefix="/api/threads", tags=["threads"])
app.include_router(messages.router, prefix="/api/messages", tags=["messages"])
app.include_router(billing.router, prefix="/api/billing", tags=["billing"])
app.include_router(websockets.router, prefix="/ws", tags=["websockets"])

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

@app.on_event("startup")
async def startup_event():
    """Initialize Kafka message processors on startup"""
    await initialize_message_processors()

@app.on_event("shutdown")
async def shutdown_event():
    """Shut down Kafka message processors on shutdown"""
    await shutdown_message_processors()

@app.get("/")
def read_root():
    return {"message": "Welcome to AI Thread Billing API"}

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint to verify API is running and connected to DB"""
    try:
        # Test database connection
        db.execute("SELECT 1")
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return {
        "status": "healthy",
        "database": db_status
    }