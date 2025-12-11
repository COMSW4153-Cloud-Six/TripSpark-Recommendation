from fastapi import FastAPI, HTTPException, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uuid
import threading
import requests
import time
from datetime import datetime
from dotenv import load_dotenv
import os
import json

load_dotenv()

app = FastAPI(
    title="TripSpark Recommendation Service",
    description="Composite microservice aggregating User + Catalog services",
    version="2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

USER_SERVICE_URL = os.getenv("USER_URL")
CATALOG_SERVICE_URL = os.getenv("CATALOG_URL")
tasks = {}

# ============================================
# RESPONSE MODELS
# ============================================

class RecommendationResponse(BaseModel):
    recommendation_id: str
    user_id: str
    destination: str
    generated_at: datetime
    recommendations: List[Dict[str, Any]]
    user_profile: Dict[str, Any]
    catalog_data: Dict[str, Any]
    _links: Dict[str, str]

class AsyncTaskResponse(BaseModel):
    task_id: str
    status: str
    message: str
    _links: Dict[str, str]

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    progress: Optional[float] = None

# ============================================
# USER CLIENT
# ============================================

class UserServiceClient:

    @staticmethod
    def get_user(user_id: str):
        try:
            res = requests.get(f"{USER_SERVICE_URL}/users/{user_id}", timeout=5)
            if res.status_code == 200:
                return res.json()
            raise HTTPException(status_code=404, detail="User not found")
        except Exception:
            raise HTTPException(status_code=503, detail="User service unavailable")

    @staticmethod
    def get_profile(user_id: str):
        try:
            res = requests.get(f"{USER_SERVICE_URL}/users/{user_id}/profile", timeout=5)
            if res.status_code == 200:
                return res.json()
            raise HTTPException(status_code=404, detail="Profile not found")
        except Exception:
            raise HTTPException(status_code=503, detail="User service unavailable")

# ============================================
# CATALOG CLIENT
# ============================================

class CatalogServiceClient:

    @staticmethod
    def get_pois(city: Optional[str] = None, tags: List[str] = None, budget: Optional[str] = None):
        params = {}
        if city: params["city"] = city
        if tags: params["tags"] = ",".join(tags)
        if budget: params["budget"] = budget

        try:
            res = requests.get(f"{CATALOG_SERVICE_URL}/pois", params=params, timeout=5)
            if res.status_code == 200:
                return res.json().get("pois", [])
            return []
        except:
            return []

# ============================================
# RECOMMENDATION ENGINE
# ============================================

class RecommendationEngine:

    def __init__(self):
        self.user_client = UserServiceClient()
        self.catalog_client = CatalogServiceClient()

    def generate_recommendations(self, user_id, destination, vibes, budget):

        results = {}
        errors = {}

        # THREAD 1 — USER
        def fetch_user():
            try:
                user = self.user_client.get_user(user_id)
                profile = self.user_client.get_profile(user_id)
                results["profile"] = profile
            except Exception as e:
                errors["user"] = str(e)

        # THREAD 2 — CATALOG
        def fetch_catalog():
            try:
                pois = self.catalog_client.get_pois(
                    city=destination,
                    tags=vibes,
                    budget=budget
                )
                results["pois"] = pois
            except Exception as e:
                errors["catalog"] = str(e)

        t1 = threading.Thread(target=fetch_user)
        t2 = threading.Thread(target=fetch_catalog)
        t1.start(); t2.start()
        t1.join(); t2.join()

        if errors:
            raise HTTPException(status_code=500, detail=errors)

        recs = self._compute_recommendations(results, vibes, budget)

        return {
            "user_profile": results["profile"],
            "catalog_data": {"pois": results["pois"]},
            "recommendations": recs
        }

    # -------------------------------------------
    # MATCHING + SCORING
    # -------------------------------------------

    def _compute_recommendations(self, data, vibes, budget):
        profile = data["user_profile"]
        pois = data["catalog_data"]["pois"]

        user_vibes = set(profile.get("preferred_vibes", []))
        user_food = set(profile.get("favorite_foods", []))
        user_activities = set(profile.get("favorite_activities", []))
        user_tags = user_vibes | user_food | user_activities

        request_vibes = set([v.strip() for v in vibes]) if vibes else set()
        effective_vibes = user_vibes | request_vibes

        user_budget_pref = profile.get("spending_preference")
        user_daily_budget = profile.get("daily_budget_limit")

        recommendations = []

        for poi in pois[:50]:

            score = 0

            poi_vibes = set([v.strip() for v in poi.get("vibes", "").split(",") if v.strip()])
            poi_activities = set([a.strip() for a in poi.get("activities", "").split(",") if a.strip()])
            poi_food = set([f.strip() for f in poi.get("food", "").split(",") if f.strip()])
            poi_tags = poi_vibes | poi_activities | poi_food

            matching_tags = poi_tags & user_tags
            score += len(matching_tags) * 2

            matching_vibes = poi_vibes & effective_vibes
            score += len(matching_vibes)

            if user_budget_pref and poi.get("spending") == user_budget_pref:
                score += 3

            if user_daily_budget and poi.get("budget"):
                if poi["budget"] <= user_daily_budget:
                    score += 2

            score += (poi.get("rating", 0) / 5) * 2

            if score > 0:
                recommendations.append({
                    "poi_id": poi.get("poi"),
                    "name": poi.get("poi"),
                    "city": poi.get("city"),
                    "country": poi.get("country"),
                    "location": {
                        "latitude": poi.get("latitude"),
                        "longitude": poi.get("longitude"),
                    },
                    "spending": poi.get("spending"),
                    "budget": poi.get("budget"),
                    "rating": poi.get("rating"),
                    "score": score,
                    "matching_tags": list(matching_tags),
                    "matching_vibes": list(matching_vibes),
                })

        recommendations.sort(key=lambda x: x["score"], reverse=True)
        return recommendations[:5]

# ============================================
# ASYNC BACKGROUND TASK
# ============================================

def generate_async_task(task_id, user_id, destination, vibes, budget):
    try:
        tasks[task_id] = {"status": "processing", "progress": 0.1}
        time.sleep(1)

        engine = RecommendationEngine()
        result = engine.generate_recommendations(user_id, destination, vibes, budget)

        tasks[task_id] = {
            "status": "completed",
            "progress": 1.0,
            "result": result,
            "completed_at": datetime.now().isoformat()
        }

    except Exception as e:
        tasks[task_id] = {"status": "failed", "error": str(e)}

# ============================================
# ENDPOINTS
# ============================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow(),
        "services": {
            "user": requests.get(f"{USER_SERVICE_URL}/health").status_code == 200,
            "catalog": requests.get(f"{CATALOG_SERVICE_URL}/health").status_code == 200,
        }
    }

# data
@app.get("/recommendations/{user_name}")
def get_recommendation(
    user_name: str,
    destination: Optional[str] = None,
    vibes: str = "",
    budget: Optional[str] = None
):
    try:
        with open("data/sample.json", "r") as f:
            data = json.load(f)
        return data
    except Exception as e:
        return {"error": str(e)}


# ==========================================================
#  🔥 SYNC RECOMMENDATIONS — WITH FK VALIDATION
# ==========================================================

@app.get("/recommendations/{user_id}", response_model=RecommendationResponse)
def get_recommendations(
    user_id: str,
    destination: Optional[str] = None,
    vibes: str = "",
    budget: Optional[str] = None
):
    # -------------------------------
    # LOGICAL FOREIGN KEY CONSTRAINT
    # -------------------------------

    # 1. Validate user_id exists → FK check
    try:
        UserServiceClient().get_user(user_id)
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(
                status_code=400,
                detail=f"Foreign key constraint failed: user_id '{user_id}' does not exist in User Service"
            )
        raise

    # 2. Optional: validate that destination city exists in catalog
    if destination:
        try:
            test_catalog = requests.get(
                f"{CATALOG_SERVICE_URL}/pois",
                params={"city": destination},
                timeout=5
            )
            if test_catalog.status_code != 200:
                raise Exception()
        except:
            raise HTTPException(
                status_code=400,
                detail=f"Foreign key constraint failed: destination '{destination}' is not recognized by Catalog Service"
            )

    # -------------------------------
    # Continue with recommendation logic
    # -------------------------------
    vibes_list = [v.strip() for v in vibes.split(",")] if vibes else []
    engine = RecommendationEngine()
    result = engine.generate_recommendations(user_id, destination, vibes_list, budget)

    rec_id = str(uuid.uuid4())

    return RecommendationResponse(
        recommendation_id=rec_id,
        user_id=user_id,
        destination=destination or "general",
        generated_at=datetime.now(),
        recommendations=result["recommendations"],
        user_profile=result["user_profile"],
        catalog_data=result["catalog_data"],
        _links={
            "self": f"/recommendations/{user_id}",
            "user": f"/users/{user_id}",
            "async": f"/recommendations/async/{user_id}"
        }
    )

# ==========================================================
#  🔥 ASYNC RECOMMENDATIONS — FK VALIDATION
# ==========================================================

@app.post("/recommendations/async/{user_id}", status_code=202, response_model=AsyncTaskResponse)
def start_async(
    user_id: str,
    background_tasks: BackgroundTasks,
    destination: Optional[str] = None,
    vibes: str = "",
    budget: Optional[str] = None
):

    # -------------------------------
    # LOGICAL FK CONSTRAINT (user_id)
    # -------------------------------
    try:
        UserServiceClient().get_user(user_id)
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(
                status_code=400,
                detail=f"Foreign key constraint failed: user_id '{user_id}' does not exist"
            )
        raise

    task_id = str(uuid.uuid4())
    vibes_list = [v.strip() for v in vibes.split(",")] if vibes else []

    tasks[task_id] = {"status": "accepted", "progress": 0.0}

    background_tasks.add_task(
        generate_async_task,
        task_id, user_id, destination, vibes_list, budget
    )

    return AsyncTaskResponse(
        task_id=task_id,
        status="accepted",
        message="Task started.",
        _links={"status": f"/recommendations/status/{task_id}"}
    )

@app.get("/recommendations/status/{task_id}", response_model=TaskStatusResponse)
def task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found.")
    return TaskStatusResponse(task_id=task_id, **tasks[task_id])

@app.get("/")
def root():
    return {"message": "TripSpark Recommendation Composite Service v2.0"}

# ============================================
# LOCAL RUN
# ============================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
