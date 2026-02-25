#!/bin/bash
# Example script to test the EsMS API with curl

API_URL="http://localhost:8000"

echo "Testing EsMS Energy Optimization API"
echo "===================================="
echo ""

# Test health endpoint
echo "1. Testing health endpoint..."
curl -s ${API_URL}/health | python -m json.tool
echo ""
echo ""

# Run optimization
echo "2. Running optimization with sample files..."
curl -X POST ${API_URL}/optimize \
  -F "batteries_json=@batteries.json" \
  -F "forecasts_csv=@forecasts.csv" \
  -F "config_json=@config.json" \
  -o schedule.csv

echo ""
echo "Optimization complete! Results saved to schedule.csv"
echo ""

echo "===================================="
echo "Test complete!"
