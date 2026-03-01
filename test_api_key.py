#!/usr/bin/env python3
"""测试后端是否正确加载 API 密钥"""

import requests
import json

base = "http://localhost:8000"

print("Testing backend API key loading...")
print("=" * 60)

# 1. Test get settings
print("\n1. Getting settings...")
try:
    r = requests.get(f"{base}/api/settings", timeout=10)
    if r.status_code == 200:
        settings = r.json()
        providers = settings.get('providers', {})
        moonshot = providers.get('moonshot', {})
        api_key = moonshot.get('api_key', '')
        if api_key:
            print(f"   [OK] Moonshot API key configured (length: {len(api_key)})")
        else:
            print("   [FAIL] Moonshot API key not configured")
    else:
        print(f"   [FAIL] Get settings failed: HTTP {r.status_code}")
except Exception as e:
    print(f"   [FAIL] Error: {e}")

# 2. Test connection
print("\n2. Testing AI connection...")
try:
    r = requests.post(
        f"{base}/api/settings/test-connection",
        json={"provider": "moonshot", "api_key": "", "api_base": "", "model": ""},
        timeout=35
    )
    data = r.json()
    if r.status_code == 200 and data.get('success'):
        print(f"   [OK] Connection success! Model: {data.get('model')}")
    else:
        error = data.get('error', 'Unknown error')
        print(f"   [FAIL] Connection failed: {error}")
except requests.exceptions.Timeout:
    print("   [FAIL] Connection timeout - network issue or proxy problem")
except Exception as e:
    print(f"   [FAIL] Error: {e}")

# 3. Check system info
print("\n3. Checking system info...")
try:
    r = requests.get(f"{base}/api/system/info", timeout=5)
    if r.status_code == 200:
        print("   [OK] Backend service running")
        print(f"   Info: {r.json()}")
except Exception as e:
    print(f"   [FAIL] Cannot get system info: {e}")

print("\n" + "=" * 60)
print("Test completed")
