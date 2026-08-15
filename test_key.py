import requests
import json
import os

key = "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"
res = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    json={
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": "Hello"}]
    }
)
print(res.status_code, res.text)
