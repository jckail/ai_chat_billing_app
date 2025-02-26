#!/bin/bash

echo "Updating Anthropic SDK and restarting AI Thread Billing services..."

# Navigate to the project directory
cd /Users/jordankail/projects/ai_thread_billing

# Stop the currently running containers
echo "Stopping current services..."
docker-compose down

# Update the Anthropic package in the backend container
echo "Updating Anthropic SDK to latest version..."
docker-compose run --rm backend pip install anthropic>=0.22.0

# Build and restart the containers
echo "Restarting services..."
docker-compose up -d

echo "Services updated and restarted! The application should now handle streaming correctly."
echo "You can check the logs with: docker-compose logs -f backend"