from fastapi import FastAPI, HTTPException, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uuid
import threading
import requests
import time
import asyncio
import aiohttp
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import json

app = FastAPI(
    title="TripSpark Recommendation Service",
    description="Composite microservice that generates travel recommendations by aggregating data from User and Catalog services",
    version="1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

USER_SERVICE_URL = "http://localhost:8081"  
CATALOG_SERVICE_URL = "http://localhost:8082"  

tasks = {}

class RecommendationRequest(BaseModel):
    user_id: str
    destination: Optional[str] = None
    vibes: List[str] = []
    budget: Optional[str] = None
    days: Optional[int] = 1

class RecommendationResponse(BaseModel):
    recommendation_id: str
    user_id: str
    destination: str
    generated_at: datetime
    recommendations: List[Dict[str, Any]]
    user_preferences: Dict[str, Any]
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

class UserServiceClient:
    @staticmethod
    def get_user(user_id: str) -> Dict[str, Any]:
        """Get user data from User microservice"""
        try:
            response = requests.get(f"{USER_SERVICE_URL}/users/{user_id}", timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=503, detail=f"User service unavailable: {str(e)}")

    @staticmethod
    def get_user_preferences(user_id: str) -> Dict[str, Any]:
        """Get user preferences from User microservice"""
        try:
            response = requests.get(f"{USER_SERVICE_URL}/users/{user_id}/preferences", timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                return {}  
        except requests.exceptions.RequestException:
            return {}  

class CatalogServiceClient:
    @staticmethod
    def get_pois(city: Optional[str] = None, tags: List[str] = None, budget: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get POIs from Catalog microservice"""
        try:
            params = {}
            if city:
                params['city'] = city
            if tags:
                params['tags'] = ','.join(tags)
            if budget:
                params['budget'] = budget
                
            response = requests.get(f"{CATALOG_SERVICE_URL}/pois", params=params, timeout=5)
            if response.status_code == 200:
                return response.json().get('pois', [])
            else:
                return []
        except requests.exceptions.RequestException:
            return []  

    @staticmethod
    def get_city_info(city: str) -> Optional[Dict[str, Any]]:
        """Get city information from Catalog microservice"""
        try:
            response = requests.get(f"{CATALOG_SERVICE_URL}/cities/{city}", timeout=5)
            if response.status_code == 200:
                return response.json()
            return None
        except requests.exceptions.RequestException:
            return None

class RecommendationEngine:
    def __init__(self):
        self.user_client = UserServiceClient()
        self.catalog_client = CatalogServiceClient()

    def generate_recommendations(self, user_id: str, destination: Optional[str] = None, 
                               vibes: List[str] = None, budget: Optional[str] = None) -> Dict[str, Any]:
        """Generate recommendations using threaded parallel execution"""
        vibes = vibes or []
        
        results = {}
        errors = {}

        def fetch_user_data():
            try:
                results['user'] = self.user_client.get_user(user_id)
                results['preferences'] = self.user_client.get_user_preferences(user_id)
            except Exception as e:
                errors['user'] = str(e)

        def fetch_catalog_data():
            try:
                results['pois'] = self.catalog_client.get_pois(city=destination, tags=vibes, budget=budget)
                if destination:
                    results['city_info'] = self.catalog_client.get_city_info(destination)
            except Exception as e:
                errors['catalog'] = str(e)

        user_thread = threading.Thread(target=fetch_user_data)
        catalog_thread = threading.Thread(target=fetch_catalog_data)
        
        user_thread.start()
        catalog_thread.start()
        
        user_thread.join()
        catalog_thread.join()

        if errors:
            raise HTTPException(status_code=500, detail=f"Service errors: {errors}")

        recommendations = self._compute_recommendations(results, vibes, budget)
        
        return {
            'user_data': results.get('user', {}),
            'user_preferences': results.get('preferences', {}),
            'catalog_data': {
                'pois': results.get('pois', []),
                'city_info': results.get('city_info', {})
            },
            'recommendations': recommendations
        }

    def _compute_recommendations(self, data: Dict[str, Any], vibes: List[str], budget: str) -> List[Dict[str, Any]]:
        """Compute personalized recommendations based on user preferences and catalog data"""
        user_prefs = data.get('user_preferences', {})
        pois = data.get('pois', [])
        
        recommendations = []
        
        for poi in pois[:10]:  # here, we will limit at top 10
            score = 0
            
            poi_tags = poi.get('tags', [])
            matching_tags = set(poi_tags) & set(vibes)
            score += len(matching_tags) * 2
            
            if budget and poi.get('budget') == budget:
                score += 3
                
            user_interests = user_prefs.get('interests', [])
            matching_interests = set(poi_tags) & set(user_interests)
            score += len(matching_interests)
            
            score += poi.get('rating', 0) / 5 * 2
            
            if score > 0:
                recommendations.append({
                    'poi_id': poi.get('id'),
                    'name': poi.get('name'),
                    'type': poi.get('type', 'attraction'),
                    'description': poi.get('description'),
                    'location': poi.get('location'),
                    'budget': poi.get('budget'),
                    'rating': poi.get('rating'),
                    'score': score,
                    'matching_tags': list(matching_tags),
                    'reason': f"Matches {len(matching_tags)} of your preferences"
                })
        
        recommendations.sort(key=lambda x: x['score'], reverse=True)
        return recommendations[:5]

def generate_recommendations_async(task_id: str, user_id: str, destination: str, vibes: List[str], budget: str):
    """Background task for async recommendation generation"""
    try:
        tasks[task_id] = {"status": "processing", "progress": 0.1}
        
        engine = RecommendationEngine()
        
        time.sleep(2)
        tasks[task_id]["progress"] = 0.5
        
        result = engine.generate_recommendations(user_id, destination, vibes, budget)
        
        tasks[task_id] = {
            "status": "completed", 
            "progress": 1.0,
            "result": result,
            "completed_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        tasks[task_id] = {
            "status": "failed",
            "error": str(e),
            "failed_at": datetime.now().isoformat()
        }

@app.get("/health")
async def health():
    """Health check endpoint"""
    services_health = {}
    try:
        user_health = requests.get(f"{USER_SERVICE_URL}/health", timeout=2)
        services_health['user_service'] = user_health.status_code == 200
    except:
        services_health['user_service'] = False
        
    try:
        catalog_health = requests.get(f"{CATALOG_SERVICE_URL}/health", timeout=2)
        services_health['catalog_service'] = catalog_health.status_code == 200
    except:
        services_health['catalog_service'] = False
    
    return {
        "status": "healthy",
        "timestamp": datetime.now(),
        "services": services_health,
        "service": "recommendation_composite"
    }

@app.get("/recommendations/{user_id}", response_model=RecommendationResponse)
async def get_recommendations(user_id: str, destination: Optional[str] = None, 
                            vibes: str = "", budget: Optional[str] = None):
    """
    Get real-time recommendations using parallel threaded execution
    - Calls User service and Catalog service concurrently using threads
    - Combines data to generate personalized recommendations
    """
    vibes_list = [vibe.strip() for vibe in vibes.split(",")] if vibes else []
    
    engine = RecommendationEngine()
    result = engine.generate_recommendations(user_id, destination, vibes_list, budget)
    
    recommendation_id = str(uuid.uuid4())
    
    return RecommendationResponse(
        recommendation_id=recommendation_id,
        user_id=user_id,
        destination=destination or "general",
        generated_at=datetime.now(),
        recommendations=result['recommendations'],
        user_preferences=result['user_preferences'],
        catalog_data=result['catalog_data'],
        _links={
            "self": f"/recommendations/{user_id}",
            "user": f"/users/{user_id}",
            "catalog": "/catalog",
            "async": f"/recommendations/async/{user_id}"
        }
    )

@app.post("/recommendations/async/{user_id}", status_code=status.HTTP_202_ACCEPTED, response_model=AsyncTaskResponse)
async def start_async_recommendations(
    user_id: str, 
    background_tasks: BackgroundTasks,
    destination: Optional[str] = None,
    vibes: str = "",
    budget: Optional[str] = None
):
    """
    Start async recommendation generation (202 Accepted pattern)
    - Returns immediately with task ID
    - Client polls for status using the task ID
    """
    try:
        user_client = UserServiceClient()
        user_client.get_user(user_id)  
    except HTTPException:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    
    task_id = str(uuid.uuid4())
    vibes_list = [vibe.strip() for vibe in vibes.split(",")] if vibes else []
    
    background_tasks.add_task(
        generate_recommendations_async, 
        task_id, user_id, destination or "general", vibes_list, budget
    )
    
    tasks[task_id] = {"status": "accepted", "progress": 0.0}
    
    return AsyncTaskResponse(
        task_id=task_id,
        status="accepted",
        message="Recommendation generation started",
        _links={
            "status": f"/recommendations/status/{task_id}",
            "user": f"/users/{user_id}",
            "self": f"/recommendations/async/{user_id}"
        }
    )

@app.get("/recommendations/status/{task_id}", response_model=TaskStatusResponse)
async def get_async_task_status(task_id: str):
    """
    Poll async task status
    - Client polls this endpoint to check recommendation generation progress
    """
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        result=task.get("result"),
        progress=task.get("progress", 0.0)
    )

@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "message": "TripSpark Recommendation Composite Service",
        "version": "1.0",
        "description": "Aggregates data from User and Catalog services to generate personalized travel recommendations",
        "endpoints": {
            "health": "GET /health",
            "realtime_recommendations": "GET /recommendations/{user_id}",
            "async_recommendations": "POST /recommendations/async/{user_id}",
            "async_status": "GET /recommendations/status/{task_id}"
        },
        "dependencies": {
            "user_service": USER_SERVICE_URL,
            "catalog_service": CATALOG_SERVICE_URL
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)