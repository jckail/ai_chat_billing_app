# AI Thread Billing System

A proof-of-concept application for tracking and billing AI chat thread interactions in real-time. This system demonstrates cost tracking for LLM (Large Language Model) interactions using Anthropic's Claude models.

## Features

- **Real-time Chat Interface**: Interact with Claude 3.5 Haiku and other LLMs
- **Cost Tracking**: Monitor token usage and costs per message in real-time
- **Analytics Dashboard**: View usage metrics and cost breakdowns
- **Billing Management**: Generate invoices for threads and track billing history
- **Event Collection**: Capture API events for comprehensive billing
- **Kafka-based Architecture**: Scalable message processing pipeline

## Architecture

The system consists of the following components:

- **Backend**: FastAPI application with SQLite database
- **Frontend**: React single-page application
- **Dashboard**: Streamlit analytics dashboard
- **Event Collector**: Service for capturing API events
- **Infrastructure**: Apache Kafka, Redis, Docker Compose

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Anthropic API key

### Setup

1. Clone this repository
2. Create a `.env` file from the `.env.sample` template
3. Add your Anthropic API key to the `.env` file
4. Build and start the application using Docker Compose:

```bash
docker-compose up
```

### Accessing the Application

- **Chat Interface**: http://localhost:3000
- **API**: http://localhost:8000
- **Analytics Dashboard**: http://localhost:8501
- **Event Collector**: http://localhost:8080

## Data Model

The system uses a comprehensive data model to track users, threads, messages, token usage, and billing:

- Dimension tables for users, models, and pricing
- Transaction tables for threads, messages, and events
- Billing tables for invoices and line items

## Development

To extend or modify this application:

1. Backend code is in the `backend/` directory
2. Frontend code is in the `frontend/` directory
3. Dashboard code is in the `dashboard/` directory
4. Event Collector code is in the `event_collector/` directory

## License

MIT

## Acknowledgements

- Anthropic for Claude API
- FastAPI, React, and Streamlit for the application frameworks
- Apache Kafka and Redis for the messaging infrastructure