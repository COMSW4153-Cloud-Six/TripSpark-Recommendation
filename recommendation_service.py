import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from database import db
from models import POI, RecommendationRequest, RecommendationResponse

class RecommendationService:

    # ------------------------------
    # TAG EXTRACTION HELPERS
    # ------------------------------
    def _extract_poi_tags(self, poi: Dict[str, Any]) -> set:
        """Convert comma-separated vibes/activities/food into a unified tag set."""
        vibes = [v.strip() for v in poi.get("vibes", "").split(",") if v.strip()]
        activities = [a.strip() for a in poi.get("activities", "").split(",") if a.strip()]
        food = [f.strip() for f in poi.get("food", "").split(",") if f.strip()]

        return set(vibes + activities + food)

    def _compute_score(self, poi: Dict[str, Any], request: RecommendationRequest, user_profile: Dict[str, Any]) -> int:
        """Compute recommendation score aligned with UserProfile + Catalog models."""
        score = 0

        # ---- Extract tags from POI ----
        poi_tags = self._extract_poi_tags(poi)

        # ---- Build user interest tag set ----
        user_tags = set(user_profile.get("preferred_vibes", [])) \
                    | set(user_profile.get("favorite_foods", [])) \
                    | set(user_profile.get("favorite_activities", []))

        # ---- Vibes passed in request ----
        request_vibes = set(request.vibes)

        # ---- Match tags ----
        matching_tags = poi_tags & user_tags
        score += len(matching_tags) * 2

        # ---- Match request vibes ----
        matching_vibes = poi_tags & request_vibes
        score += len(matching_vibes)

        # ---- Spending preference (textual: low/medium/high) ----
        user_spending = user_profile.get("spending_preference")
        if user_spending and poi.get("spending") == user_spending:
            score += 3

        # ---- Daily budget match (numeric) ----
        daily_budget = user_profile.get("daily_budget_limit")
        if daily_budget and poi.get("budget") and poi["budget"] <= daily_budget:
            score += 2

        # ---- Rating boost ----
        score += (poi.get("rating", 0) / 5) * 2

        return score

    # ------------------------------
    # MAIN RECOMMENDATION METHOD
    # ------------------------------
    def get_recommendations(
        self,
        request: RecommendationRequest,
        user_profile: Optional[Dict[str, Any]] = None
    ) -> RecommendationResponse:

        # ------------------------------
        # STEP 1: Retrieve POIs
        # ------------------------------
        pois_data = db.get_pois_by_filters(
            tags=request.vibes,
            budget=request.budget,
            location=request.destination
        )

        # Convert raw DB entries → POI objects
        pois = [POI(**poi) for poi in pois_data]

        # ------------------------------
        # STEP 2: Score POIs
        # ------------------------------
        scored_pois = []

        # Ensure user_profile exists (fallback for anonymous users)
        user_profile = user_profile or {
            "preferred_vibes": [],
            "favorite_activities": [],
            "favorite_foods": [],
            "spending_preference": None,
            "daily_budget_limit": None
        }

        for poi in pois_data:
            score = self._compute_score(poi, request, user_profile)
            if score > 0:
                poi_entry = poi.copy()
                poi_entry["score"] = score
                scored_pois.append(poi_entry)

        # Sort by descending score
        scored_pois.sort(key=lambda x: x["score"], reverse=True)

        # Convert top POIs back to models
        top_pois = [POI(**p) for p in scored_pois[:5]]

        # ------------------------------
        # STEP 3: Generate Itinerary
        # ------------------------------
        itinerary = None
        if request.days > 1:
            itinerary = {}
            for day in range(1, request.days + 1):
                itinerary[f"day_{day}"] = [
                    {
                        "time_of_day": "Morning",
                        "description": f"Explore {request.destination}'s highlights",
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

        # ------------------------------
        # STEP 4: Save Recommendation
        # ------------------------------
        recommendation_id = str(uuid.uuid4())

        db.save_recommendation({
            "id": recommendation_id,
            "user_id": request.user_id,
            "destination": request.destination,
            "vibes": request.vibes,
            "budget": request.budget,
            "pois": [poi.dict() for poi in top_pois],
            "itinerary": itinerary
        })

        # ------------------------------
        # STEP 5: Return Response
        # ------------------------------
        return RecommendationResponse(
            recommendation_id=recommendation_id,
            user_id=request.user_id or "anonymous",
            destination=request.destination,
            generated_at=datetime.now(),
            pois=top_pois,
            itinerary=itinerary
        )


# Instance for import
recommendation_service = RecommendationService()
