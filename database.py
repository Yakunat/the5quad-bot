import sqlite3
import datetime
from typing import List, Tuple, Optional

class FootballDatabase:
    def __init__(self, db_name: str = "football_bot.db"):
        self.db_name = db_name
        self.init_database()
    
    def init_database(self):
        """Create tables if they don't exist."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            # Events table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    time TEXT NOT NULL,
                    max_players INTEGER NOT NULL,
                    description TEXT,
                    created_by INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active'
                )
            ''')
            
            # Registrations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS registrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    registration_type TEXT NOT NULL DEFAULT 'main',
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    FOREIGN KEY (event_id) REFERENCES events (id),
                    UNIQUE(event_id, user_id)
                )
            ''')
            
            conn.commit()
    
    def create_event(self, date: str, time: str, max_players: int, created_by: int, description: str = "") -> int:
        """Create a new football event. Returns event ID."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO events (date, time, max_players, description, created_by)
                VALUES (?, ?, ?, ?, ?)
            ''', (date, time, max_players, description, created_by))
            conn.commit()
            return cursor.lastrowid
    
    def get_active_events(self) -> List[Tuple]:
        """Get all active events."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, date, time, max_players, description, created_by, created_at
                FROM events 
                WHERE status = 'active'
                ORDER BY date, time
            ''')
            return cursor.fetchall()
    
    def get_event(self, event_id: int) -> Optional[Tuple]:
        """Get a specific event by ID."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, date, time, max_players, description, created_by, created_at, status
                FROM events 
                WHERE id = ?
            ''', (event_id,))
            return cursor.fetchone()
    
    def register_user(self, event_id: int, user_id: int, username: str, first_name: str) -> bool:
        """Register a user for an event. Returns True if successful."""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                
                # Check if user is already registered
                cursor.execute('''
                    SELECT id FROM registrations 
                    WHERE event_id = ? AND user_id = ? AND status = 'active'
                ''', (event_id, user_id))
                
                if cursor.fetchone():
                    return False  # Already registered
                
                # Count current registrations
                cursor.execute('''
                    SELECT COUNT(*) FROM registrations 
                    WHERE event_id = ? AND registration_type = 'main' AND status = 'active'
                ''', (event_id,))
                main_count = cursor.fetchone()[0]
                
                # Get max players for this event
                cursor.execute('SELECT max_players FROM events WHERE id = ?', (event_id,))
                max_players = cursor.fetchone()[0]
                
                # Determine registration type
                reg_type = 'main' if main_count < max_players else 'reserve'
                
                # Register the user
                cursor.execute('''
                    INSERT INTO registrations (event_id, user_id, username, first_name, registration_type)
                    VALUES (?, ?, ?, ?, ?)
                ''', (event_id, user_id, username, first_name, reg_type))
                
                conn.commit()
                return True
                
        except sqlite3.IntegrityError:
            return False  # User already registered
    
    def unregister_user(self, event_id: int, user_id: int) -> bool:
        """Unregister a user from an event. Returns True if successful."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            # Get user's current registration
            cursor.execute('''
                SELECT registration_type FROM registrations 
                WHERE event_id = ? AND user_id = ? AND status = 'active'
            ''', (event_id, user_id))
            
            result = cursor.fetchone()
            if not result:
                return False  # User not registered
            
            user_reg_type = result[0]
            
            # Remove user
            cursor.execute('''
                UPDATE registrations 
                SET status = 'cancelled' 
                WHERE event_id = ? AND user_id = ? AND status = 'active'
            ''', (event_id, user_id))
            
            # If user was in main list, promote someone from reserve
            if user_reg_type == 'main':
                cursor.execute('''
                    SELECT user_id FROM registrations 
                    WHERE event_id = ? AND registration_type = 'reserve' AND status = 'active'
                    ORDER BY registered_at 
                    LIMIT 1
                ''', (event_id,))
                
                next_user = cursor.fetchone()
                if next_user:
                    cursor.execute('''
                        UPDATE registrations 
                        SET registration_type = 'main' 
                        WHERE event_id = ? AND user_id = ? AND status = 'active'
                    ''', (event_id, next_user[0]))
            
            conn.commit()
            return True
    
    def get_event_registrations(self, event_id: int) -> dict:
        """Get all registrations for an event, organized by type."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, username, first_name, registration_type, registered_at
                FROM registrations 
                WHERE event_id = ? AND status = 'active'
                ORDER BY registration_type, registered_at
            ''', (event_id,))
            
            registrations = cursor.fetchall()
            
            result = {
                'main': [],
                'reserve': []
            }
            
            for reg in registrations:
                user_id, username, first_name, reg_type, registered_at = reg
                user_info = {
                    'user_id': user_id,
                    'username': username,
                    'first_name': first_name,
                    'registered_at': registered_at
                }
                result[reg_type].append(user_info)
            
            return result
    
    def get_user_registrations(self, user_id: int) -> List[Tuple]:
        """Get all active registrations for a user."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT e.id, e.date, e.time, r.registration_type
                FROM events e
                JOIN registrations r ON e.id = r.event_id
                WHERE r.user_id = ? AND r.status = 'active' AND e.status = 'active'
                ORDER BY e.date, e.time
            ''', (user_id,))
            return cursor.fetchall()
    
    def cancel_event(self, event_id: int) -> bool:
        """Cancel an event."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE events 
                SET status = 'cancelled' 
                WHERE id = ?
            ''', (event_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_players_for_teams(self, event_id: int) -> List[dict]:
        """Get all main list players for team assignment."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, username, first_name
                FROM registrations 
                WHERE event_id = ? AND registration_type = 'main' AND status = 'active'
                ORDER BY registered_at
            ''', (event_id,))
            
            players = []
            for user_id, username, first_name in cursor.fetchall():
                players.append({
                    'user_id': user_id,
                    'username': username,
                    'first_name': first_name,
                    'display_name': first_name or username or str(user_id)
                })
            
            return players