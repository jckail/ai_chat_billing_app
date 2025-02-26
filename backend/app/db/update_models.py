"""Script to update model names in the database to ensure they have the correct date suffixes."""
import logging
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.dimensions import DimModel

logger = logging.getLogger(__name__)

def update_model_names():
    """Update any model names without date suffixes to include them."""
    logger.info("Checking and updating model names with date suffixes")
    
    db = SessionLocal()
    try:
        # Model name mappings (old name -> new name with date suffix)
        model_updates = {
            "claude-3-5-haiku": "claude-3-5-haiku-20241022",
            "claude-3-opus": "claude-3-7-opus-20250219",
            "claude-3-sonnet": "claude-3-7-sonnet-20250219"
        }
        
        updated = False
        
        # Find models that need updating
        for old_name, new_name in model_updates.items():
            model = db.query(DimModel).filter(DimModel.model_name == old_name).first()
            if model:
                logger.info(f"Updating model name from '{old_name}' to '{new_name}'")
                model.model_name = new_name
                updated = True
        
        if updated:
            db.commit()
            logger.info("Model names updated successfully")
        else:
            logger.info("No model names needed updating")
    
    except Exception as e:
        logger.error(f"Error updating model names: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    # Can be run as a standalone script
    update_model_names()