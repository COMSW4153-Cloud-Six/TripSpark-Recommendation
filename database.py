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
        if not self.connection:
            return
        cursor = self.connection.cursor()
        # Users table
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
        # POIs table
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
        self.connection.commit()
        cursor.close()

    def get_pois_by_filters(self, tags: List[str] = None, budget: str = None, location: str = None) -> List[Dict[str, Any]]:
        if not self.connection:
            return []
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

db = Database()
