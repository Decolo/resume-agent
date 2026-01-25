#!/usr/bin/env python3
"""List available Gemini models"""

from google import genai

api_key = "AIzaSyCAlPgLJnzG6iad9ujohkkUFrewO2ajzfU"
client = genai.Client(api_key=api_key)

print("Available Gemini models:")
print("=" * 60)

try:
    models = client.models.list()
    for model in models:
        print(f"- {model.name}")
        if hasattr(model, 'supported_generation_methods'):
            print(f"  Methods: {model.supported_generation_methods}")
except Exception as e:
    print(f"Error: {e}")
