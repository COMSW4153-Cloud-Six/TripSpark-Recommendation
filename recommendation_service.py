import uuid
from datetime import datetime
from database import db
from models import POI, RecommendationRequest, RecommendationResponse
from typing import List, Dict, Any

class RecommendationService:
    def __init__(self):
        self.simple_recommender = SimpleRecommender()
        self.llm_recommender = LLMRecommender()
    
    def get_recommendations(self, request: RecommendationRequest) -> RecommendationResponse:
        pois = self.simple_recommender.get_poi_recommendations(
            request.destination, request.vibes, request.budget
        )
        
        itinerary = None
        if request.days > 1 or request.season:
            itinerary = self.llm_recommender.generate_itinerary(
                request.destination, request.season, request.vibes, request.budget, request.days
            )
        
        recommendation_id = str(uuid.uuid4())
        
        if request.user_id:
            db.save_recommendation({
                'id': recommendation_id,
                'user_id': request.user_id,
                'destination': request.destination,
                'vibes': request.vibes,
                'budget': request.budget,
                'pois': [poi.dict() for poi in pois],
                'itinerary': itinerary
            })
        
        return RecommendationResponse(
            recommendation_id=recommendation_id,
            user_id=request.user_id or "anonymous",
            destination=request.destination,
            generated_at=datetime.now(),
            pois=pois,
            itinerary=itinerary
        )

class SimpleRecommender:
    def get_poi_recommendations(self, destination: str, vibes: List[str], budget: str) -> List[POI]:
        pois_data = db.get_pois_by_filters(tags=vibes, budget=budget, location=destination)
        
        pois = []
        for poi_data in pois_data:
            pois.append(POI(**poi_data))
        
        return pois

class LLMRecommender:
    def generate_itinerary(self, city: str, season: str, preferences: List[str], 
                          budget: str, days: int) -> Dict[str, Any]:
        itinerary = {}
        for day in range(1, days + 1):
            itinerary[f"day_{day}"] = [
                {
                    "time_of_day": "Morning",
                    "description": f"Explore {city}'s attractions",
                    "estimated_price": "$0-20" if budget == "low" else "$20-50" if budget == "medium" else "$50+"
                },
                {
                    "time_of_day": "Afternoon", 
                    "description": f"Visit local spots matching your interests: {', '.join(preferences)}",
                    "estimated_price": "$10-30" if budget == "low" else "$30-70" if budget == "medium" else "$70+"
                },
                {
                    "time_of_day": "Evening",
                    "description": "Dinner and relaxation",
                    "estimated_price": "$15-40" if budget == "low" else "$40-100" if budget == "medium" else "$100+"
                }
            ]
        
        return itinerary

recommendation_service = RecommendationService()