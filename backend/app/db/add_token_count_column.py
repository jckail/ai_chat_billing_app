"""Script to add token_count column to UserThreadMessage table."""
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, engine

logger = logging.getLogger(__name__)

def add_token_count_column():
    """Add token_count column to user_thread_messages table if it doesn't exist."""
    logger.info("Checking if token_count column exists in user_thread_messages table")
    
    db = SessionLocal()
    try:
        # Check if column exists
        # SQLite-compatible approach
        with engine.connect() as connection:
            result = connection.execute(text("PRAGMA table_info(user_thread_messages)"))
            columns = result.fetchall()
            column_exists = any(col[1] == 'token_count' for col in columns)
        
        if not column_exists:
            logger.info("Adding token_count column to user_thread_messages table")
            with engine.connect() as connection:
                connection.execute(text("""
                    ALTER TABLE user_thread_messages 
                    ADD COLUMN token_count INTEGER NULL
                """))
                connection.commit()
            logger.info("token_count column added successfully")
        else:
            logger.info("token_count column already exists")
            
        # Update token_count based on MessageToken records where possible
        logger.info("Updating token_count values from existing token records")
        
        # SQLite compatible approach for updating user messages
        db.execute(text("""
            UPDATE user_thread_messages
            SET token_count = (
                SELECT mt.token_count
                FROM message_tokens mt
                WHERE user_thread_messages.message_id = mt.message_id
                AND mt.token_type = 'input'
                AND user_thread_messages.role = 'user'
            )
            WHERE role = 'user'
            AND token_count IS NULL
            AND EXISTS (
                SELECT 1 FROM message_tokens mt 
                WHERE user_thread_messages.message_id = mt.message_id
                AND mt.token_type = 'input'
            )
        """))
        
        # SQLite compatible approach for updating assistant messages
        db.execute(text("""
            UPDATE user_thread_messages
            SET token_count = (
                SELECT mt.token_count
                FROM message_tokens mt
                WHERE user_thread_messages.message_id = mt.message_id
                AND mt.token_type = 'output'
                AND user_thread_messages.role = 'assistant'
            )
            WHERE role = 'assistant'
            AND token_count IS NULL
            AND EXISTS (
                SELECT 1 FROM message_tokens mt 
                WHERE user_thread_messages.message_id = mt.message_id
                AND mt.token_type = 'output'
            )
        """))
        
        # Commit the changes
        db.commit()
        logger.info("Existing token counts updated where available")
            
    except Exception as e:
        logger.error(f"Error adding token_count column: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    # Can be run as a standalone script
    add_token_count_column()