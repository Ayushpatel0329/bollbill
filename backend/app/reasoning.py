"""NVIDIA Nemotron Reasoning LLM Client.
Supports deep reasoning, JSON draft structured extraction, and shop assistant chat.
"""
import json
import logging
from typing import List, Dict, Any, Tuple
from openai import AsyncOpenAI

log = logging.getLogger("bollbill.reasoning")

def get_nvidia_client(api_key: str, base_url: str = "https://integrate.api.nvidia.com/v1") -> AsyncOpenAI:
    return AsyncOpenAI(base_url=base_url, api_key=api_key)

SYSTEM_PROMPT = """You are Boll Bill Assistant, a smart, fast and reliable retail AI assistant for Indian shopkeepers.
You help create voice bills, inspect inventory, report udhaar (credit), and calculate daily sales.
Keep responses concise, clear, polite and accurate. Use Hindi, Hinglish or English based on the user's input.
When extracting bill items from speech, return strictly a valid JSON object matching the requested schema.
"""

async def voice_bill_with_reasoning(
    client: AsyncOpenAI,
    model: str,
    shop_items: List[Dict[str, Any]],
    speech_text: str
) -> Dict[str, Any]:
    """Uses NVIDIA Nemotron reasoning to parse spoken sentence into structured bill draft."""
    items_summary = "\n".join([f"- {it['name']} (Price: ₹{it.get('price', 0)}, Unit: {it.get('unit', 'piece')})" for it in shop_items[:100]])
    
    prompt = f"""Spoken sentence by shopkeeper: "{speech_text}"

Available Price List Items:
{items_summary}

Task:
Extract all items, quantities, and units mentioned in the speech.
Match with available items where possible. If an item is not found, list it in "unmatched".

Return ONLY a JSON object with this exact structure:
{{
  "lines": [
    {{"item": "Item Name", "qty": 2.0, "unit": "kg", "price": 50.0}}
  ],
  "unmatched": ["unknown item name"],
  "customer": "Customer Name or empty string"
}}
"""

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You extract structured invoice drafts from retail speech. Respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=2048,
            extra_body={"chat_template_kwargs": {"enable_thinking": True}}
        )

        content = response.choices[0].message.content or ""
        # Find JSON block
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start != -1 and json_end != -1:
            parsed = json.loads(content[json_start:json_end])
            return parsed
        return {"lines": [], "unmatched": [speech_text], "customer": ""}
    except Exception as e:
        log.exception("NVIDIA reasoning voice draft failed")
        return {"lines": [], "unmatched": [speech_text], "customer": ""}

async def chat_with_reasoning(
    client: AsyncOpenAI,
    model: str,
    message: str,
    history: List[Dict[str, str]],
    context_str: str = ""
) -> str:
    """Chat completion using NVIDIA Nemotron reasoning model."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT + ("\nContext:\n" + context_str if context_str else "")}]
    for h in history:
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            top_p=0.95,
            max_tokens=4096,
            extra_body={"chat_template_kwargs": {"enable_thinking": True}}
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        log.exception("NVIDIA reasoning chat failed")
        return f"Error contacting AI reasoning service: {str(e)}"
