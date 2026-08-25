import asyncio
import os
import sys

# Add backend directory to sys.path to allow imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nlp.openrouter import _achat_json, ai_provider_name
import json

async def test():
    keywords = [
        {"phrase": f"iron condor {i}", "type": "primary", "is_ai": False}
        for i in range(150)
    ]
    trimmed = keywords[:500]
    prompt = f"""
*Visually Optimized JSON Output.*
• Output MUST be a valid JSON object matching the schema below exactly. 
• DO NOT USE markdown ticks for the JSON output. Return pure JSON.
• Treat both the Master Hub and each Sub-Silo as separate objects in the `hubs` array.
• Format for spokes: "[Optimized Title] (Target Keyword: [exact keyword])" or "[Optimized Title] (Target Keyword: [exact keyword]) [Include H2: entity]"

EXPECTED JSON SCHEMA:
{{
  "hubs": [
    {{
      "hub_title": "📍 MASTER HUB: [Broadest Search Intent / Topic]",
      "layers": {{
        "🧱 FOUNDATION SPOKES (Authority)": ["What Is [Core Entity]? Complete Guide (Target Keyword: what is [core entity])"],
        "⚙️ CORE STRATEGY": ["How to Implement [Core Entity] (Target Keyword: how to implement [core entity])"]
      }},
      "sub_silos": [
        {{
          "hub_title": "🪐 SUB-SILO 1: LEARNING HUB — How to Use [Core Entity]",
          "layers": {{
            "🧱 Foundations": ["How to Use [Core Entity] (Target Keyword: how to use [core entity])"]
          }}
        }}
      ]
    }}
  ]
}}

Main Keywords (Create Master Hubs and Spokes using ONLY these):
{json.dumps([kw for kw in trimmed if kw.get("type") != "entity"])}

Entity Keywords (DO NOT CREATE SPOKES FOR THESE. Distribute and append them as [Include H2: entity] to the most relevant Spokes created above):
{json.dumps([kw["phrase"] for kw in trimmed if kw.get("type") == "entity"])}
"""
    try:
        print("Sending request to", ai_provider_name())
        payload = await _achat_json(
            system_prompt="You are a Senior SEO Content Strategist. You output only valid JSON objects matching the SEO architecture schema.",
            user_prompt=prompt,
            temperature=0.15,
            max_tokens=4000,
        )
        print("Raw Payload:", type(payload), payload)
    except Exception as exc:
        print("Error:", exc)

if __name__ == "__main__":
    asyncio.run(test())
