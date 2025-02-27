#!/bin/bash
# Script to restart services and test the billing metrics update fix

echo "===== Testing Billing Metrics Fix ====="

# Step 1: Restart the backend services 
echo "Restarting backend services..."
docker-compose restart backend
sleep 5

# Step 2: Restart the frontend
echo "Restarting frontend service..."
docker-compose restart frontend
sleep 5

# Step 3: Clear Redis cache to ensure fresh metrics
echo "Clearing Redis cache..."
docker-compose exec redis redis-cli FLUSHALL
echo "Redis cache cleared."

# Step 4: Watch the logs for billing-related messages
echo "Monitoring logs for billing metrics updates..."
echo "Press Ctrl+C to stop watching logs"
docker-compose logs -f --tail=100 backend | grep -i "\[BILLING\]"