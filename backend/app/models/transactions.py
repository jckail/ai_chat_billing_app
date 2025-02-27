from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class UserThread(Base):
    """User thread model for chat conversations"""
    __tablename__ = "user_threads"
    
    thread_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("dim_users.user_id"), index=True)
    title = Column(String, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    model_id = Column(Integer, ForeignKey("dim_models.model_id"), index=True)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    user = relationship("DimUser", back_populates="threads")
    model = relationship("DimModel", back_populates="threads")
    messages = relationship("UserThreadMessage", back_populates="thread")
    invoices = relationship("UserInvoice", back_populates="thread")


class UserThreadMessage(Base):
    """Messages within a user thread"""
    __tablename__ = "user_thread_messages"
    
    message_id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey("user_threads.thread_id"), index=True)
    user_id = Column(Integer, ForeignKey("dim_users.user_id"), index=True)
    content = Column(Text)
    role = Column(String)  # 'user' or 'assistant'
    created_at = Column(DateTime, default=func.now())
    model_id = Column(Integer, ForeignKey("dim_models.model_id"), index=True)
    token_count = Column(Integer, nullable=True)  # Added for easier token display in UI
    
    # Relationships
    thread = relationship("UserThread", back_populates="messages")
    user = relationship("DimUser", back_populates="messages")
    model = relationship("DimModel", back_populates="messages")
    tokens = relationship("MessageToken", back_populates="message")
    invoice_line_items = relationship("UserInvoiceLineItem", back_populates="message")
    api_events = relationship("ApiEvent", back_populates="message")


class MessageToken(Base):
    """Token usage for messages"""
    __tablename__ = "message_tokens"
    
    token_id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("user_thread_messages.message_id"), index=True)
    token_type = Column(String)  # 'input' or 'output'
    token_count = Column(Integer)
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    message = relationship("UserThreadMessage", back_populates="tokens")
    invoice_line_items = relationship("UserInvoiceLineItem", back_populates="token")


class ApiEvent(Base):
    """API events for billing and tracking"""
    __tablename__ = "api_events"
    
    event_id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("user_thread_messages.message_id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("dim_users.user_id"), index=True)
    event_type_id = Column(Integer, ForeignKey("dim_event_types.event_type_id"), index=True)
    model_id = Column(Integer, ForeignKey("dim_models.model_id"), index=True)
    quantity = Column(Float)
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    message = relationship("UserThreadMessage", back_populates="api_events")
    user = relationship("DimUser", back_populates="api_events")
    event_type = relationship("DimEventType", back_populates="api_events")
    model = relationship("DimModel", back_populates="api_events")
    resource_invoice_items = relationship("ResourceInvoiceLineItem", back_populates="event")


class UserInvoice(Base):
    """User invoice for billing"""
    __tablename__ = "user_invoices"
    
    invoice_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("dim_users.user_id"), index=True)
    thread_id = Column(Integer, ForeignKey("user_threads.thread_id"), index=True)
    total_amount = Column(Float)
    invoice_date = Column(DateTime, default=func.now())
    status = Column(String, default="pending")  # 'pending' or 'paid'
    
    # Relationships
    user = relationship("DimUser", back_populates="invoices")
    thread = relationship("UserThread", back_populates="invoices")


class UserInvoiceLineItem(Base):
    """Line items for token-based billing"""
    __tablename__ = "user_invoice_line_item"
    
    line_item_id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("user_thread_messages.message_id"), index=True)
    token_id = Column(Integer, ForeignKey("message_tokens.token_id"), index=True)
    pricing_id = Column(Integer, ForeignKey("dim_token_pricing.pricing_id"), index=True)
    amount = Column(Float)
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    message = relationship("UserThreadMessage", back_populates="invoice_line_items")
    token = relationship("MessageToken", back_populates="invoice_line_items")
    pricing = relationship("DimTokenPricing", back_populates="invoice_line_items")


class ResourceInvoiceLineItem(Base):
    """Line items for resource-based billing"""
    __tablename__ = "resource_invoice_line_item"
    
    resource_line_item_id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("api_events.event_id"), index=True)
    user_id = Column(Integer, ForeignKey("dim_users.user_id"), index=True)
    resource_pricing_id = Column(Integer, ForeignKey("dim_resource_pricing.resource_pricing_id"), index=True)
    quantity = Column(Float)
    amount = Column(Float)
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    event = relationship("ApiEvent", back_populates="resource_invoice_items")
    resource_pricing = relationship("DimResourcePricing", back_populates="resource_invoice_items")