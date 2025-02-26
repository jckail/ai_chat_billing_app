# LLM Chat Billing Proof of Concept Requirements

## 1. Project Overview

This project is a proof-of-concept (POC) web application that integrates a real-time chat interface with a dynamic billing system for LLM (Anthropic's claude3.5-haiku) interactions. The application will provide real-time cost breakdowns for each chat thread and message while also displaying detailed token usage and pricing metrics. Additionally, a separate Streamlit-based dashboard will offer near real-time (15-second SLA) insights into cost metrics and overall system performance.

## 2. Technology Stack

- **Backend:**  
  - FastAPI with Pydantic for data validation and API endpoints  
  - Anthropic Python SDK (default model: claude3.5-haiku)
  - Apache Kafka for message queuing to handle high throughput

- **Database & Caching:**  
  - SQLite for primary data persistence  
  - Redis for caching and real-time data serving

- **Frontend:**  
  - React.js for a single-page application (SPA) that hosts the chat interface and data artifacts  
  - Streamlit for a separate dashboard displaying cost and usage metrics in near real time

- **Containerization & Orchestration:**  
  - Docker (with Docker Compose) to containerize the FastAPI, React, Redis, and Kafka components

## 3. Functional Requirements

### 3.1. Chat Interface & Messaging

- **Message Flow:**
  - Users can create a new chat thread or rejoin an existing thread.
  - Users send messages in real time, with each message mapped to a specific chat thread.
  - Messages are routed through Apache Kafka to a Redis cache, which then stores them into SQLite, allowing scalability for higher message volumes.
  - The system captures events from the Inference API for every API call, including model used, input/output tokens, and any generated pixels or images.

- **Real-Time Cost & Billing Display:**
  - Next to the chat interface, display the cumulative cost for the entire thread.
  - Provide a detailed cost breakdown per message, including:
    - Total tokens used (input, output, etc.)
    - Cost invoiced per token type
    - Resource usage metrics (pixels, images, etc.) when applicable

- **User Identification:**
  - Implement a simple form to input a user ID (full authentication is not required for this POC).

### 3.2. Backend Services & LLM Integration

- **Chat Messaging Service:**
  - Develop FastAPI endpoints for chat creation, message sending, and message retrieval.
  - Integrate the Anthropic SDK to send and receive real messages using claude3.5-haiku.
  
- **Billing & Token Counting:**
  - For each message, count tokens (input, output, and others) and store details.
  - Calculate costs per message based on current token pricing.
  - Aggregate individual message costs into a cumulative thread total.
  - Generate detailed invoice line items and summary invoices.

- **Asynchronous Processing:**
  - Use Apache Kafka to queue incoming messages, decoupling message receipt from processing.
  - Process messages from Kafka to update Redis and eventually write to SQLite.

- **Scalable Data Ingestion Pipeline:**
  - Implement a dedicated event collector service to capture all Inference API events.
  - Design a multi-stage processing pipeline to handle high volumes of events.
  - Support different event types (token usage, image generation, etc.) with appropriate schemas.
  - Implement batch processing for efficiency with high volumes while maintaining near real-time visibility.

### 3.3. Billing Dashboard (Streamlit)

- **Dashboard Features:**
  - Display a real-time overview of cost metrics for chat threads and users.
  - Provide visualizations for:
    - Total cost per thread
    - Message-level cost breakdown
    - Token usage statistics
    - Resource usage metrics (pixels, images, etc.)
  - Ensure data on the dashboard is updated with a latency of no more than 15 seconds (15-second SLA).
  - Include visualizations for different usage types (tokens, images, etc.) and their associated costs.

## 4. Data Model & Database Schemas

### 4.1. Core Tables

- **dim_users**
  - `user_id` (PK)
  - `username`
  - `email`
  - `created_at`

- **dim_models**
  - `model_id` (PK)
  - `model_name` (e.g., "claude-3-5-haiku")
  - `description`
  - `is_active`

- **dim_event_types**
  - `event_type_id` (PK)
  - `event_name` (e.g., "token_usage", "image_generation")
  - `description`
  - `unit_of_measure` (e.g., "tokens", "pixels", "images")
  - `is_active`

- **dim_token_pricing** (Slowly Changing Dimension - Type 2)
  - `pricing_id` (PK)
  - `model_id` (FK to dim_models)
  - `input_token_price` (decimal)
  - `output_token_price` (decimal)
  - `effective_from` (datetime)
  - `effective_to` (datetime)
  - `is_current` (boolean)

- **dim_resource_pricing** (For non-token resources like images)
  - `resource_pricing_id` (PK)
  - `model_id` (FK to dim_models)
  - `event_type_id` (FK to dim_event_types)
  - `unit_price` (decimal)
  - `effective_from` (datetime)
  - `effective_to` (datetime)
  - `is_current` (boolean)

### 4.2. User and Thread Data

- **user_threads**
  - `thread_id` (PK)
  - `user_id` (FK to dim_users)
  - `title`
  - `created_at`
  - `updated_at`
  - `model_id` (FK to dim_models)
  - `is_active`

- **user_thread_messages**
  - `message_id` (PK)
  - `thread_id` (FK to user_threads)
  - `user_id` (FK to dim_users)
  - `content`
  - `role` (user/assistant)
  - `created_at`
  - `model_id` (FK to dim_models)

### 4.3. Token and Billing Data

- **message_tokens**
  - `token_id` (PK)
  - `message_id` (FK to user_thread_messages)
  - `token_type` (input/output)
  - `token_count`
  - `created_at`

- **api_events**
  - `event_id` (PK)
  - `message_id` (FK to user_thread_messages, nullable)
  - `user_id` (FK to dim_users)
  - `event_type_id` (FK to dim_event_types)
  - `model_id` (FK to dim_models)
  - `quantity` (decimal - tokens, pixels, images, etc.)
  - `created_at`

- **user_invoice_line_item**
  - `line_item_id` (PK)
  - `message_id` (FK to user_thread_messages)
  - `token_id` (FK to message_tokens)
  - `pricing_id` (FK to dim_token_pricing)
  - `amount` (decimal)
  - `created_at`

- **resource_invoice_line_item**
  - `resource_line_item_id` (PK)
  - `event_id` (FK to api_events)
  - `user_id` (FK to dim_users)
  - `resource_pricing_id` (FK to dim_resource_pricing)
  - `quantity` (decimal)
  - `amount` (decimal)
  - `created_at`

- **user_invoices**
  - `invoice_id` (PK)
  - `user_id` (FK to dim_users)
  - `thread_id` (FK to user_threads)
  - `total_amount` (decimal)
  - `invoice_date`
  - `status` (pending/paid)

### 4.4. Kafka Topics and Message Schemas

- **Inference API Events Topic**
  - Event ID, timestamp, user ID
  - Model ID, event type
  - Resource quantities (tokens, pixels, images)
  - Additional metadata for specific event types

## 5. Frontend (React.js SPA)

- **Unified Dashboard:**
  - Persistent chat interface along with tabs for:
    - Chat interactions (send/receive messages)
    - Billing details and cost breakdowns
    - Data artifacts (user details, invoice summaries)

- **Chat Interface:**
  - Message input box with real-time display of message history.
  - Display real-time token count and cost information next to each message.
  - Options to create a new thread or rejoin an existing thread.

- **User Management:**
  - Simple form for user ID input (no full authentication required).

- **Settings:**
  - Option to select the chat model (default is claude3.5-haiku).
  - Manage token pricing parameters.
  - Configure resource pricing for non-token resources (images, etc.).

## 6. Deployment & Infrastructure

- **Docker & Docker Compose:**
  - Containerize each component (FastAPI backend, React frontend, Redis, Kafka).
  - Use Docker Compose for orchestrating containers and setting up networked services.

- **Database Initialization:**
  - Pre-populate `dim_models` with Claude 3.5 Haiku.
  - Set up default token pricing in `dim_token_pricing`.
  - Initialize event types and resource pricing dimensions.

- **Environment & Configuration:**
  - Manage configuration via environment variables (model selection, pricing, etc.).

## 7. Additional Components

### 7.1. Apache Kafka Integration

- **Purpose:**
  - Enhance scalability by queuing incoming messages via Kafka.
  - Allow asynchronous processing of messages before caching in Redis and writing to SQLite.

- **Workflow:**
  - Messages sent from the chat interface are published to a Kafka topic.
  - A Kafka consumer retrieves messages, sends them to Redis for quick access, and subsequently writes them into SQLite for persistence.

- **Kafka Topics:**
  - `raw-messages`: User message input
  - `llm-responses`: Responses from Anthropic API
  - `token-metrics`: Token counts and billing metrics
  - `inference-events`: Events from the Inference API
  - `processed-events`: Fully processed events with billing information

- **Scaling Considerations:**
  - Implement partitioning strategies for high-volume topics
  - Configure consumer groups for parallel processing of events

### 7.2. Streamlit Dashboard

- **Features:**
  - A separate web application built with Streamlit to monitor:
    - Chat thread costs
    - User-specific billing metrics
    - Overall token usage and system performance
  - Designed to update every 15 seconds to meet SLA requirements.

### 7.3. Inference API Event Collection

- **Event Collector Service:**
  - Lightweight service that captures events from the Inference API
  - Publishes events to dedicated Kafka topics
  - Supports batching for high-volume scenarios
  - Implements retry logic and dead-letter queues for reliability
  - Scales horizontally to handle increasing event volumes

## 8. Non-Functional Requirements

- **Scalability & Maintainability:**
  - Modular code structure separating backend APIs, business logic, and frontend components.
  - Use of Kafka and Redis to support high message volumes and real-time processing.

- **Performance:**
  - Ensure real-time responsiveness for chat and billing updates.
  - Optimize data queries from SQLite and use Redis caching where necessary.
  - Streamlit dashboard data updates should not exceed a 15-second latency.
  - Support for processing thousands of events per second during peak loads.

- **Extensibility:**
  - Design data models and API endpoints to accommodate future features such as authentication, additional LLM models, or enhanced analytics.

- **Logging & Error Handling:**
  - Implement robust logging across services to trace message flows and billing calculations.
  - Provide error handling to manage failures in external integrations (e.g., Anthropic SDK, Kafka, Redis).

- **Data Retention & Archiving:**
  - Implement policies for event data retention in Redis and SQLite.
  - Design archiving strategies for historical billing data.

## 9. Development Approach

1. **Data Modeling:**
   - Define and implement the database schema for users, threads, messages, tokens, and billing.

2. **Backend API Development:**
   - Implement FastAPI endpoints for user management, thread management, message handling, and billing.
   - Integrate Apache Kafka for asynchronous message processing.

3. **Event Ingestion Pipeline:**
   - Develop the event collector service for the Inference API.
   - Implement Kafka producers and consumers for event processing.

4. **LLM Integration:**
   - Integrate with the Anthropic SDK to process chat messages in real time.
   - Extract token counts and pricing details from responses.

5. **Frontend Development:**
   - Develop the React.js single-page application with a persistent chat interface and tabbed views.
   - Implement forms for user input and thread management.

6. **Real-Time Dashboard:**
   - Build the Streamlit dashboard to display near real-time metrics with a 15-second refresh SLA.

7. **Containerization & Orchestration:**
   - Containerize all components using Docker.
   - Set up orchestration using Docker Compose to manage FastAPI, React, Kafka, Redis, and SQLite.

8. **Testing & Deployment:**
   - Conduct unit and integration tests.
   - Deploy locally for proof-of-concept demonstration.

## 10. Summary

This project is a POC for a billing application prototype for an LLM-powered chat system. It combines a real-time chat interface (via FastAPI and React.js) with a comprehensive billing mechanism that tracks token usage and cost per message. The system leverages SQLite for persistence, Redis for caching, and Apache Kafka for scalable messaging. The architecture includes a scalable data ingestion pipeline for processing high volumes of Inference API events, supporting various resource types beyond just tokens (such as images and pixels). Additionally, a Streamlit dashboard provides near real-time (15-second SLA) insights into cost metrics and usage statistics. All components are containerized with Docker, facilitating local development and testing.