#!/bin/bash
set -e

echo "Rebuilding and restarting services..."

# Rebuild and restart event_collector
echo "Rebuilding event_collector..."
docker-compose build event_collector

# Rebuild and restart backend
echo "Rebuilding backend..."
docker-compose build backend

# Restart services
echo "Restarting services..."
docker-compose up -d event_collector backend frontend

echo "Services restarted. Check logs with 'docker-compose logs -f'"