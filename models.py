from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

# POI
class POI(BaseModel):
    id: str
    name: str
    description: str
    tags: List[str]
    budget: str
    location: str
    coordinates: Optional[Dict[str, float]] = None
    rating: Optional[float] = None
    price_level: Optional[int] = None

# Recommendation requests
class RecommendationRequest(BaseModel):
    user_id: Optional[str] = None
    destination: str
    vibes: List[str] = []
    budget: str
    days: Optional[int] = 1

# Recommendation responses
class RecommendationResponse(BaseModel):
    recommendation_id: str
    user_id: str
    destination: str
    generated_at: datetime
    pois: List[POI]
    itinerary: Optional[Dict[str, Any]] = None
