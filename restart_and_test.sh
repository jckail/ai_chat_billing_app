#!/bin/bash

# Stop any existing containers
echo "Stopping existing containers..."
docker-compose down

# Rebuild and start the services
echo "Building and starting services..."
docker-compose up -d --build

# Wait for services to be ready
echo "Waiting for services to be ready..."
sleep 10

# Display logs to verify everything is working
echo "Displaying backend logs (Ctrl+C to exit):"
docker-compose logs -f backend