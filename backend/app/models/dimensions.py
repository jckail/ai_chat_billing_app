from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base

class DimUser(Base):
    """User dimension table"""
    __tablename__ = "dim_users"
    
    user_id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    threads = relationship("UserThread", back_populates="user")
    messages = relationship("UserThreadMessage", back_populates="user")
    invoices = relationship("UserInvoice", back_populates="user")
    api_events = relationship("ApiEvent", back_populates="user")


class DimModel(Base):
    """AI Model dimension table"""
    __tablename__ = "dim_models"
    
    model_id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String, unique=True, index=True)
    description = Column(String)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    token_prices = relationship("DimTokenPricing", back_populates="model")
    resource_prices = relationship("DimResourcePricing", back_populates="model")
    threads = relationship("UserThread", back_populates="model")
    messages = relationship("UserThreadMessage", back_populates="model")
    api_events = relationship("ApiEvent", back_populates="model")


class DimEventType(Base):
    """Event types dimension table"""
    __tablename__ = "dim_event_types"
    
    event_type_id = Column(Integer, primary_key=True, index=True)
    event_name = Column(String, unique=True, index=True)
    description = Column(String)
    unit_of_measure = Column(String)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    resource_prices = relationship("DimResourcePricing", back_populates="event_type")
    api_events = relationship("ApiEvent", back_populates="event_type")


class DimTokenPricing(Base):
    """Token pricing dimension table (SCD Type 2)"""
    __tablename__ = "dim_token_pricing"
    
    pricing_id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("dim_models.model_id"), index=True)
    input_token_price = Column(Float)
    output_token_price = Column(Float)
    effective_from = Column(DateTime, default=func.now())
    effective_to = Column(DateTime, nullable=True)
    is_current = Column(Boolean, default=True)
    
    # Relationships
    model = relationship("DimModel", back_populates="token_prices")
    invoice_line_items = relationship("UserInvoiceLineItem", back_populates="pricing")


class DimResourcePricing(Base):
    """Resource pricing dimension table (SCD Type 2)"""
    __tablename__ = "dim_resource_pricing"
    
    resource_pricing_id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("dim_models.model_id"), index=True)
    event_type_id = Column(Integer, ForeignKey("dim_event_types.event_type_id"), index=True)
    unit_price = Column(Float)
    effective_from = Column(DateTime, default=func.now())
    effective_to = Column(DateTime, nullable=True)
    is_current = Column(Boolean, default=True)
    
    # Relationships
    model = relationship("DimModel", back_populates="resource_prices")
    event_type = relationship("DimEventType", back_populates="resource_prices")
    resource_invoice_items = relationship("ResourceInvoiceLineItem", back_populates="resource_pricing")