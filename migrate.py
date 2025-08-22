import json
import os
import asyncio
import logging
from database import DatabaseManager

class DataMigrator:
    def __init__(self):
        self.db = DatabaseManager()
        self.logger = logging.getLogger(__name__)
        
    async def migrate_json_data(self, guild_id: int):
        """Migrate existing JSON data to database for a specific guild"""
        self.logger.info(f"Starting migration for guild {guild_id}")
        
        # Create backup before migration
        await self.create_backup()
        
        # Migrate points data
        await self.migrate_points(guild_id)
        
        # Migrate ticket numbers
        await self.migrate_ticket_numbers(guild_id)
        
        self.logger.info(f"Migration completed for guild {guild_id}")
    
    async def create_backup(self):
        """Create backup of existing JSON files"""
        backup_dir = "backup"
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        
        files_to_backup = ["points.json", "ticket_numbers.json"]
        
        for filename in files_to_backup:
            if os.path.exists(filename):
                import shutil
                backup_path = os.path.join(backup_dir, f"{filename}.backup")
                shutil.copy2(filename, backup_path)
                self.logger.info(f"Backed up {filename} to {backup_path}")
    
    async def migrate_points(self, guild_id: int):
        """Migrate points.json to database"""
        if os.path.exists("points.json"):
            try:
                with open("points.json", "r") as f:
                    points_data = json.load(f)
                
                # Convert string user IDs to integers and migrate
                for user_id_str, points in points_data.items():
                    try:
                        user_id = int(user_id_str)
                        await self.db.update_user_points(guild_id, user_id, points)
                    except ValueError:
                        self.logger.warning(f"Invalid user ID: {user_id_str}")
                
                self.logger.info(f"Migrated {len(points_data)} user points records")
                
            except (json.JSONDecodeError, FileNotFoundError) as e:
                self.logger.error(f"Error migrating points: {e}")
    
    async def migrate_ticket_numbers(self, guild_id: int):
        """Migrate ticket_numbers.json to database"""
        if os.path.exists("ticket_numbers.json"):
            try:
                with open("ticket_numbers.json", "r") as f:
                    ticket_data = json.load(f)
                
                for category, number in ticket_data.items():
                    await self.db.execute(
                        """INSERT INTO ticket_numbers (guild_id, category, current_number) 
                           VALUES (?, ?, ?) 
                           ON CONFLICT(guild_id, category) 
                           DO UPDATE SET current_number = ?""",
                        (guild_id, category, number, number)
                    )
                
                self.logger.info(f"Migrated {len(ticket_data)} ticket number records")
                
            except (json.JSONDecodeError, FileNotFoundError) as e:
                self.logger.error(f"Error migrating ticket numbers: {e}")
    
    async def set_default_configuration(self, guild_id: int):
        """Set default configuration for a guild"""
        # Default point values
        default_point_values = {
            "Ultra Speaker Express": 8,
            "Ultra Gramiel Express": 7,
            "4-Man Ultra Daily Express": 4,
            "7-Man Ultra Daily Express": 7,
            "Ultra Weekly Express": 12,
            "Grim Express": 10,
            "Daily Temple Express": 6
        }
        
        # Default helper slots
        default_helper_slots = {
            "7-Man Ultra Daily Express": 6,
            "Grim Express": 6
        }
        
        await self.db.set_point_values(guild_id, default_point_values)
        await self.db.set_helper_slots(guild_id, default_helper_slots)
        
        # Set default rules
        default_hrules = """📥Ticket Rules for Helpers📥
⚔️ Respect Comes First
Toxicity, harassment, discrimination, or any disrespectful behavior is not allowed.

🚫 No Ticket-Hopping
You cannot leave a ticket to join another one for better chances or rewards.
The only exception: If your ticket has no available helpers, and another ticket urgently needs help to proceed. In this case, you may assist there so the group can finish and free up helpers for others.

🤖 Botting = Cheating
Using bots, scripts, premium clients or whichever automation tools is considered cheating in-game and is not allowed inside tickets.

🎭 No Trolling
Helpers are not allowed to troll or sabotage under any circumstance. Unlike requestors, skill issue is not a valid excuse. Helpers must be reliable.
Trolling will result in your Helper role being revoked (if confirmed by staff or with valid proof).

📸 Stay for the Screenshot
Leaving before the screenshot means you won't be counted. Helpers must stay until the very end.

⚖️ Use Common Sense
Attempting to exploit loopholes or bend the rules for any reason will be punished without mercy.

🫡 Be a Good Helper
Try your best not to rush other helpers during tickets. Wait till everyone is ready before beginning the fight.
Use meta classes and proper comps for fast and reliable clears.
Adjust to comps:
Example: You are phasing the boss at /Astralshrine and you notice the classes VDK, LR, LOO, LH, CSS, AF are already present. Do not equip VDK and expect the previous wearer to adjust - do it yourself!"""
        
        await self.db.set_custom_rule(guild_id, "helper_rules", default_hrules)
        
        self.logger.info(f"Set default configuration for guild {guild_id}")
