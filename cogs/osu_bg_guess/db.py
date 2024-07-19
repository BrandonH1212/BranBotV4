import sqlite3
from typing import List, Tuple, Optional

class BgGameDatabase:
    _instance: Optional['BgGameDatabase'] = None
    def __init__(self) -> None:
        self.conn: sqlite3.Connection = sqlite3.connect('cogs/osu_bg_guess/bg_game.db')
        self.c: sqlite3.Cursor = self.conn.cursor()
        
        self.c.execute('''CREATE TABLE IF NOT EXISTS users
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                        discord_id INTEGER UNIQUE,
                        osu_id INTEGER)''')
        
        self.c.execute('''CREATE INDEX IF NOT EXISTS idx_users_osu_id ON users(osu_id)''')
        
        self.c.execute('''CREATE TABLE IF NOT EXISTS play_history
                    (osu_id INTEGER,
                    mapset_id INTEGER,
                    PRIMARY KEY (osu_id, mapset_id))''')
        
        self.conn.commit()
    
    def add_play_history_batch(self, play_data: List[Tuple[int, int]]) -> None:
        self.c.executemany("INSERT OR IGNORE INTO play_history (osu_id, mapset_id) VALUES (?, ?)", play_data)
        self.conn.commit()

    def get_common_sets(self, osu_ids: List[int]) -> List[int]:
        placeholders = ','.join('?' for _ in osu_ids)
        self.c.execute(f'''
            SELECT DISTINCT osu_id 
            FROM users 
            WHERE osu_id IN ({placeholders})
        ''', osu_ids)
        
        valid_osu_ids = [row[0] for row in self.c.fetchall()]
        
        if not valid_osu_ids:
            return []
        
        placeholders = ','.join('?' for _ in valid_osu_ids)

        if len(valid_osu_ids) == 1:
            query = f'''
            SELECT DISTINCT mapset_id
            FROM play_history
            WHERE osu_id = ?
            '''
            self.c.execute(query, valid_osu_ids)
        else:
            query = f'''
            SELECT mapset_id
            FROM play_history
            WHERE osu_id IN ({placeholders})
            GROUP BY mapset_id
            HAVING COUNT(DISTINCT osu_id) = ?
            '''
            self.c.execute(query, valid_osu_ids + [len(valid_osu_ids)])
        
        return [row[0] for row in self.c.fetchall()]

    def add_user(self, discord_id: int, osu_id: int) -> None:
        self.c.execute('''INSERT OR REPLACE INTO users (discord_id, osu_id)
                        VALUES (?, ?)''', (discord_id, osu_id))
        self.conn.commit()
    
    def get_user(self, discord_id: int) -> Optional[Tuple[int, int, int]]:
        self.c.execute("SELECT id, discord_id, osu_id FROM users WHERE discord_id = ?", (discord_id,))
        return self.c.fetchone()
    
    def get_all_sets(self) -> List[int]:
        self.c.execute("SELECT DISTINCT mapset_id FROM play_history")
        return [row[0] for row in self.c.fetchall()]

    def get_osu_ids_from_discord(self, discord_ids: List[int]) -> List[int]:
        placeholders = ','.join('?' for _ in discord_ids)
        self.c.execute(f'''
            SELECT osu_id
            FROM users
            WHERE discord_id IN ({placeholders})
        ''', discord_ids)
        return [row[0] for row in self.c.fetchall()]

    def close(self) -> None:
        self.conn.close()
        
    @classmethod
    def get_instance(cls) -> 'BgGameDatabase':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

game_db = BgGameDatabase.get_instance()