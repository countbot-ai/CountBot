#!/usr/bin/env python3
"""
Direct test Moonshot API connection (bypass proxy)
"""

import os
import sys
from pathlib import Path

# Load .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)
    print(f"Loaded .env from {env_path}")

# Clear proxy env vars before importing other libs
for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    if key in os.environ:
        del os.environ[key]
        print(f"Cleared env var: {key}")

os.environ['NO_PROXY'] = '*'

import httpx
from openai import OpenAI

API_KEY = os.environ.get('MOONSHOT_API_KEY', '')
if not API_KEY:
    print("ERROR: MOONSHOT_API_KEY not set")
    print("Please set it in .env file or environment variable")
    sys.exit(1)

print(f"API Key length: {len(API_KEY)}")
print(f"API Key prefix: {API_KEY[:10]}...")

print("\nTest 1: Direct httpx test (no proxy)")
print("-" * 60)
try:
    client = httpx.Client(
        proxy=None,
        timeout=30.0,
        verify=True,
    )
    
    response = client.get(
        "https://api.moonshot.cn/v1/models",
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=30.0
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"[OK] Success! Got {len(data.get('data', []))} models")
        for model in data.get('data', [])[:3]:
            print(f"  - {model.get('id')}")
    else:
        print(f"[FAIL] HTTP {response.status_code}")
        print(f"Response: {response.text}")
except Exception as e:
    print(f"[FAIL] Error: {e}")
    import traceback
    traceback.print_exc()

print("\nTest 2: OpenAI client test")
print("-" * 60)
try:
    http_client = httpx.Client(
        proxy=None,
        timeout=30.0,
        verify=True,
    )
    
    client = OpenAI(
        api_key=API_KEY,
        base_url="https://api.moonshot.cn/v1",
        http_client=http_client,
        timeout=30.0,
    )
    
    models = client.models.list()
    print(f"[OK] Success! Got model list")
    for model in list(models.data)[:3]:
        print(f"  - {model.id}")
    
    print("\nTest 3: Simple chat request")
    print("-" * 60)
    completion = client.chat.completions.create(
        model="kimi-k2.5",
        messages=[
            {"role": "system", "content": "You are Kimi"},
            {"role": "user", "content": "Hello, please reply 'Test successful'"}
        ],
        temperature=1.0,
        max_tokens=50,
    )
    
    print(f"[OK] Success!")
    print(f"Reply: {completion.choices[0].message.content}")
    
except Exception as e:
    print(f"[FAIL] Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Test completed")
