#!/bin/bash
# Test Gemini API with curl

API_KEY="AIzaSyCAlPgLJnzG6iad9ujohkkUFrewO2ajzfU"

echo "Testing Gemini API with different models..."
echo "=============================================="
echo ""

# Test 1: gemini-2.0-flash-exp
echo "Test 1: gemini-2.0-flash-exp"
echo "----------------------------"
curl -s "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=${API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "contents": [{
      "parts": [{
        "text": "Say hello"
      }]
    }]
  }' | jq '.'
echo ""
echo ""

# Test 2: gemini-1.5-flash
echo "Test 2: gemini-1.5-flash"
echo "------------------------"
curl -s "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "contents": [{
      "parts": [{
        "text": "Say hello"
      }]
    }]
  }' | jq '.'
echo ""
echo ""

# Test 3: gemini-1.5-pro
echo "Test 3: gemini-1.5-pro"
echo "----------------------"
curl -s "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key=${API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "contents": [{
      "parts": [{
        "text": "Say hello"
      }]
    }]
  }' | jq '.'
echo ""
echo ""

# Test 4: List available models
echo "Test 4: List all available models"
echo "----------------------------------"
curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=${API_KEY}" | jq '.models[] | {name: .name, supportedGenerationMethods: .supportedGenerationMethods}'
