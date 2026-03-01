#!/usr/bin/env python3
"""
Direct test Moonshot API connection using LiteLLM
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

import litellm
from litellm import completion

API_KEY = os.environ.get('MOONSHOT_API_KEY', '')
if not API_KEY:
    print("ERROR: MOONSHOT_API_KEY not set")
    print("Please set it in .env file or environment variable")
    sys.exit(1)

print(f"API Key length: {len(API_KEY)}")
print(f"API Key prefix: {API_KEY[:10]}...")

print("\nTest 1: LiteLLM completion test (no proxy)")
print("-" * 60)

try:
    # Disable LiteLLM verbose logging
    litellm.set_verbose = False
    
    response = completion(
        model="moonshot/kimi-k2.5",
        api_key=API_KEY,
        api_base="https://api.moonshot.cn/v1",
        messages=[
            {"role": "system", "content": "You are Kimi"},
            {"role": "user", "content": "Hello, please reply 'Test successful'"}
        ],
        temperature=1.0,
        max_tokens=50,
    )
    
    print(f"[OK] Success!")
    print(f"Model: {response.model}")
    print(f"Reply: {response.choices[0].message.content}")
    
except Exception as e:
    print(f"[FAIL] Error: {e}")
    import traceback
    traceback.print_exc()

print("\nTest 2: LiteLLM streaming test")
print("-" * 60)

try:
    response = completion(
        model="moonshot/kimi-k2.5",
        api_key=API_KEY,
        api_base="https://api.moonshot.cn/v1",
        messages=[
            {"role": "system", "content": "You are Kimi"},
            {"role": "user", "content": "Say 'Streaming works'"}
        ],
        temperature=1.0,
        max_tokens=20,
        stream=True,
    )
    
    print("[OK] Streaming response:", end=" ")
    collected = ""
    for chunk in response:
        if chunk.choices[0].delta.content:
            content = chunk.choices[0].delta.content
            collected += content
            print(content, end="")
    print()
    print(f"Full response: {collected}")
    
except Exception as e:
    print(f"[FAIL] Error: {e}")
    import traceback
    traceback.print_exc()

print("\nTest 3: LiteLLM with additional parameters")
print("-" * 60)

try:
    response = completion(
        model="moonshot/kimi-k2.5",
        api_key=API_KEY,
        api_base="https://api.moonshot.cn/v1",
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Count from 1 to 3"}
        ],
        temperature=1.0,
        max_tokens=100,
        # top_p=0.9,  # kimi-k2.5 只支持 temperature=1
    )
    
    print(f"[OK] Success!")
    print(f"Usage: {response.usage}")
    print(f"Reply: {response.choices[0].message.content}")
    
except Exception as e:
    print(f"[FAIL] Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("LiteLLM Test completed")
