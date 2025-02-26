"""WebSocket router for real-time AI chat interactions."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, List, Optional, AsyncGenerator
from datetime import datetime, timezone
import json
import logging
import asyncio
from uuid import uuid4

from app.db.database import get_db
from sqlalchemy.orm import Session
from app.models.transactions import UserThread, UserThreadMessage
from app.models.dimensions import DimUser, DimModel
from app.services.anthropic_service import anthropic_service
import traceback

logger = logging.getLogger(__name__)

router = APIRouter()

# Connection manager to track active WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_details: Dict[str, Dict] = {}
        
    async def connect(self, websocket: WebSocket, client_id: str, user_id: int, thread_id: int):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.connection_details[client_id] = {
            "user_id": user_id,
            "thread_id": thread_id,
            "connected_at": datetime.now(timezone.utc).isoformat()
        }
        logger.info(f"WebSocket connection established - client_id: {client_id}")
        
    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.connection_details:
            del self.connection_details[client_id]
        logger.info(f"WebSocket connection removed - client_id: {client_id}")

    async def send_text(self, client_id: str, message: str):
        if client_id in self.active_connections:
            websocket = self.active_connections[client_id]
            await websocket.send_text(message)
            
    async def send_json(self, client_id: str, data: dict):
        if client_id in self.active_connections:
            websocket = self.active_connections[client_id]
            await websocket.send_json(data)

# Initialize connection manager
manager = ConnectionManager()

# Helper function to fetch thread history
async def get_thread_messages(db: Session, thread_id: int) -> List[dict]:
    """Get chat history for a specific thread"""
    messages = db.query(UserThreadMessage).filter(
        UserThreadMessage.thread_id == thread_id
    ).order_by(UserThreadMessage.created_at).all()
    
    formatted_messages = []
    for msg in messages:
        formatted_messages.append({
            "id": msg.message_id,
            "role": msg.role,
            "content": msg.content,
            "timestamp": msg.created_at.isoformat(),
            "user_id": msg.user_id
        })
    return formatted_messages

# Handle user chat messages
async def handle_chat_message(
    client_id: str,
    message: str,
    user_id: int,
    thread_id: int,
    model_id: int,
    db: Session
) -> None:
    """Process chat messages and stream responses"""
    try:
        # Get thread from database
        thread = db.query(UserThread).filter(UserThread.thread_id == thread_id).first()
        if not thread:
            await manager.send_json(client_id, {
                "type": "ERROR",
                "error": "Thread not found",
                "status_code": 404
            })
            return
            
        # Create user message in the database
        user_message = UserThreadMessage(
            thread_id=thread_id,
            user_id=user_id,
            content=message,
            role="user",
            model_id=model_id
        )
        db.add(user_message)
        db.commit()
        db.refresh(user_message)
        
        # Update thread's updated_at timestamp
        thread.updated_at = datetime.now(timezone.utc)
        db.commit()
        
        # Send confirmation of user message
        await manager.send_json(client_id, {
            "type": "MESSAGE_SENT",
            "message": {
                "id": user_message.message_id,
                "role": "user",
                "content": message,
                "timestamp": user_message.created_at.isoformat(),
                "thread_id": thread_id,
                "user_id": user_id
            }
        })
        
        # Get chat history to provide context
        previous_messages = db.query(UserThreadMessage).filter(
            UserThreadMessage.thread_id == thread_id
        ).order_by(UserThreadMessage.created_at).limit(10).all()
        
        # Format messages for Anthropic API
        formatted_messages = []
        for prev_msg in previous_messages:
            formatted_messages.append({
                "role": prev_msg.role,
                "content": prev_msg.content
            })
            
        # Create a placeholder assistant message to update during streaming
        assistant_message = UserThreadMessage(
            thread_id=thread_id,
            user_id=user_id,
            content="",  # Will be updated with full content after streaming
            role="assistant",
            model_id=model_id
        )
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)
        
        # Initialize streaming response
        full_response = ""
        
        # Start response streaming
        await manager.send_json(client_id, {
            "type": "ASSISTANT_TYPING",
            "message_id": assistant_message.message_id
        })
        
        # Process through anthropic service
        try:
            # Get model name
            model = db.query(DimModel).filter(DimModel.model_id == model_id).first()
            model_name = "claude-3-5-haiku-20241022"  # Default model
            if model:
                model_name = model.model_name
            
            async for chunk in anthropic_service.stream_chat_completion(
                messages=formatted_messages,
                model=model_name
            ):
                # Add to full response
                if "content" in chunk and chunk["content"]:
                    full_response += chunk["content"]
                    
                    # Send chunk to client
                    await manager.send_json(client_id, {
                        "type": "ASSISTANT_CHUNK",
                        "message_id": assistant_message.message_id,
                        "chunk": chunk["content"],
                        "token_count": chunk["token_usage"]["output_tokens"]
                    })
                    await asyncio.sleep(0)  # Allow cancellation points
                
            # Update the assistant message with full content
            assistant_message.content = full_response
            db.commit()
            
            # Send completion notification
            await manager.send_json(client_id, {
                "type": "ASSISTANT_COMPLETE",
                "message": {
                    "id": assistant_message.message_id,
                    "role": "assistant",
                    "content": full_response,
                    "timestamp": assistant_message.created_at.isoformat(),
                    "thread_id": thread_id,
                    "user_id": user_id
                }
            })
            
        except Exception as streaming_error:
            logger.error(f"Error streaming response: {str(streaming_error)}")
            logger.error(traceback.format_exc())
            
            await manager.send_json(client_id, {
                "type": "ASSISTANT_CHUNK", 
                "message_id": assistant_message.message_id,
                "chunk": f"Anthropic API Error: {str(streaming_error)}", "token_count": 0
            })
            
            # Also send completion to ensure frontend handles it properly
            await manager.send_json(client_id, {
                "type": "ASSISTANT_COMPLETE",
                "message": {
                    "id": assistant_message.message_id,
                    "role": "assistant",
                    "content": f"Anthropic API Error: {str(streaming_error)}",
                    "timestamp": assistant_message.created_at.isoformat(),
                    "thread_id": thread_id,
                    "user_id": user_id
                }
            })
    except Exception as e:
        logger.error(f"Error processing chat message: {str(e)}")
        await manager.send_json(client_id, {
            "type": "ERROR",
            "error": "Failed to process message",
            "status_code": 500
        })

# Handle ping/pong for connection healthcheck
async def handle_ping(client_id: str, timestamp: str) -> None:
    """Respond to ping with pong"""
    try:
        pong_response = {
            "type": "PONG",
            "timestamp": timestamp,
            "server_time": datetime.now(timezone.utc).isoformat()
        }
        await manager.send_json(client_id, pong_response)
    except Exception as e:
        logger.error(f"Error handling ping: {str(e)}")

# Message router function
async def message_router(
    websocket: WebSocket,
    client_id: str,
    user_id: int,
    thread_id: int,
    db: Session
) -> None:
    """Route incoming WebSocket messages to appropriate handlers"""
    try:
        while True:
            # Get message from WebSocket
            message = await websocket.receive_text()
            logger.debug(f"Received message: {message}")
            
            try:
                # Parse as JSON
                data = json.loads(message)
                
                # Check message structure
                if not isinstance(data, dict) or "type" not in data:
                    logger.warning(f"Invalid message format from client {client_id}")
                    await manager.send_json(client_id, {
                        "type": "ERROR",
                        "error": "Invalid message format",
                        "status_code": 400
                    })
                    continue
                
                # Route by message type
                if data["type"] == "PING":
                    await handle_ping(client_id, data.get("timestamp", datetime.now(timezone.utc).isoformat()))
                
                elif data["type"] == "CHAT":
                    if "message" not in data:
                        await manager.send_json(client_id, {
                            "type": "ERROR",
                            "error": "Message content required",
                            "status_code": 400
                        })
                        continue
                    
                    model_id = data.get("model_id", 1)  # Default to model_id 1 if not specified
                    
                    await handle_chat_message(
                        client_id=client_id,
                        message=data["message"],
                        user_id=user_id,
                        thread_id=thread_id,
                        model_id=model_id,
                        db=db
                    )
                
                else:
                    logger.warning(f"Unknown message type: {data['type']}")
                    await manager.send_json(client_id, {
                        "type": "ERROR",
                        "error": f"Unknown message type: {data['type']}",
                        "status_code": 400
                    })
            
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from client {client_id}")
                await manager.send_json(client_id, {
                    "type": "ERROR",
                    "error": "Invalid JSON",
                    "status_code": 400
                })
    
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logger.info(f"WebSocket disconnect: {client_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        manager.disconnect(client_id)

# WebSocket endpoint for thread chat
@router.websocket("/chat/{user_id}/{thread_id}")
async def websocket_chat(
    websocket: WebSocket,
    user_id: int,
    thread_id: int,
    db: Session = Depends(get_db)
):
    """WebSocket endpoint for real-time chat"""
    # Generate unique client ID
    client_id = f"chat_{user_id}_{thread_id}_{uuid4().hex[:8]}"
    
    try:
        # Check if thread exists
        thread = db.query(UserThread).filter(UserThread.thread_id == thread_id).first()
        if not thread:
            await websocket.close(code=1008, reason="Thread not found")
            return
        
        # Check if user exists
        user = db.query(DimUser).filter(DimUser.user_id == user_id).first()
        if not user:
            await websocket.close(code=1008, reason="User not found")
            return
            
        # Accept connection and track in manager
        await manager.connect(websocket, client_id, user_id, thread_id)
        
        # Send thread info and chat history
        thread_messages = await get_thread_messages(db, thread_id)
        await manager.send_json(client_id, {
            "type": "THREAD_CONNECTED",
            "thread_id": thread_id,
            "history": thread_messages
        })
        
        # Process messages until disconnection
        await message_router(websocket, client_id, user_id, thread_id, db)
        
    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {str(e)}")
        try:
            await websocket.close(code=1011, reason=f"Server error: {str(e)}")
        except:
            pass
        manager.disconnect(client_id)