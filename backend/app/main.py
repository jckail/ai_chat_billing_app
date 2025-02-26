from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.db.database import engine, get_db
from app.models import dimensions, transactions  # Import models to create tables
from app.db.init_db import init_db
from app.api import users, threads, messages, billing

def setup_database():
    """Create tables and initialize with seed data"""
    print("Setting up database...")
    
    # Create all tables
    dimensions.Base.metadata.create_all(bind=engine)
    transactions.Base.metadata.create_all(bind=engine)
    
    # Initialize seed data
    init_db()

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