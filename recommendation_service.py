import uuid
from datetime import datetime
from typing import List, Dict, Any
from database import db
from models import POI, RecommendationRequest, RecommendationResponse

class RecommendationService:
    def get_recommendations(self, request: RecommendationRequest) -> RecommendationResponse:
        pois_data = db.get_pois_by_filters(tags=request.vibes, budget=request.budget, location=request.destination)
        pois = [POI(**poi) for poi in pois_data]

        itinerary = None
        if request.days > 1:
            itinerary = {}
            for day in range(1, request.days + 1):
                itinerary[f"day_{day}"] = [
                    {
                        "time_of_day": "Morning",
                        "description": f"Explore {request.destination}'s attractions",
                        "estimated_price": "$10-50"
                    },
                    {
                        "time_of_day": "Afternoon",
                        "description": f"Visit places matching your vibes: {', '.join(request.vibes)}",
                        "estimated_price": "$10-50"
                    },
                    {
                        "time_of_day": "Evening",
                        "description": "Dinner / Relaxation",
                        "estimated_price": "$15-60"
                    }
                ]
        # Save recommendation
        recommendation_id = str(uuid.uuid4())
        if request.user_id:
            db.save_recommendation({
                "id": recommendation_id,
                "user_id": request.user_id,
                "destination": request.destination,
                "vibes": request.vibes,
                "budget": request.budget,
                "pois": [poi.dict() for poi in pois],
                "itinerary": itinerary
            })
        return RecommendationResponse(
            recommendation_id=recommendation_id,
            user_id=request.user_id or "anonymous",
            destination=request.destination,
            generated_at=datetime.now(),
            pois=pois,
            itinerary=itinerary
        )

recommendation_service = RecommendationService()
