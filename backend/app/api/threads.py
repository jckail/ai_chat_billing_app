from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List

from app.db.database import get_db
from app.models.transactions import UserThread
from app.models.dimensions import DimUser, DimModel
from app.schemas.thread import ThreadCreate, ThreadResponse, ThreadUpdate

router = APIRouter()


@router.post("/", response_model=ThreadResponse, status_code=status.HTTP_201_CREATED)
def create_thread(thread: ThreadCreate, db: Session = Depends(get_db)):
    """Create a new thread"""
    # Check if user exists
    user = db.query(DimUser).filter(DimUser.user_id == thread.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Check if model exists
    model = db.query(DimModel).filter(DimModel.model_id == thread.model_id).first()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found"
        )
    
    # Create new thread
    db_thread = UserThread(
        user_id=thread.user_id,
        title=thread.title,
        model_id=thread.model_id
    )
    db.add(db_thread)
    db.commit()
    db.refresh(db_thread)
    return db_thread


@router.get("/", response_model=List[ThreadResponse])
def get_threads(user_id: int = None, skip: int = 0, limit: int = 100, 
               db: Session = Depends(get_db)):
    """Get a list of threads, optionally filtered by user"""
    query = db.query(UserThread)
    
    if user_id:
        query = query.filter(UserThread.user_id == user_id)
    
    threads = query.order_by(desc(UserThread.updated_at)).offset(skip).limit(limit).all()
    return threads


@router.get("/{thread_id}", response_model=ThreadResponse)
def get_thread(thread_id: int, db: Session = Depends(get_db)):
    """Get a specific thread by ID"""
    thread = db.query(UserThread).filter(UserThread.thread_id == thread_id).first()
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found"
        )
    return thread


@router.put("/{thread_id}", response_model=ThreadResponse)
def update_thread(thread_id: int, thread_update: ThreadUpdate, db: Session = Depends(get_db)):
    """Update thread properties"""
    db_thread = db.query(UserThread).filter(UserThread.thread_id == thread_id).first()
    if db_thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found"
        )
    
    # Update fields if provided
    update_data = thread_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_thread, key, value)
    
    db.commit()
    db.refresh(db_thread)
    return db_thread