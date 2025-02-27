#!/bin/bash

echo "Restarting just the backend container to apply token tracking changes..."

# Stop the backend container
docker-compose stop backend

# Rebuild and restart just the backend
docker-compose up -d --build backend

echo "Backend restarted. Opening the application in browser to test..."

# Open the frontend in a browser
sleep 5
open http://localhost:3000/