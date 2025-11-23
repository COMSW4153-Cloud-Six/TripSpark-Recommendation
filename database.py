import os
import json
import sqlite3
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

class Database:
    def __init__(self):
        self.connection = None
        self.use_sqlite = os.getenv('USE_SQLITE', 'true').lower() == 'true'
        self.connect()
    
    def connect(self):
        try:
            if self.use_sqlite:
                self.connection = sqlite3.connect('tripspark.db', check_same_thread=False)
                self.connection.row_factory = sqlite3.Row
                self._init_database()
                print("✅ Connected to SQLite database")
            else:
                import mysql.connector
                self.connection = mysql.connector.connect(
                    host=os.getenv('DB_HOST', 'localhost'),
                    user=os.getenv('DB_USER', 'root'),
                    password=os.getenv('DB_PASSWORD', ''),
                    database=os.getenv('DB_NAME', 'tripspark'),
                    port=os.getenv('DB_PORT', '3306')
                )
                self._init_database()
                print("✅ Connected to MySQL database")
        except Exception as e:
            print(f"❌ Database connection error: {e}")
            print("🔄 Using in-memory data storage")
            self.connection = None
    
    def _init_database(self):
        """Initialize database tables and sample data"""
        if not self.connection:
            return
            
        cursor = self.connection.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                preferences TEXT,
                travel_history TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pois (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                tags TEXT NOT NULL,
                budget TEXT NOT NULL CHECK (budget IN ('low', 'medium', 'high')),
                location TEXT NOT NULL,
                city TEXT NOT NULL,
                country TEXT NOT NULL,
                coordinates TEXT,
                rating REAL,
                price_level INTEGER,
                popularity INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recommendations (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                destination TEXT NOT NULL,
                vibes TEXT NOT NULL,
                budget TEXT NOT NULL,
                pois TEXT NOT NULL,
                itinerary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        cursor.execute("SELECT COUNT(*) FROM pois")
        if cursor.fetchone()[0] == 0:
            self._insert_sample_pois(cursor)
        
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            self._insert_sample_users(cursor)
        
        self.connection.commit()
        cursor.close()
    
    def _insert_sample_pois(self, cursor):
        """Insert sample Points of Interest"""
        sample_pois = [
            ('poi_ny_1', 'Central Perk Cafe', 'Cozy coffee shop inspired by Friends', 
             '["coffee", "cozy", "breakfast", "cafe"]', 'medium', 'Manhattan', 'New York', 'USA',
             '{"lat": 40.7128, "lng": -74.0060}', 4.5, 2, 85),
            
            ('poi_ny_2', 'Metropolitan Museum of Art', 'World-class art museum', 
             '["museums", "art", "history", "culture"]', 'high', 'Manhattan', 'New York', 'USA',
             '{"lat": 40.7794, "lng": -73.9632}', 4.8, 3, 92),
            
            ('poi_ny_3', 'Brooklyn Bridge Park', 'Beautiful waterfront park with amazing views', 
             '["outdoors", "walks", "views", "parks"]', 'low', 'Brooklyn', 'New York', 'USA',
             '{"lat": 40.7021, "lng": -73.9963}', 4.7, 1, 78),
            
            ('poi_ny_4', 'Chelsea Market', 'Indoor food hall and shopping mall', 
             '["food", "shopping", "coffee", "restaurants"]', 'medium', 'Manhattan', 'New York', 'USA',
             '{"lat": 40.7420, "lng": -74.0060}', 4.4, 2, 81),
            
            ('poi_paris_1', 'Eiffel Tower', 'Iconic iron tower and landmark', 
             '["landmark", "views", "romantic", "architecture"]', 'medium', '7th Arrondissement', 'Paris', 'France',
             '{"lat": 48.8584, "lng": 2.2945}', 4.7, 2, 95),
            
            ('poi_paris_2', 'Louvre Museum', 'World\'s largest art museum', 
             '["museums", "art", "history", "culture"]', 'medium', '1st Arrondissement', 'Paris', 'France',
             '{"lat": 48.8606, "lng": 2.3376}', 4.6, 2, 89),
            
            ('poi_paris_3', 'Montmartre District', 'Historic artistic neighborhood', 
             '["art", "walks", "historic", "views"]', 'low', '18th Arrondissement', 'Paris', 'France',
             '{"lat": 48.8867, "lng": 2.3431}', 4.5, 1, 76),
            
            ('poi_tokyo_1', 'Senso-ji Temple', 'Ancient Buddhist temple', 
             '["temples", "historic", "culture", "architecture"]', 'low', 'Asakusa', 'Tokyo', 'Japan',
             '{"lat": 35.7148, "lng": 139.7967}', 4.4, 1, 82),
            
            ('poi_tokyo_2', 'Shibuya Crossing', 'Famous busy pedestrian crossing', 
             '["shopping", "urban", "landmark", "entertainment"]', 'low', 'Shibuya', 'Tokyo', 'Japan',
             '{"lat": 35.6595, "lng": 139.7004}', 4.3, 1, 88),
            
            ('poi_tokyo_3', 'Tsukiji Outer Market', 'Fresh seafood and food market', 
             '["food", "markets", "seafood", "local"]', 'medium', 'Chuo City', 'Tokyo', 'Japan',
             '{"lat": 35.6655, "lng": 139.7704}', 4.6, 2, 79)
        ]
        
        cursor.executemany('''
            INSERT INTO pois (id, name, description, tags, budget, location, city, country, coordinates, rating, price_level, popularity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_pois)
    
    def _insert_sample_users(self, cursor):
        """Insert sample users"""
        import hashlib
        sample_users = [
            ('user_1', 'traveler_john', 'john@email.com', 
             hashlib.sha256('password123'.encode()).hexdigest(),
             '{"preferred_budget": "medium", "interests": ["museums", "food", "art"]}',
             '["New York", "Paris"]'),
            
            ('user_2', 'adventure_amy', 'amy@email.com',
             hashlib.sha256('password123'.encode()).hexdigest(),
             '{"preferred_budget": "low", "interests": ["outdoors", "walks", "views"]}',
             '["Tokyo", "London"]'),
            
            ('user_3', 'luxury_tom', 'tom@email.com',
             hashlib.sha256('password123'.encode()).hexdigest(),
             '{"preferred_budget": "high", "interests": ["luxury", "fine dining", "shopping"]}',
             '["Paris", "Dubai"]')
        ]
        
        cursor.executemany('''
            INSERT INTO users (id, username, email, password_hash, preferences, travel_history)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', sample_users)
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        if not self.connection:
            return self._get_mock_user(user_id)
            
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        cursor.close()
        
        if row:
            user = dict(row)
            for field in ['preferences', 'travel_history']:
                if field in user and user[field]:
                    user[field] = json.loads(user[field])
            return user
        return None
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        if not self.connection:
            return None
            
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        cursor.close()
        
        if row:
            user = dict(row)
            for field in ['preferences', 'travel_history']:
                if field in user and user[field]:
                    user[field] = json.loads(user[field])
            return user
        return None
    
    def create_user(self, user_data: Dict[str, Any]) -> str:
        """Create new user"""
        if not self.connection:
            return user_data['id']
            
        cursor = self.connection.cursor()
        cursor.execute(
            "INSERT INTO users (id, username, email, password_hash, preferences, travel_history) VALUES (?, ?, ?, ?, ?, ?)",
            (user_data['id'], user_data['username'], user_data['email'], 
             user_data['password_hash'], 
             json.dumps(user_data.get('preferences', {})),
             json.dumps(user_data.get('travel_history', [])))
        )
        self.connection.commit()
        cursor.close()
        return user_data['id']
    
    def get_pois_by_filters(self, tags: List[str] = None, budget: str = None, 
                           location: str = None, city: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get POIs with advanced filtering"""
        if not self.connection:
            return self._get_mock_pois(tags, budget, location)
        
        cursor = self.connection.cursor()
        
        query = "SELECT * FROM pois WHERE 1=1"
        params = []
        
        if tags:
            tag_conditions = []
            for tag in tags:
                tag_conditions.append("tags LIKE ?")
                params.append(f'%"{tag}"%')
            query += f" AND ({' OR '.join(tag_conditions)})"
        
        if budget:
            query += " AND budget = ?"
            params.append(budget)
            
        if location:
            query += " AND location LIKE ?"
            params.append(f"%{location}%")
            
        if city:
            query += " AND city LIKE ?"
            params.append(f"%{city}%")
        
        query += " ORDER BY popularity DESC, rating DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        
        pois = []
        for row in rows:
            poi = dict(row)
            if 'tags' in poi and isinstance(poi['tags'], str):
                poi['tags'] = json.loads(poi['tags'])
            if 'coordinates' in poi and isinstance(poi['coordinates'], str):
                poi['coordinates'] = json.loads(poi['coordinates'])
            pois.append(poi)
        
        return pois
    
    def get_poi_by_id(self, poi_id: str) -> Optional[Dict[str, Any]]:
        """Get specific POI by ID"""
        if not self.connection:
            return None
            
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM pois WHERE id = ?", (poi_id,))
        row = cursor.fetchone()
        cursor.close()
        
        if row:
            poi = dict(row)
            if 'tags' in poi and isinstance(poi['tags'], str):
                poi['tags'] = json.loads(poi['tags'])
            if 'coordinates' in poi and isinstance(poi['coordinates'], str):
                poi['coordinates'] = json.loads(poi['coordinates'])
            return poi
        return None
    
    def save_recommendation(self, recommendation_data: Dict[str, Any]) -> str:
        """Save recommendation to database"""
        if not self.connection:
            return recommendation_data['id']
            
        cursor = self.connection.cursor()
        cursor.execute(
            """INSERT INTO recommendations 
            (id, user_id, destination, vibes, budget, pois, itinerary) 
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (recommendation_data['id'], recommendation_data['user_id'], 
             recommendation_data['destination'], json.dumps(recommendation_data['vibes']),
             recommendation_data['budget'], json.dumps(recommendation_data['pois']),
             json.dumps(recommendation_data.get('itinerary', {})))
        )
        self.connection.commit()
        cursor.close()
        return recommendation_data['id']
    
    def get_recommendation(self, recommendation_id: str) -> Optional[Dict[str, Any]]:
        """Get recommendation by ID"""
        if not self.connection:
            return None
            
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM recommendations WHERE id = ?", (recommendation_id,))
        row = cursor.fetchone()
        cursor.close()
        
        if row:
            rec = dict(row)
            for field in ['vibes', 'pois', 'itinerary']:
                if field in rec and isinstance(rec[field], str):
                    rec[field] = json.loads(rec[field])
            return rec
        return None
    
    def get_user_recommendations(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get all recommendations for a user"""
        if not self.connection:
            return []
            
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT * FROM recommendations WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        rows = cursor.fetchall()
        cursor.close()
        
        recommendations = []
        for row in rows:
            rec = dict(row)
            for field in ['vibes', 'pois', 'itinerary']:
                if field in rec and isinstance(rec[field], str):
                    rec[field] = json.loads(rec[field])
            recommendations.append(rec)
        
        return recommendations
    
    def _get_mock_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        mock_users = {
            'user_1': {
                'id': 'user_1',
                'username': 'traveler_john',
                'email': 'john@email.com',
                'preferences': {'preferred_budget': 'medium', 'interests': ['museums', 'food', 'art']},
                'travel_history': ['New York', 'Paris']
            }
        }
        return mock_users.get(user_id)
    
    def _get_mock_pois(self, tags: List[str] = None, budget: str = None, 
                      location: str = None) -> List[Dict[str, Any]]:
        return []

db = Database()