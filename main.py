"""
FastAPI travel recommendation backend using OpenAI for generation
Supports:
 - POST /recommend -> returns an LLM-generated full-day itinerary
 - GET  /session/{user_id}/history -> view conversation memory
 - POST /session/{user_id}/clear -> clear memory for a user

Memory: in-memory dict by default (ephemeral). To persist across restarts, set REDIS_URL environment variable.
Environment:
 - OPENAI_API_KEY (required)
 - REDIS_URL (optional; e.g., redis://localhost:6379/0)
"""

import os
import uuid
import asyncio
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from openai import OpenAI
import httpx

# Optional Redis — used only if REDIS_URL provided
try:
    import redis.asyncio as redis_async
except Exception:
    redis_async = None

# -----------------------
# Config
# -----------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Please set the OPENAI_API_KEY environment variable.")

REDIS_URL = os.getenv("REDIS_URL")  # optional: e.g. redis://localhost:6379/0
USE_REDIS = bool(REDIS_URL) and (redis_async is not None)

# LLM settings
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")  # change if needed
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "700"))
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.8"))

# -----------------------
# Initialize OpenAI client
# -----------------------
client = OpenAI(api_key=OPENAI_API_KEY)

# -----------------------
# Memory backend
# -----------------------
if USE_REDIS:
    redis = redis_async.from_url(REDIS_URL)
else:
    # simple in-memory dict: user_id -> list of messages
    _memory_store: Dict[str, List[Dict[str,str]]] = {}

# helper funcs for memory
async def get_memory(user_id: str) -> List[Dict[str, str]]:
    if USE_REDIS:
        raw = await redis.get(f"conversation:{user_id}")
        if not raw:
            return []
        import json
        return json.loads(raw)
    else:
        return _memory_store.get(user_id, [])

async def append_memory(user_id: str, role: str, content: str):
    if USE_REDIS:
        import json
        mem = await get_memory(user_id)
        mem.append({"role": role, "content": content})
        await redis.set(f"conversation:{user_id}", json.dumps(mem))
    else:
        if user_id not in _memory_store:
            _memory_store[user_id] = []
        _memory_store[user_id].append({"role": role, "content": content})

async def clear_memory(user_id: str):
    if USE_REDIS:
        await redis.delete(f"conversation:{user_id}")
    else:
        _memory_store.pop(user_id, None)

# -----------------------
# API models
# -----------------------
class RecommendRequest(BaseModel):
    user_id: Optional[str] = Field(None, description="Optional user id. If not provided, server will create one.")
    city: str
    season: str
    min_budget: int
    max_budget: int
    preference: Optional[str] = None  # e.g., "food", "romantic", "adventure"
    days: Optional[int] = Field(1, ge=1, le=14, description="Number of days for itinerary")

class ItineraryItem(BaseModel):
    time_of_day: str
    description: str
    estimated_price: Optional[str] = None

class RecommendResponse(BaseModel):
    user_id: str
    city: str
    season: str
    preference: Optional[str]
    days: int
    itinerary: Dict[str, List[ItineraryItem]]  # day -> list of items

# -----------------------
# FastAPI app
# -----------------------
app = FastAPI(title="LLM Travel Recommender", version="1.0")

# -----------------------
# Helpers to craft LLM prompt/messages
# -----------------------
def build_system_prompt() -> str:
    return (
        "You are an expert travel planner. Given a user's city, season, budget and preference tags, "
        "generate a friendly, realistic, and varied day-by-day itinerary. "
        "Each day should have: Morning, Lunch, Afternoon, Dinner, Evening suggestions. "
        "Include one-sentence descriptions and an approximate price for each item. "
        "Keep results concise and JSON-serializable. Do not ask clarifying questions. "
        "If the user's budget is tight, bias towards low-cost options; if high, include premium options. "
        "Prefer local experiences and include timing hints when appropriate."
    )

def build_user_prompt(payload: RecommendRequest) -> str:
    pref_text = f"Preference: {payload.preference}." if payload.preference else "No special preference."
    budget_text = f"Budget per-person range: ${payload.min_budget} - ${payload.max_budget}."
    return (
        f"Plan {payload.days} day(s) of activities for a visitor to {payload.city} in {payload.season}. "
        f"{pref_text} {budget_text} "
        "Return a JSON object with keys 'day_1', 'day_2', ... each containing a list of 5 items "
        "with 'time_of_day' (Morning/Lunch/Afternoon/Dinner/Evening), 'description', and 'estimated_price'. "
        "Make the descriptions vivid and realistic. Keep prices approximate and within the budget range."
    )

# Utility to ask the OpenAI Chat API (uses the OpenAI Python client)
async def call_llm(messages: List[Dict[str,str]]) -> str:
    """
    Calls OpenAI using the chat completions endpoint via the OpenAI Python client.
    Returns the assistant text content (string).
    """
    # We wrap in async HTTP call; OpenAI client supports sync and may support async depending on version.
    # Use the client's chat completion method if available, otherwise fall back to httpx.
    try:
        # Preferred: client.chat.completions.create(...)
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE
        )
        # resp.choices[0].message.content or resp.choices[0].message['content'] depending on client
        content = None
        if hasattr(resp, "choices") and len(resp.choices) > 0:
            # many SDK responses expose content differently depending on version:
            choice0 = resp.choices[0]
            if hasattr(choice0, "message") and choice0.message is not None:
                content = choice0.message.get("content") if isinstance(choice0.message, dict) else choice0.message.content
            else:
                # older formats:
                content = getattr(choice0, "text", None)
        if content is None:
            # fallback: str(resp)
            content = str(resp)
        return content
    except Exception as e:
        # fallback: call REST via httpx (transparent; requires OPENAI_API_KEY)
        openai_url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=60.0) as http:
            r = await http.post(openai_url, json={
                "model": LLM_MODEL,
                "messages": messages,
                "max_tokens": MAX_TOKENS,
                "temperature": TEMPERATURE
            }, headers=headers)
            r.raise_for_status()
            j = r.json()
            # try to extract content
            try:
                return j["choices"][0]["message"]["content"]
            except Exception:
                return j

# Minimal JSON extractor (attempt to parse JSON out of free text)
import json, re
def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    If the LLM returns JSON, extract it. If it returns text with JSON inside, try to find the JSON substring.
    Returns dict or None.
    """
    # Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # Try to detect the first { ... } block
    m = re.search(r"(\{(?:.|\n)*\})", text)
    if m:
        candidate = m.group(1)
        try:
            return json.loads(candidate)
        except Exception:
            pass

    # Could not parse JSON
    return None

# -----------------------
# Endpoints
# -----------------------
@app.post("/recommend", response_model=RecommendResponse)
async def recommend(payload: RecommendRequest = Body(...)):
    # assign or create user_id
    user_id = payload.user_id or str(uuid.uuid4())

    # Append user's request to memory
    user_message_text = f"User requests itinerary: city={payload.city}, season={payload.season}, " \
                        f"budget={payload.min_budget}-{payload.max_budget}, preference={payload.preference}, days={payload.days}"
    await append_memory(user_id, "user", user_message_text)

    # Build messages for LLM: include system, conversation memory, then user instruction
    messages = [{"role": "system", "content": build_system_prompt()}]

    # Retrieve short conversation history (we'll include up to last N messages to keep prompt size reasonable)
    history = await get_memory(user_id)
    # limit to last 12 messages to avoid very large contexts
    recent = history[-12:] if len(history) > 12 else history
    for m in recent:
        messages.append({"role": m["role"], "content": m["content"]})

    # Add user instruction
    user_prompt = build_user_prompt(payload)
    messages.append({"role": "user", "content": user_prompt})

    # Call the LLM
    llm_response_text = await call_llm(messages)

    # Save assistant response to memory
    await append_memory(user_id, "assistant", llm_response_text)

    # Try to parse JSON
    parsed = extract_json_from_text(llm_response_text)

    itinerary_struct: Dict[str, List[ItineraryItem]] = {}

    if parsed:
        # Expect keys 'day_1', 'day_2', ...
        for day_key, items in parsed.items():
            # normalize each item into ItineraryItem
            day_list = []
            if isinstance(items, list):
                for itm in items:
                    # expected: time_of_day, description, estimated_price
                    tod = itm.get("time_of_day") or itm.get("time") or "Unknown"
                    desc = itm.get("description") or itm.get("desc") or str(itm)
                    price = itm.get("estimated_price") or itm.get("price") or None
                    day_list.append(ItineraryItem(time_of_day=tod, description=desc, estimated_price=price))
            itinerary_struct[day_key] = day_list
    else:
        # If not JSON-parsable, create a fallback by splitting response into lines and placing into one day
        lines = [ln.strip() for ln in llm_response_text.splitlines() if ln.strip()]
        day_list = []
        for i, ln in enumerate(lines[:20]):
            # crude split: "Morning:" etc
            if ":" in ln:
                tod, rest = ln.split(":", 1)
                day_list.append(ItineraryItem(time_of_day=tod.strip(), description=rest.strip(), estimated_price=None))
            else:
                day_list.append(ItineraryItem(time_of_day=f"item_{i+1}", description=ln, estimated_price=None))
        itinerary_struct["day_1"] = day_list

    # Build result model
    response = RecommendResponse(
        user_id=user_id,
        city=payload.city,
        season=payload.season,
        preference=payload.preference,
        days=payload.days,
        itinerary=itinerary_struct
    )
    return response

@app.get("/session/{user_id}/history")
async def session_history(user_id: str):
    mem = await get_memory(user_id)
    return {"user_id": user_id, "history": mem}

@app.post("/session/{user_id}/clear")
async def session_clear(user_id: str):
    await clear_memory(user_id)
    return {"user_id": user_id, "status": "cleared"}

# Root health check
@app.get("/")
async def root():
    return {"ok": True, "info": "LLM Travel Recommender. POST /recommend to get itineraries."}

# Run with: uvicorn main:app --reload
