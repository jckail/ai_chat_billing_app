#!/bin/bash

echo "Applying token metrics fix..."

# Stop the backend container but keep Redis running
echo "Stopping backend service..."
docker-compose stop backend

# Update all the necessary files
echo "Restarting backend service with updated code..."
docker-compose up -d --build backend

# Give it a moment to start up
echo "Waiting for backend to initialize..."
sleep 5

# Force Redis to flush its thread_metrics cache to ensure fresh data
echo "Flushing metrics caches..."
docker-compose exec redis redis-cli KEYS "billing:thread_metrics:*" | xargs -r docker-compose exec redis redis-cli DEL

echo "Fix applied! Now open the app in your browser and send a test message."
echo "The metrics should update properly after sending/receiving messages."

# Open in browser
sleep 2
open http://localhost:3000/