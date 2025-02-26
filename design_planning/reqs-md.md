# LLM Chat Billing System Requirements

## Project Overview

This project aims to create a proof-of-concept (POC) web application that integrates a real-time chat interface with a dynamic billing system for Large Language Model interactions. The system will track and display costs associated with each chat message and thread in real-time, while maintaining a comprehensive data model for billing and analytics purposes.

The application consists of two main components:
1. A single-page web application with chat interface and billing details using FastAPI and React
2. A near real-time analytics dashboard using Streamlit for cost metrics and user analytics

## Technology Stack

### Primary Application
- **Backend**: 
  - FastAPI with Pydantic for data validation
  - Anthropic Python SDK (default model: claude-3.5-haiku)
  - Apache Kafka for message streaming
- **Frontend**: 
  - React.js (single-page application)
- **Database & Caching**: 
  - SQLite (primary persistence)
  - Redis (caching and message queuing)
- **Deployment**: 
  - Docker containers orchestrated with Docker Compose

### Analytics Dashboard
- **Framework**: Streamlit
- **Data Source**: Redis cache with 15-second SLA for data freshness
- **Visualization**: Native Streamlit components plus optional libraries (Plotly, Matplotlib)

## Architecture Overview

```
User → React Frontend → FastAPI Backend → Anthropic API
                                      ↓
                                Apache Kafka
                                      ↓
                                 Redis Cache ← Streamlit Dashboard
                                      ↓
                                SQLite Database
```

- **Message Flow**: User messages are sent to the FastAPI backend, which forwards them to Anthropic API
- **Data Processing**: Responses and token metrics are published to Kafka topics
- **Data Storage**: Kafka consumers process messages and store in Redis cache before persisting to SQLite
- **Analytics**: Streamlit dashboard reads from Redis cache with a 15-second SLA for near real-time reporting

## Data Model

### Core Tables

1. **dim_users**
   - `user_id` (primary key)
   - `username`
   - `email`
   - `created_at`

2. **dim_models**
   - `model_id` (primary key)
   - `model_name` (e.g., "claude-3-5-haiku")
   - `description`
   - `is_active`

3. **dim_token_pricing** (SCD Type 2)
   - `pricing_id` (primary key)
   - `model_id` (foreign key to dim_models)
   - `input_token_price` (decimal)
   - `output_token_price` (decimal)
   - `effective_from` (datetime)
   - `effective_to` (datetime)
   - `is_current` (boolean)

4. **user_threads**
   - `thread_id` (primary key)
   - `user_id` (foreign key to dim_users)
   - `title`
   - `created_at`
   - `updated_at`
   - `model_id` (foreign key to dim_models)
   - `is_active`

5. **user_thread_messages**
   - `message_id` (primary key)
   - `thread_id` (foreign key to user_threads)
   - `user_id` (foreign key to dim_users)
   - `content`
   - `role` (user/assistant)
   - `created_at`
   - `model_id` (foreign key to dim_models)

6. **message_tokens**
   - `token_id` (primary key)
   - `message_id` (foreign key to user_thread_messages)
   - `token_type` (input/output)
   - `token_count`
   - `created_at`

7. **user_invoice_line_item**
   - `line_item_id` (primary key)
   - `message_id` (foreign key to user_thread_messages)
   - `token_id` (foreign key to message_tokens)
   - `pricing_id` (foreign key to dim_token_pricing)
   - `amount` (decimal)
   - `created_at`

8. **user_invoices**
   - `invoice_id` (primary key)
   - `user_id` (foreign key to dim_users)
   - `thread_id` (foreign key to user_threads)
   - `total_amount` (decimal)
   - `invoice_date`
   - `status` (pending/paid)

## Functional Requirements

### 1. Real-Time Chat Interface

- **Message Flow**:
  - Create new chat threads or join existing ones
  - Send messages processed in real-time by Anthropic API
  - Map each message to a specific chat thread

- **Cost & Billing Display**:
  - Show cumulative cost for entire thread alongside chat
  - Provide detailed breakdown per message:
    - Input tokens, output tokens, and other token types
    - Cost per token type based on current pricing
  - Update costs in real-time as messages are processed

- **User Identification**:
  - Simple form to input user ID (no authentication required for POC)
  - Associate users with their chat threads and billing

### 2. Backend Services & LLM Integration

- **Chat Messaging Service**:
  - FastAPI endpoints for thread and message management
  - Integration with Anthropic Python SDK (claude-3.5-haiku default)
  - Kafka producers to publish messages and metrics

- **Message Processing Pipeline**:
  - Kafka topics for raw messages, processed responses, and billing metrics
  - Consumers to handle data persistence and cache updates
  - Redis cache for fast access to recent messages and metrics

- **Billing Logic**:
  - Token counting for each message (input/output)
  - Cost calculation based on token pricing dimensions
  - Invoice generation at message and thread level

### 3. Streamlit Analytics Dashboard

- **Real-time Metrics Display**:
  - Cost metrics by user, thread, and time period
  - Token usage patterns and trends
  - Active users and threads

- **Performance Requirements**:
  - 15-second maximum SLA for data freshness
  - Automatic refresh of visualizations
  - Filter controls for different dimensions (time, user, model)

- **Integration**:
  - Read directly from Redis cache for performance
  - Fall back to SQLite for historical data

### 4. Frontend (React Single-Page Application)

- **Unified Dashboard**:
  - Persistent chat interface always visible
  - Tabbed interface for other features:
    - Thread management
    - Billing details
    - User settings
    - Data artifacts

- **Chat Components**:
  - Message input with send button
  - Message history display with typing indicators
  - Thread selection dropdown/sidebar
  - Real-time token count display

- **Billing Components**:
  - Thread cost summary panel
  - Message-level cost breakdown
  - Token usage visualization
  - Invoice generation controls

## Technical Implementation Details

### 1. Docker Configuration

- **Container Services**:
  - FastAPI backend container
  - React frontend container
  - Kafka and Zookeeper containers
  - Redis container
  - SQLite volume (or container with volume)
  - Streamlit dashboard container

- **Networking**:
  - Internal network for container communication
  - Exposed ports for web interfaces:
    - React app: 3000
    - FastAPI: 8000
    - Streamlit: 8501

### 2. Message Flow Implementation

- **Kafka Topics**:
  - `raw-messages`: User message input
  - `llm-responses`: Responses from Anthropic API
  - `token-metrics`: Token counts and billing metrics
  - `processed-messages`: Fully processed message pairs

- **Consumers and Producers**:
  - FastAPI endpoints produce to `raw-messages`
  - LLM service consumes from `raw-messages` and produces to `llm-responses`
  - Token counter consumes from `llm-responses` and produces to `token-metrics`
  - Database service consumes from multiple topics for persistence

### 3. Anthropic Integration

- **SDK Configuration**:
  - Use Python SDK with streaming responses
  - Configure claude-3.5-haiku as default model
  - Extract token counts from API responses

- **Token Extraction**:
  - Parse Anthropic API responses for token counts
  - Calculate costs based on current pricing dimension
  - Store token metrics in message_tokens table

### 4. Redis Caching Strategy

- **Cache Structure**:
  - Recent messages by thread
  - Token counts and costs by message
  - Aggregated metrics for dashboard
  - User thread summaries

- **TTL Policies**:
  - Short TTL for raw message data (1 hour)
  - Longer TTL for aggregated metrics (24 hours)
  - Permanent storage in SQLite

### 5. Streamlit Dashboard Implementation

- **Page Structure**:
  - Overview page with key metrics
  - User detail pages
  - Thread analysis pages
  - Cost projection tools

- **Data Refresh**:
  - Automatic refresh every 15 seconds to meet SLA
  - Manual refresh button
  - Historical data selection with date range picker

## Development Approach

1. **Setup & Infrastructure** (Week 1)
   - Configure Docker environment with all services
   - Set up Kafka, Redis, and SQLite
   - Establish communication between services

2. **Data Model Implementation** (Week 1-2)
   - Create SQLite schemas
   - Set up Redis data structures
   - Define Kafka topics and message formats

3. **Backend API Development** (Week 2-3)
   - Implement FastAPI endpoints
   - Integrate Anthropic SDK
   - Set up Kafka producers and consumers

4. **Frontend Development** (Week 3-4)
   - Create React components
   - Implement chat interface
   - Build billing display components

5. **Streamlit Dashboard** (Week 4)
   - Create dashboard pages
   - Implement metrics visualization
   - Configure Redis data source

6. **Integration & Testing** (Week 5)
   - End-to-end testing
   - Performance optimization
   - SLA verification for dashboard

7. **Documentation & Deployment** (Week 5)
   - Technical documentation
   - Deployment instructions
   - User guide

## Conclusion

This proof-of-concept system will demonstrate a comprehensive billing mechanism for LLM chat interactions, featuring real-time cost tracking and analytics. The application will provide valuable insights into token usage patterns and associated costs, serving as a foundation for a production-ready billing system for AI chat applications.
