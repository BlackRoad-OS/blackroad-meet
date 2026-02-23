"""
BlackRoad Meet - Video meeting/conferencing backend
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Set
import sqlite3
import os
import uuid
from pathlib import Path


@dataclass
class Room:
    """Represents a video meeting room"""
    id: str
    name: str
    host: str
    participants: List[str]
    max_size: int
    status: str  # 'active' or 'ended'
    created_at: datetime
    ended_at: Optional[datetime] = None
    recording_url: str = ""


@dataclass
class Participant:
    """Represents a participant in a video room"""
    id: str
    room_id: str
    user: str
    joined_at: datetime
    left_at: Optional[datetime] = None
    camera_on: bool = True
    mic_on: bool = True


class MeetServer:
    """Main video meeting server"""
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.expanduser("~/.blackroad/meet.db")
        
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()
        self.rooms: Dict[str, Room] = {}
        self.participants: Dict[str, Set[Participant]] = {}
    
    def _init_db(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                max_size INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                ended_at TEXT,
                recording_url TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                id TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                user TEXT NOT NULL,
                joined_at TEXT NOT NULL,
                left_at TEXT,
                camera_on INTEGER NOT NULL,
                mic_on INTEGER NOT NULL,
                FOREIGN KEY(room_id) REFERENCES rooms(id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def create_room(self, name: str, host: str, max_size: int = 50) -> tuple[str, str]:
        """Create a new video room
        
        Returns:
            tuple: (room_id, join_url)
        """
        room_id = str(uuid.uuid4())[:8]
        created_at = datetime.now()
        
        room = Room(
            id=room_id,
            name=name,
            host=host,
            participants=[],
            max_size=max_size,
            status='active',
            created_at=created_at
        )
        
        self.rooms[room_id] = room
        self.participants[room_id] = set()
        
        # Store in DB
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO rooms (id, name, host, max_size, status, created_at, ended_at, recording_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (room_id, name, host, max_size, 'active', created_at.isoformat(), None, ''))
        conn.commit()
        conn.close()
        
        join_url = f"https://meet.blackroad.io/r/{room_id}"
        return room_id, join_url
    
    def join_room(self, room_id: str, user: str) -> bool:
        """Add participant to room
        
        Returns:
            bool: True if successful, False if room full or not found
        """
        if room_id not in self.rooms:
            return False
        
        room = self.rooms[room_id]
        if len(room.participants) >= room.max_size:
            return False
        
        participant_id = str(uuid.uuid4())[:8]
        joined_at = datetime.now()
        
        participant = Participant(
            id=participant_id,
            room_id=room_id,
            user=user,
            joined_at=joined_at,
            camera_on=True,
            mic_on=True
        )
        
        room.participants.append(user)
        self.participants[room_id].add(participant)
        
        # Store in DB
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO participants (id, room_id, user, joined_at, left_at, camera_on, mic_on)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (participant_id, room_id, user, joined_at.isoformat(), None, 1, 1))
        conn.commit()
        conn.close()
        
        return True
    
    def leave_room(self, room_id: str, user: str) -> bool:
        """Remove participant from room"""
        if room_id not in self.rooms:
            return False
        
        room = self.rooms[room_id]
        if user not in room.participants:
            return False
        
        room.participants.remove(user)
        left_at = datetime.now()
        
        # Update DB
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE participants SET left_at = ?
            WHERE room_id = ? AND user = ? AND left_at IS NULL
        """, (left_at.isoformat(), room_id, user))
        conn.commit()
        conn.close()
        
        return True
    
    def toggle_media(self, room_id: str, user: str, camera: Optional[bool] = None, mic: Optional[bool] = None) -> bool:
        """Toggle user's camera and/or microphone"""
        if room_id not in self.rooms:
            return False
        
        for participant in self.participants.get(room_id, set()):
            if participant.user == user:
                if camera is not None:
                    participant.camera_on = camera
                if mic is not None:
                    participant.mic_on = mic
                return True
        
        return False
    
    def end_room(self, room_id: str, recording_url: str = "") -> bool:
        """End a meeting room"""
        if room_id not in self.rooms:
            return False
        
        room = self.rooms[room_id]
        room.status = 'ended'
        room.ended_at = datetime.now()
        room.recording_url = recording_url
        
        # Update DB
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE rooms SET status = ?, ended_at = ?, recording_url = ?
            WHERE id = ?
        """, ('ended', room.ended_at.isoformat(), recording_url, room_id))
        conn.commit()
        conn.close()
        
        return True
    
    def get_room(self, room_id: str) -> Optional[Dict]:
        """Get room info with participant list and duration"""
        if room_id not in self.rooms:
            return None
        
        room = self.rooms[room_id]
        duration = None
        if room.ended_at:
            duration = int((room.ended_at - room.created_at).total_seconds() / 60)
        
        return {
            'id': room.id,
            'name': room.name,
            'host': room.host,
            'participants': room.participants,
            'max_size': room.max_size,
            'status': room.status,
            'created_at': room.created_at.isoformat(),
            'ended_at': room.ended_at.isoformat() if room.ended_at else None,
            'recording_url': room.recording_url,
            'duration_minutes': duration
        }
    
    def get_active_rooms(self) -> List[Dict]:
        """Get list of live meetings"""
        return [self.get_room(rid) for rid in self.rooms 
                if self.rooms[rid].status == 'active']
    
    def get_user_history(self, user: str, n: int = 10) -> List[Dict]:
        """Get past meetings for a user"""
        history = []
        for room in self.rooms.values():
            if user in room.participants and room.status == 'ended':
                history.append(self.get_room(room.id))
        return sorted(history, key=lambda x: x['created_at'], reverse=True)[:n]
    
    def room_stats(self, room_id: str) -> Optional[Dict]:
        """Get room statistics"""
        if room_id not in self.rooms:
            return None
        
        room = self.rooms[room_id]
        peak_participants = len(room.participants)
        duration = 0
        if room.ended_at:
            duration = int((room.ended_at - room.created_at).total_seconds() / 60)
        
        # Count join events from DB
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM participants WHERE room_id = ?
        """, (room_id,))
        join_events = cursor.fetchone()[0]
        conn.close()
        
        return {
            'peak_participants': peak_participants,
            'duration_min': duration,
            'join_events': join_events
        }


if __name__ == '__main__':
    import sys
    
    server = MeetServer()
    
    if len(sys.argv) < 2:
        print("Usage: python meet_server.py <command> [args]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == 'create':
        name = sys.argv[2]
        host = sys.argv[3]
        max_size = 50
        if '--max' in sys.argv:
            max_size = int(sys.argv[sys.argv.index('--max') + 1])
        
        room_id, join_url = server.create_room(name, host, max_size)
        print(f"Room created: {room_id}")
        print(f"Join URL: {join_url}")
    
    elif cmd == 'rooms':
        active = server.get_active_rooms()
        for room in active:
            print(f"[{room['id']}] {room['name']} (host: {room['host']}, participants: {len(room['participants'])}/{room['max_size']})")
    
    elif cmd == 'join':
        room_id = sys.argv[2]
        user = sys.argv[3]
        if server.join_room(room_id, user):
            print(f"User {user} joined room {room_id}")
        else:
            print(f"Failed to join room {room_id}")
