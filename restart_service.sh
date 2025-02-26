#!/bin/bash

echo "Restarting AI Thread Billing services..."

# Navigate to the project directory
cd /Users/jordankail/projects/ai_thread_billing

# Stop the currently running containers
docker-compose down

# Build and restart the containers
docker-compose up -d

echo "Services restarted! The application should now be using the correct model names with date suffixes."
echo "You can check the logs with: docker-compose logs -f backend"