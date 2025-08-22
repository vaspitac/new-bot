import sqlite3
import json
import os
import logging
from typing import Dict, List, Optional, Tuple
import asyncio
import aiosqlite

class DatabaseManager:
    def __init__(self, db_path: str = "bot_database.db"):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        
    async def initialize_database(self):
        """Initialize the database with required tables"""
        async with aiosqlite.connect(self.db_path) as db:
            # Server configurations table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS server_configs (
                    guild_id INTEGER PRIMARY KEY,
                    helper_role_id INTEGER,
                    viewer_role_id INTEGER,
                    blocked_role_id INTEGER,
                    ticket_category_id INTEGER,
                    transcript_channel_id INTEGER,
                    guidelines_channel_id INTEGER,
                    setup_completed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Admin roles table (many-to-many relationship)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS admin_roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    role_id INTEGER,
                    FOREIGN KEY (guild_id) REFERENCES server_configs (guild_id),
                    UNIQUE(guild_id, role_id)
                )
            """)
            
            # Point values table (server-specific point configurations)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS point_values (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    service_name TEXT,
                    points INTEGER,
                    FOREIGN KEY (guild_id) REFERENCES server_configs (guild_id),
                    UNIQUE(guild_id, service_name)
                )
            """)
            
            # Helper slots table (server-specific helper slot configurations)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS helper_slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    service_name TEXT,
                    slots INTEGER,
                    FOREIGN KEY (guild_id) REFERENCES server_configs (guild_id),
                    UNIQUE(guild_id, service_name)
                )
            """)
            
            # User points table (server-specific user points)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    user_id INTEGER,
                    points INTEGER DEFAULT 0,
                    FOREIGN KEY (guild_id) REFERENCES server_configs (guild_id),
                    UNIQUE(guild_id, user_id)
                )
            """)
            
            # Ticket numbers table (server-specific ticket counters)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ticket_numbers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    category TEXT,
                    current_number INTEGER DEFAULT 0,
                    FOREIGN KEY (guild_id) REFERENCES server_configs (guild_id),
                    UNIQUE(guild_id, category)
                )
            """)
            
            # Custom rules table (server-specific rule customizations)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS custom_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    rule_type TEXT,
                    content TEXT,
                    FOREIGN KEY (guild_id) REFERENCES server_configs (guild_id),
                    UNIQUE(guild_id, rule_type)
                )
            """)
            
            await db.commit()
            self.logger.info("Database initialized successfully")
    
    async def get_server_config(self, guild_id: int) -> Optional[Dict]:
        """Get server configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT * FROM server_configs WHERE guild_id = ?", 
                (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    columns = [description[0] for description in cursor.description]
                    return dict(zip(columns, row))
                return None
    
    async def update_server_config(self, guild_id: int, **kwargs):
        """Update server configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            # Check if config exists
            config = await self.get_server_config(guild_id)
            if config:
                # Update existing config
                set_clause = ", ".join([f"{key} = ?" for key in kwargs.keys()])
                values = list(kwargs.values()) + [guild_id]
                await db.execute(
                    f"UPDATE server_configs SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ?",
                    values
                )
            else:
                # Insert new config
                columns = ["guild_id"] + list(kwargs.keys())
                placeholders = ", ".join(["?"] * len(columns))
                values = [guild_id] + list(kwargs.values())
                await db.execute(
                    f"INSERT INTO server_configs ({', '.join(columns)}) VALUES ({placeholders})",
                    values
                )
            await db.commit()
    
    async def get_admin_roles(self, guild_id: int) -> List[int]:
        """Get admin roles for a server"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT role_id FROM admin_roles WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
    
    async def set_admin_roles(self, guild_id: int, role_ids: List[int]):
        """Set admin roles for a server"""
        async with aiosqlite.connect(self.db_path) as db:
            # Clear existing admin roles
            await db.execute("DELETE FROM admin_roles WHERE guild_id = ?", (guild_id,))
            # Insert new admin roles
            for role_id in role_ids:
                await db.execute(
                    "INSERT INTO admin_roles (guild_id, role_id) VALUES (?, ?)",
                    (guild_id, role_id)
                )
            await db.commit()
    
    async def get_point_values(self, guild_id: int) -> Dict[str, int]:
        """Get point values for a server"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT service_name, points FROM point_values WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return {row[0]: row[1] for row in rows}
    
    async def set_point_values(self, guild_id: int, point_values: Dict[str, int]):
        """Set point values for a server"""
        async with aiosqlite.connect(self.db_path) as db:
            # Clear existing point values
            await db.execute("DELETE FROM point_values WHERE guild_id = ?", (guild_id,))
            # Insert new point values
            for service_name, points in point_values.items():
                await db.execute(
                    "INSERT INTO point_values (guild_id, service_name, points) VALUES (?, ?, ?)",
                    (guild_id, service_name, points)
                )
            await db.commit()
    
    async def get_helper_slots(self, guild_id: int) -> Dict[str, int]:
        """Get helper slots for a server"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT service_name, slots FROM helper_slots WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return {row[0]: row[1] for row in rows}
    
    async def set_helper_slots(self, guild_id: int, helper_slots: Dict[str, int]):
        """Set helper slots for a server"""
        async with aiosqlite.connect(self.db_path) as db:
            # Clear existing helper slots
            await db.execute("DELETE FROM helper_slots WHERE guild_id = ?", (guild_id,))
            # Insert new helper slots
            for service_name, slots in helper_slots.items():
                await db.execute(
                    "INSERT INTO helper_slots (guild_id, service_name, slots) VALUES (?, ?, ?)",
                    (guild_id, service_name, slots)
                )
            await db.commit()
    
    async def get_user_points(self, guild_id: int, user_id: int) -> int:
        """Get points for a specific user"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT points FROM user_points WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
    
    async def update_user_points(self, guild_id: int, user_id: int, points: int):
        """Update points for a specific user"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO user_points (guild_id, user_id, points) 
                   VALUES (?, ?, ?) 
                   ON CONFLICT(guild_id, user_id) 
                   DO UPDATE SET points = ?""",
                (guild_id, user_id, points, points)
            )
            await db.commit()
    
    async def add_user_points(self, guild_id: int, user_id: int, amount: int):
        """Add points to a specific user (existing points + amount)"""
        current_points = await self.get_user_points(guild_id, user_id)
        new_points = current_points + amount
        await self.update_user_points(guild_id, user_id, new_points)
    
    async def set_user_points(self, guild_id: int, user_id: int, points: int):
        """Set specific points for a user (alias for update_user_points)"""
        await self.update_user_points(guild_id, user_id, points)
    
    async def get_all_user_points(self, guild_id: int) -> Dict[int, int]:
        """Get all user points for a server"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT user_id, points FROM user_points WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return {row[0]: row[1] for row in rows}
    
    async def get_next_ticket_number(self, guild_id: int, category: str) -> int:
        """Get next ticket number for a category"""
        async with aiosqlite.connect(self.db_path) as db:
            # Get current number
            async with db.execute(
                "SELECT current_number FROM ticket_numbers WHERE guild_id = ? AND category = ?",
                (guild_id, category)
            ) as cursor:
                row = await cursor.fetchone()
                current_num = row[0] if row else 0
            
            # Increment and update
            new_num = current_num + 1
            await db.execute(
                """INSERT INTO ticket_numbers (guild_id, category, current_number) 
                   VALUES (?, ?, ?) 
                   ON CONFLICT(guild_id, category) 
                   DO UPDATE SET current_number = ?""",
                (guild_id, category, new_num, new_num)
            )
            await db.commit()
            return new_num
    
    async def reset_ticket_number(self, guild_id: int, category: str):
        """Reset ticket number for a category"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO ticket_numbers (guild_id, category, current_number) 
                   VALUES (?, ?, 0) 
                   ON CONFLICT(guild_id, category) 
                   DO UPDATE SET current_number = 0""",
                (guild_id, category)
            )
            await db.commit()
    
    async def get_custom_rule(self, guild_id: int, rule_type: str) -> Optional[str]:
        """Get custom rule content"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT content FROM custom_rules WHERE guild_id = ? AND rule_type = ?",
                (guild_id, rule_type)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
    
    async def set_custom_rule(self, guild_id: int, rule_type: str, content: str):
        """Set custom rule content"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO custom_rules (guild_id, rule_type, content) 
                   VALUES (?, ?, ?) 
                   ON CONFLICT(guild_id, rule_type) 
                   DO UPDATE SET content = ?""",
                (guild_id, rule_type, content, content)
            )
            await db.commit()
