import discord
from discord.ext import commands
from discord import Embed, ButtonStyle, Interaction
from discord.ui import View, Button, Select, Modal, TextInput
import json, asyncio, os, datetime
import threading
import functools
from dotenv import load_dotenv
from server import start_server
from database import DatabaseManager
from migrate import DataMigrator
import logging

# -------- CONFIG --------
load_dotenv()  # Load .env if it exists
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("ERROR: DISCORD_BOT_TOKEN environment variable not found!")
    exit(1)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default values for fallback
DEFAULT_POINT_VALUES = {
    "Ultra Speaker Express": 8,
    "Ultra Gramiel Express": 7,
    "4-Man Ultra Daily Express": 4,
    "7-Man Ultra Daily Express": 7,
    "Ultra Weekly Express": 12,
    "Grim Express": 10,
    "Daily Temple Express": 6
}

DEFAULT_HELPER_SLOTS = {
    "7-Man Ultra Daily Express": 6,
    "Grim Express": 6
}
DEFAULT_SLOTS = 3

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command('help')

# Initialize database
db = DatabaseManager()
migrator = DataMigrator()

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await db.initialize_database()
    logger.info("Database initialized")

async def get_server_config(guild_id: int):
    """Get server configuration"""
    config = await db.get_server_config(guild_id)
    if not config:
        # Initialize with default configuration using setup system
        await migrator.set_default_configuration(guild_id)
        config = await db.get_server_config(guild_id)
    return config

async def get_point_values(guild_id: int):
    """Get point values for guild with fallback"""
    point_values = await db.get_point_values(guild_id)
    return point_values if point_values else DEFAULT_POINT_VALUES

async def get_helper_slots(guild_id: int):
    """Get helper slots for guild with fallback"""
    helper_slots = await db.get_helper_slots(guild_id)
    return helper_slots if helper_slots else DEFAULT_HELPER_SLOTS

async def get_admin_roles(guild_id: int):
    """Get admin roles for guild"""
    return await db.get_admin_roles(guild_id)

class SetupModal(Modal, title="Basic Bot Setup"):
    def __init__(self):
        super().__init__()
        
    async def on_submit(self, interaction: Interaction):
        await interaction.response.send_message(
            "✅ Setup will continue with role and channel selection...",
            ephemeral=True
        )

class RoleSelect(Select):
    def __init__(self, roles, setup_type, placeholder):
        self.setup_type = setup_type
        options = [
            discord.SelectOption(
                label=role.name,
                value=str(role.id),
                description=f"ID: {role.id}"
            ) for role in roles[:25]  # Discord limit
        ]
        super().__init__(placeholder=placeholder, options=options, max_values=len(options) if setup_type == "admin" else 1)
    
    async def callback(self, interaction: Interaction):
        if self.setup_type == "helper":
            await db.update_server_config(interaction.guild.id, helper_role_id=int(self.values[0]))
            await interaction.response.send_message(f"✅ Helper role set to <@&{self.values[0]}>", ephemeral=True)
        elif self.setup_type == "viewer":
            await db.update_server_config(interaction.guild.id, viewer_role_id=int(self.values[0]))
            await interaction.response.send_message(f"✅ Ticket viewer role set to <@&{self.values[0]}>", ephemeral=True)
        elif self.setup_type == "blocked":
            await db.update_server_config(interaction.guild.id, blocked_role_id=int(self.values[0]))
            await interaction.response.send_message(f"✅ Blocked role set to <@&{self.values[0]}> - users with this role cannot create tickets", ephemeral=True)
        elif self.setup_type == "admin":
            role_ids = [int(role_id) for role_id in self.values]
            await db.set_admin_roles(interaction.guild.id, role_ids)
            role_mentions = " ".join([f"<@&{role_id}>" for role_id in role_ids])
            await interaction.response.send_message(f"✅ Admin roles set to: {role_mentions}", ephemeral=True)

class ChannelSelect(Select):
    def __init__(self, channels, setup_type, placeholder):
        self.setup_type = setup_type
        options = [
            discord.SelectOption(
                label=f"#{channel.name}",
                value=str(channel.id),
                description=f"ID: {channel.id}"
            ) for channel in channels[:25]
        ]
        super().__init__(placeholder=placeholder, options=options)
    
    async def callback(self, interaction: Interaction):
        if self.setup_type == "category":
            await db.update_server_config(interaction.guild.id, ticket_category_id=int(self.values[0]))
            await interaction.response.send_message(f"✅ Ticket category set to <#{self.values[0]}>", ephemeral=True)
        elif self.setup_type == "transcript":
            await db.update_server_config(interaction.guild.id, transcript_channel_id=int(self.values[0]))
            await interaction.response.send_message(f"✅ Transcript channel set to <#{self.values[0]}>", ephemeral=True)
        elif self.setup_type == "guidelines":
            await db.update_server_config(interaction.guild.id, guidelines_channel_id=int(self.values[0]))
            await interaction.response.send_message(f"✅ Guidelines channel set to <#{self.values[0]}>", ephemeral=True)

@bot.command(name="setup")
async def setup_bot(ctx):
    """Interactive bot setup for server administrators"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ You need administrator permissions to run setup.")
        return
    
    embed = Embed(
        title="🔧 Bot Setup",
        description="Choose what you want to configure:",
        color=discord.Color.blue()
    )
    
    view = SetupView(ctx.guild)
    await ctx.send(embed=embed, view=view)

class SetupView(View):
    def __init__(self, guild):
        super().__init__(timeout=300)
        self.guild = guild
    
    @discord.ui.button(label="Helper Role", style=ButtonStyle.primary, emoji="👥")
    async def setup_helper_role(self, interaction: Interaction, button: Button):
        roles = [role for role in self.guild.roles if not role.is_bot_managed() and role != self.guild.default_role]
        if not roles:
            await interaction.response.send_message("❌ No roles found in this server.", ephemeral=True)
            return
        
        view = View()
        view.add_item(RoleSelect(roles, "helper", "Select the helper role"))
        await interaction.response.send_message("Select the role that can join tickets as helpers:", view=view, ephemeral=True)
    
    @discord.ui.button(label="Viewer Role", style=ButtonStyle.primary, emoji="👁️")
    async def setup_viewer_role(self, interaction: Interaction, button: Button):
        roles = [role for role in self.guild.roles if not role.is_bot_managed() and role != self.guild.default_role]
        if not roles:
            await interaction.response.send_message("❌ No roles found in this server.", ephemeral=True)
            return
        
        view = View()
        view.add_item(RoleSelect(roles, "viewer", "Select the ticket viewer role"))
        await interaction.response.send_message("Select the role that can view the ticket category:", view=view, ephemeral=True)
    
    @discord.ui.button(label="Blocked Role", style=ButtonStyle.danger, emoji="🚫")
    async def setup_blocked_role(self, interaction: Interaction, button: Button):
        roles = [role for role in self.guild.roles if not role.is_bot_managed() and role != self.guild.default_role]
        if not roles:
            await interaction.response.send_message("❌ No roles found in this server.", ephemeral=True)
            return
        
        view = View()
        view.add_item(RoleSelect(roles, "blocked", "Select the role that CANNOT create tickets"))
        await interaction.response.send_message("Select the role that should be **blocked** from creating tickets:", view=view, ephemeral=True)
    
    @discord.ui.button(label="Admin Roles", style=ButtonStyle.danger, emoji="🛡️")
    async def setup_admin_roles(self, interaction: Interaction, button: Button):
        roles = [role for role in self.guild.roles if not role.is_bot_managed() and role != self.guild.default_role]
        if not roles:
            await interaction.response.send_message("❌ No roles found in this server.", ephemeral=True)
            return
        
        view = View()
        view.add_item(RoleSelect(roles, "admin", "Select admin roles (can select multiple)"))
        await interaction.response.send_message("Select the roles that can close tickets and perform admin actions:", view=view, ephemeral=True)
    
    @discord.ui.button(label="Ticket Category", style=ButtonStyle.secondary, emoji="📁")
    async def setup_ticket_category(self, interaction: Interaction, button: Button):
        categories = [cat for cat in self.guild.categories]
        if not categories:
            await interaction.response.send_message("❌ No categories found in this server.", ephemeral=True)
            return
        
        view = View()
        view.add_item(ChannelSelect(categories, "category", "Select ticket category"))
        await interaction.response.send_message("Select the category where new tickets will be created:", view=view, ephemeral=True)
    
    @discord.ui.button(label="Transcript Channel", style=ButtonStyle.secondary, emoji="📄")
    async def setup_transcript_channel(self, interaction: Interaction, button: Button):
        text_channels = [ch for ch in self.guild.text_channels]
        if not text_channels:
            await interaction.response.send_message("❌ No text channels found in this server.", ephemeral=True)
            return
        
        view = View()
        view.add_item(ChannelSelect(text_channels, "transcript", "Select transcript channel"))
        await interaction.response.send_message("Select the channel where ticket transcripts will be sent:", view=view, ephemeral=True)
    
    @discord.ui.button(label="Show Config", style=ButtonStyle.success, emoji="📋")
    async def show_config(self, interaction: Interaction, button: Button):
        config = await db.get_server_config(self.guild.id)
        admin_roles = await db.get_admin_roles(self.guild.id)
        
        embed = Embed(title="🔧 Current Configuration", color=discord.Color.green())
        
        if config:
            helper_role = self.guild.get_role(config.get('helper_role_id')) if config.get('helper_role_id') else None
            viewer_role = self.guild.get_role(config.get('viewer_role_id')) if config.get('viewer_role_id') else None
            blocked_role = self.guild.get_role(config.get('blocked_role_id')) if config.get('blocked_role_id') else None
            ticket_category = self.guild.get_channel(config.get('ticket_category_id')) if config.get('ticket_category_id') else None
            transcript_channel = self.guild.get_channel(config.get('transcript_channel_id')) if config.get('transcript_channel_id') else None
            
            embed.add_field(
                name="Helper Role", 
                value=helper_role.mention if helper_role else "❌ Not set", 
                inline=True
            )
            embed.add_field(
                name="Viewer Role", 
                value=viewer_role.mention if viewer_role else "❌ Not set", 
                inline=True
            )
            embed.add_field(
                name="Blocked Role", 
                value=blocked_role.mention if blocked_role else "❌ Not set", 
                inline=True
            )
            embed.add_field(
                name="Ticket Category", 
                value=ticket_category.mention if ticket_category else "❌ Not set", 
                inline=True
            )
            embed.add_field(
                name="Transcript Channel", 
                value=transcript_channel.mention if transcript_channel else "❌ Not set", 
                inline=True
            )
            
            if admin_roles:
                admin_mentions = " ".join([f"<@&{role_id}>" for role_id in admin_roles])
                embed.add_field(name="Admin Roles", value=admin_mentions, inline=False)
            else:
                embed.add_field(name="Admin Roles", value="❌ Not set", inline=False)
        else:
            embed.description = "❌ No configuration found. Please set up the bot first."
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.command(name="migrate")
async def migrate_data(ctx):
    """Migrate existing JSON data to database (Admin only)"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ You need administrator permissions to run migration.")
        return
    
    await ctx.send("🔄 Starting data migration...")
    try:
        await migrator.migrate_json_data(ctx.guild.id)
        await ctx.send("✅ Data migration completed successfully!")
    except Exception as e:
        await ctx.send(f"❌ Migration failed: {str(e)}")
        logger.error(f"Migration failed: {e}")

class TicketDropdown(Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Ultra Speaker Express",
                description="8 points - Premium speaker run",
                emoji="🔊"
            ),
            discord.SelectOption(
                label="Ultra Gramiel Express",
                description="7 points - Ultra Gramiel run",
                emoji="⚔️"
            ),
            discord.SelectOption(
                label="4-Man Ultra Daily Express",
                description="4 points - 4-player daily run",
                emoji="👥"
            ),
            discord.SelectOption(
                label="7-Man Ultra Daily Express",
                description="7 points - 7-player daily run",
                emoji="👥"
            ),
            discord.SelectOption(
                label="Ultra Weekly Express",
                description="12 points - Weekly ultra run",
                emoji="📅"
            ),
            discord.SelectOption(
                label="Grim Express",
                description="10 points - Grim run",
                emoji="💀"
            ),
            discord.SelectOption(
                label="Daily Temple Express",
                description="6 points - Temple daily run",
                emoji="🏛️"
            )
        ]
        super().__init__(placeholder="Choose a service...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        modal = TicketModal(self.values[0], interaction.guild.id)
        await interaction.response.send_modal(modal)

class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown())


class TicketModal(Modal, title="Ticket Request"):
    def __init__(self, category, guild_id):
        super().__init__()
        self.category = category
        self.guild_id = guild_id
        self.ingame = TextInput(label="In-game name?", required=True, max_length=50)
        self.server = TextInput(label="Server name?", required=True, max_length=50)
        self.room = TextInput(label="Room number?", required=True, max_length=20)
        self.extra = TextInput(
            label="Anything else?",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.add_item(self.ingame)
        self.add_item(self.server)
        self.add_item(self.room)
        self.add_item(self.extra)

    async def on_submit(self, interaction: Interaction):
        try:
            config = await get_server_config(self.guild_id)
            if not config:
                await interaction.response.send_message(
                    "❌ Bot is not properly configured for this server.",
                    ephemeral=True
                )
                return

            # Check if user has the blocked role
            blocked_role_id = config.get('blocked_role_id')
            if blocked_role_id:
                blocked_role = interaction.guild.get_role(blocked_role_id)
                if blocked_role and blocked_role in interaction.user.roles:
                    await interaction.response.send_message(
                        "❌ You are not allowed to create tickets. Please contact an administrator if you believe this is an error.",
                        ephemeral=True
                    )
                    return

            guild = interaction.guild
            ticket_category = guild.get_channel(config.get('ticket_category_id'))
            helper_role_id = config.get('helper_role_id')
            viewer_role_id = config.get('viewer_role_id')
            admin_roles = await get_admin_roles(self.guild_id)

            if not ticket_category:
                await interaction.response.send_message(
                    "❌ Ticket category not found. Please contact an administrator.",
                    ephemeral=True
                )
                return

            # Create channel permissions
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )
            }

            # Add helper role permissions
            if helper_role_id:
                helper_role = guild.get_role(helper_role_id)
                if helper_role:
                    overwrites[helper_role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True
                    )

            # Add viewer role permissions
            if viewer_role_id:
                viewer_role = guild.get_role(viewer_role_id)
                if viewer_role:
                    overwrites[viewer_role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=False,
                        read_message_history=True
                    )

            # Add admin role permissions
            for admin_role_id in admin_roles:
                admin_role = guild.get_role(admin_role_id)
                if admin_role:
                    overwrites[admin_role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True
                    )

            # Get ticket number and create channel
            ticket_number = await db.get_next_ticket_number(self.guild_id, self.category)
            category_name = self.category.lower().replace(" ", "-").replace("'", "")
            channel_name = f"{category_name}-{ticket_number}"
            
            channel = await guild.create_text_channel(
                channel_name,
                overwrites=overwrites,
                category=ticket_category
            )

            # Create ticket embed
            embed = Embed(
                title=f"🎮 Ticket: {self.category}",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="👤 Requester", value=interaction.user.mention, inline=False)
            embed.add_field(name="🎯 IGN", value=self.ingame.value, inline=True)
            embed.add_field(name="🖥️ Server", value=self.server.value, inline=True)
            embed.add_field(name="🏠 Room", value=self.room.value, inline=True)
            
            extra_info = self.extra.value if self.extra.value else "None provided"
            embed.add_field(name="📝 Additional Info", value=extra_info, inline=False)

            # Get slots and point values for this guild
            helper_slots = await get_helper_slots(self.guild_id)
            point_values = await get_point_values(self.guild_id)
            
            slots = helper_slots.get(self.category, DEFAULT_SLOTS)
            helper_list = "\n".join([f"{i+1}. [Empty]" for i in range(slots)])
            embed.add_field(name="👥 Helpers", value=helper_list, inline=False)
            embed.add_field(name="📊 Points Reward", value=f"{point_values.get(self.category, 0)} points", inline=True)

            view = ActiveTicketView(interaction.user, self.category, slots, self.guild_id)
            
            # Send ticket message
            helper_ping = f"<@&{helper_role_id}>" if helper_role_id else "@everyone"
            await channel.send(
                f"🎫 **New ticket created!**\n"
                f"📢 {helper_ping} - Help needed for {self.category}!",
                embed=embed,
                view=view
            )
            
            await interaction.response.send_message(
                f"✅ Ticket created successfully: {channel.mention}",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Error creating ticket: {e}")
            await interaction.response.send_message(
                f"❌ Error creating ticket: {str(e)}",
                ephemeral=True
            )

class ActiveTicketView(View):
    def __init__(self, owner, category, slots, guild_id):
        super().__init__(timeout=None)
        self.owner = owner
        self.category = category
        self.slots = slots
        self.guild_id = guild_id
        self.helpers = []
        self.add_item(JoinButton(self))
        self.add_item(LeaveButton(self))
        self.add_item(RemoveHelperButton(self))
        self.add_item(CloseButton(self))

class JoinButton(Button):
    def __init__(self, ticket_view):
        super().__init__(label="Join as Helper", style=ButtonStyle.green, emoji="✋")
        self.ticket_view = ticket_view

    async def callback(self, interaction: Interaction):
        try:
            if interaction.user in self.ticket_view.helpers:
                await interaction.response.send_message(
                    "❌ You are already in the helper list!",
                    ephemeral=True
                )
                return

            if len(self.ticket_view.helpers) >= self.ticket_view.slots:
                await interaction.response.send_message(
                    "❌ All helper slots are filled!",
                    ephemeral=True
                )
                return

            # Check if user has helper role
            config = await get_server_config(self.ticket_view.guild_id)
            helper_role_id = config.get('helper_role_id') if config else None
            
            if helper_role_id:
                helper_role = interaction.guild.get_role(helper_role_id)
                if helper_role and helper_role not in interaction.user.roles:
                    await interaction.response.send_message(
                        "❌ You need the helper role to join tickets!",
                        ephemeral=True
                    )
                    return

            self.ticket_view.helpers.append(interaction.user)
            
            # Update embed
            embed = interaction.message.embeds[0]
            helper_field_index = None
            for i, field in enumerate(embed.fields):
                if field.name == "👥 Helpers":
                    helper_field_index = i
                    break

            if helper_field_index is not None:
                lines = embed.fields[helper_field_index].value.split("\n")
                for i in range(len(lines)):
                    if "[Empty]" in lines[i]:
                        lines[i] = lines[i].replace("[Empty]", interaction.user.mention, 1)
                        break
                
                embed.set_field_at(
                    helper_field_index,
                    name="👥 Helpers",
                    value="\n".join(lines),
                    inline=False
                )

            await interaction.message.edit(embed=embed, view=self.ticket_view)
            await interaction.response.send_message(
                "✅ You joined as a helper! Thank you for helping!",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error joining ticket: {e}")
            await interaction.response.send_message(
                f"❌ Error joining as helper: {str(e)}",
                ephemeral=True
            )

class LeaveButton(Button):
    def __init__(self, ticket_view):
        super().__init__(label="Leave", style=ButtonStyle.secondary, emoji="👋")
        self.ticket_view = ticket_view

    async def callback(self, interaction: Interaction):
        try:
            if interaction.user not in self.ticket_view.helpers:
                await interaction.response.send_message(
                    "❌ You are not in the helper list!",
                    ephemeral=True
                )
                return

            self.ticket_view.helpers.remove(interaction.user)
            
            # Update embed
            embed = interaction.message.embeds[0]
            helper_field_index = None
            for i, field in enumerate(embed.fields):
                if field.name == "👥 Helpers":
                    helper_field_index = i
                    break

            if helper_field_index is not None:
                lines = embed.fields[helper_field_index].value.split("\n")
                for i in range(len(lines)):
                    if interaction.user.mention in lines[i]:
                        slot_num = lines[i].split(".")[0]
                        lines[i] = f"{slot_num}. [Empty]"
                        break
                
                embed.set_field_at(
                    helper_field_index,
                    name="👥 Helpers",
                    value="\n".join(lines),
                    inline=False
                )

            await interaction.message.edit(embed=embed, view=self.ticket_view)
            await interaction.response.send_message(
                "✅ You left the helper list.",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error leaving ticket: {e}")
            await interaction.response.send_message(
                f"❌ Error leaving: {str(e)}",
                ephemeral=True
            )

class RemoveHelperButton(Button):
    def __init__(self, ticket_view):
        super().__init__(label="Remove Helper", style=ButtonStyle.secondary, emoji="🚫")
        self.ticket_view = ticket_view
        
    async def callback(self, interaction: Interaction):
        try:
            # Check if user has admin permissions
            admin_roles = await get_admin_roles(self.ticket_view.guild_id)
            is_admin = any(r.id in admin_roles for r in interaction.user.roles)
            
            if not is_admin:
                await interaction.response.send_message(
                    "❌ Only admins can remove helpers from tickets.",
                    ephemeral=True
                )
                return
                
            if not self.ticket_view.helpers:
                await interaction.response.send_message(
                    "❌ No helpers to remove from this ticket.",
                    ephemeral=True
                )
                return
                
            # Create helper selection dropdown
            options = []
            for helper in self.ticket_view.helpers:
                options.append(discord.SelectOption(
                    label=helper.display_name,
                    value=str(helper.id),
                    description=f"Remove {helper.display_name} from ticket"
                ))
            
            class HelperRemoveSelect(Select):
                def __init__(self, ticket_view):
                    self.ticket_view = ticket_view
                    super().__init__(
                        placeholder="Select helper to remove...",
                        options=options,
                        max_values=1
                    )
                    
                async def callback(self, select_interaction: Interaction):
                    helper_id = int(self.values[0])
                    helper_to_remove = None
                    
                    # Find the helper to remove
                    for helper in self.ticket_view.helpers:
                        if helper.id == helper_id:
                            helper_to_remove = helper
                            break
                    
                    if helper_to_remove:
                        # Remove from helpers list
                        self.ticket_view.helpers.remove(helper_to_remove)
                        
                        # Update embed
                        embed = select_interaction.message.embeds[0]
                        helper_field_index = None
                        for i, field in enumerate(embed.fields):
                            if field.name == "👥 Helpers":
                                helper_field_index = i
                                break
                                
                        if helper_field_index is not None:
                            lines = embed.fields[helper_field_index].value.split("\n")
                            for i in range(len(lines)):
                                if helper_to_remove.mention in lines[i]:
                                    slot_num = lines[i].split(".")[0]
                                    lines[i] = f"{slot_num}. [Empty]"
                                    break
                            
                            embed.set_field_at(
                                helper_field_index,
                                name="👥 Helpers",
                                value="\n".join(lines),
                                inline=False
                            )
                            
                        await select_interaction.message.edit(embed=embed, view=self.ticket_view)
                        await select_interaction.response.send_message(
                            f"✅ {helper_to_remove.mention} has been removed from the ticket by {select_interaction.user.mention}."
                        )
                    else:
                        await select_interaction.response.send_message(
                            "❌ Helper not found.",
                            ephemeral=True
                        )
            
            view = View(timeout=60)
            view.add_item(HelperRemoveSelect(self.ticket_view))
            await interaction.response.send_message(
                "🚫 **Remove Helper**\nSelect a helper to remove from this ticket:",
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Error removing helper: {e}")
            await interaction.response.send_message(
                f"❌ Error removing helper: {str(e)}",
                ephemeral=True
            )

class CloseButton(Button):
    def __init__(self, ticket_view):
        super().__init__(label="Close Ticket", style=ButtonStyle.red, emoji="🔒")
        self.ticket_view = ticket_view

    async def callback(self, interaction: Interaction):
        try:
            # Check if user is admin
            admin_roles = await get_admin_roles(self.ticket_view.guild_id)
            is_admin = any(r.id in admin_roles for r in interaction.user.roles)
            
            if not is_admin:
                await interaction.response.send_message(
                    "❌ Only admins can close tickets.",
                    ephemeral=True
                )
                return

            await interaction.response.send_message(
                "🔄 Closing ticket and generating transcript...",
                ephemeral=True
            )

            # Generate transcript
            messages = [f"Transcript of {interaction.channel.name}"]
            messages.append(f"Created by: {self.ticket_view.owner}")
            messages.append(f"Service: {self.ticket_view.category}")
            messages.append(f"Opened: {interaction.channel.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            messages.append(f"Closed: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
            messages.append(f"Closed by: {interaction.user}")
            messages.append(f"Helpers: {', '.join([str(helper) for helper in self.ticket_view.helpers])}")
            messages.append("=" * 50)

            # Get recent messages
            async for message in interaction.channel.history(limit=100, oldest_first=True):
                timestamp = message.created_at.strftime('%Y-%m-%d %H:%M:%S')
                messages.append(f"[{timestamp}] {message.author}: {message.content}")

            transcript_content = "\n".join(messages)

            # Send transcript to transcript channel
            config = await get_server_config(self.ticket_view.guild_id)
            if config and config.get('transcript_channel_id'):
                transcript_channel = interaction.guild.get_channel(config['transcript_channel_id'])
                if transcript_channel:
                    # Create file
                    import io
                    transcript_file = io.StringIO(transcript_content)
                    file = discord.File(transcript_file, filename=f"transcript-{interaction.channel.name}.txt")
                    
                    embed = Embed(
                        title="🎫 Ticket Closed",
                        color=discord.Color.red(),
                        timestamp=datetime.datetime.now()
                    )
                    embed.add_field(name="Ticket", value=interaction.channel.name, inline=True)
                    embed.add_field(name="Service", value=self.ticket_view.category, inline=True)
                    embed.add_field(name="Requester", value=str(self.ticket_view.owner), inline=True)
                    embed.add_field(name="Closed by", value=str(interaction.user), inline=True)
                    
                    await transcript_channel.send(embed=embed, file=file)

            # Award points to helpers
            point_values = await get_point_values(self.ticket_view.guild_id)
            points_to_award = point_values.get(self.ticket_view.category, 0)
            
            for helper in self.ticket_view.helpers:
                current_points = await db.get_user_points(self.ticket_view.guild_id, helper.id)
                new_points = current_points + points_to_award
                await db.update_user_points(self.ticket_view.guild_id, helper.id, new_points)

            # Delete channel after delay
            await asyncio.sleep(3)
            await interaction.channel.delete()

        except Exception as e:
            logger.error(f"Error closing ticket: {e}")
            try:
                await interaction.followup.send(
                    f"❌ Error closing ticket: {str(e)}",
                    ephemeral=True
                )
            except:
                pass

@bot.command(name="removehelper")
async def remove_helper(ctx, user: discord.Member, *, reason="No reason provided"):
    """Remove a specific helper from all active tickets (Admin only)"""
    admin_roles = await get_admin_roles(ctx.guild.id)
    is_admin = any(r.id in admin_roles for r in ctx.author.roles)
    
    if not is_admin:
        await ctx.send("❌ You don't have permission to use this command.")
        return
    
    config = await get_server_config(ctx.guild.id)
    if not config or not config.get('ticket_category_id'):
        await ctx.send("❌ Ticket category not configured.")
        return
    
    ticket_category = ctx.guild.get_channel(config['ticket_category_id'])
    if not ticket_category:
        await ctx.send("❌ Ticket category not found.")
        return
    
    removed_from = []
    
    for channel in ticket_category.text_channels:
        try:
            # Check if channel has ticket messages
            async for message in channel.history(limit=10):
                if message.embeds and len(message.embeds) > 0:
                    embed = message.embeds[0]
                    # Look for helper field
                    for field in embed.fields:
                        if field.name == "👥 Helpers" and user.mention in field.value:
                            # Update the embed to remove the helper
                            lines = field.value.split("\n")
                            for i in range(len(lines)):
                                if user.mention in lines[i]:
                                    slot_num = lines[i].split(".")[0]
                                    lines[i] = f"{slot_num}. [Empty]"
                                    break
                            
                            # Update field
                            field_index = embed.fields.index(field)
                            embed.set_field_at(
                                field_index,
                                name="👥 Helpers",
                                value="\n".join(lines),
                                inline=False
                            )
                            
                            await message.edit(embed=embed)
                            removed_from.append(channel.mention)
                            
                            # Notify in the ticket channel
                            await channel.send(
                                f"⚠️ {user.mention} has been removed from this ticket by {ctx.author.mention}\n"
                                f"**Reason:** {reason}"
                            )
                            break
                    break
        except Exception as e:
            logger.error(f"Error removing helper from {channel.name}: {e}")
            continue
    
    if removed_from:
        await ctx.send(
            f"✅ Removed {user.mention} from {len(removed_from)} ticket(s): {', '.join(removed_from)}\n"
            f"**Reason:** {reason}"
        )
    else:
        await ctx.send(f"❌ {user.mention} was not found in any active tickets.")

@bot.command(name="hrules", aliases=["Hrules"])
async def helper_rules(ctx):
    """Display helper ticket rules"""
    custom_rules = await db.get_custom_rule(ctx.guild.id, "helper_rules")
    
    if custom_rules:
        content = custom_rules
    else:
        content = """📥Ticket Rules for Helpers📥
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
    
    embed = Embed(
        title="📋 Helper Rules",
        description=content,
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now()
    )
    
    await ctx.send(embed=embed)

@bot.command(name="rrules", aliases=["Rrules"])
async def requester_rules(ctx):
    """Display requester ticket rules"""
    custom_rules = await db.get_custom_rule(ctx.guild.id, "requester_rules")
    
    if custom_rules:
        content = custom_rules
    else:
        content = """📥Ticket Rules for Requestors📥
⚔️ Respect Comes First
Toxicity, harassment, discrimination, or any disrespectful behavior is not allowed.

👤 No Premade Allowed
You may only open a ticket if you're alone. Absolutely no premade teams. Only Helpers + YOU

🔐 Always Use a Private Room
Tickets must be opened in a private room e.g. "ultraspeaker-2310". If you use a public room number and anyone else is in the room, the ticket is disqualified.

🎭 Skill Issue ≠ Trolling
It's okay to be bad. However, sabotaging the run intentionally or trolling in any form is not tolerated. If it happens multiple times, your ability to open tickets may be revoked. (Proof or staff confirmation is required in any complains.)

📸 You Must Take the Screenshot
Requestors are responsible for taking the final screenshot. If you fail to do this multiple times, you may be banned from opening tickets.

⚖️ Use Common Sense
Attempting to exploit loopholes or bend the rules for any reason will be punished without mercy."""
    
    embed = Embed(
        title="📋 Requester Rules",
        description=content,
        color=discord.Color.green(),
        timestamp=datetime.datetime.now()
    )
    
    await ctx.send(embed=embed)

@bot.command(name="proof")
async def proof_requirements(ctx):
    """Display proof requirements"""
    custom_proof = await db.get_custom_rule(ctx.guild.id, "proof_requirements")
    
    if custom_proof:
        content = custom_proof
    else:
        content = """After requesting a ticket and completing the objective, don't forget to post proof!

No Proof = No Points ❌

Take a screenshot of the Helpers' names and the quests that have been completed. After that, simply send the screenshot inside the ticket.

If everything is done correctly, it should look something like this:"""
    
    embed = Embed(
        title="📸 Proof Requirements",
        description=content,
        color=discord.Color.orange(),
        timestamp=datetime.datetime.now()
    )
    
    # Add the example image showing completed quests
    embed.set_image(url="attachment://proof_example.png")
    
    # Send with the attached image file
    file = discord.File("attached_assets/image_1755846164651.png", filename="proof_example.png")
    await ctx.send(embed=embed, file=file)

@bot.command(name="points")
async def check_points(ctx, user: discord.Member = None):
    """Check points for yourself or another user"""
    target_user = user or ctx.author
    points = await db.get_user_points(ctx.guild.id, target_user.id)
    
    embed = Embed(
        title="🏆 Points",
        color=discord.Color.gold()
    )
    embed.add_field(
        name=f"{target_user.display_name}'s Points",
        value=f"**{points}** points",
        inline=False
    )
    embed.set_thumbnail(url=target_user.avatar.url if target_user.avatar else target_user.default_avatar.url)
    
    await ctx.send(embed=embed)

@bot.command(name="leaderboard", aliases=["lb"])
async def leaderboard(ctx):
    """Show points leaderboard for the server"""
    all_points = await db.get_all_user_points(ctx.guild.id)
    
    if not all_points:
        await ctx.send("❌ No points data found for this server.")
        return
    
    # Sort by points (descending)
    sorted_points = sorted(all_points.items(), key=lambda x: x[1], reverse=True)
    
    embed = Embed(
        title="🏆 Points Leaderboard",
        color=discord.Color.gold(),
        timestamp=datetime.datetime.now()
    )
    
    leaderboard_text = ""
    for i, (user_id, points) in enumerate(sorted_points[:10], 1):
        user = ctx.guild.get_member(user_id)
        if user:
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            leaderboard_text += f"{medal} **{user.display_name}** - {points} points\n"
        else:
            leaderboard_text += f"{i}. *Unknown User* - {points} points\n"
    
    embed.description = leaderboard_text if leaderboard_text else "No users found."
    await ctx.send(embed=embed)

@bot.command(name="setrule")
async def set_custom_rule(ctx, rule_type: str, *, content: str):
    """Set custom rule content (Admin only)"""
    admin_roles = await get_admin_roles(ctx.guild.id)
    is_admin = any(r.id in admin_roles for r in ctx.author.roles)
    
    if not is_admin:
        await ctx.send("❌ You don't have permission to use this command.")
        return
    
    valid_rule_types = ["helper_rules", "requester_rules", "proof_requirements"]
    if rule_type not in valid_rule_types:
        await ctx.send(f"❌ Invalid rule type. Valid types: {', '.join(valid_rule_types)}")
        return
    
    await db.set_custom_rule(ctx.guild.id, rule_type, content)
    await ctx.send(f"✅ Custom {rule_type} has been updated.")

# Load legacy JSON points for backward compatibility
def load_legacy_points():
    if not os.path.exists("points.json"):
        return {}
    try:
        with open("points.json", "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_legacy_points(data):
    try:
        with open("points.json", "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving points: {e}")

legacy_points = load_legacy_points()

# Command lock decorator for original commands
command_locks = {}

def command_lock(name):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(ctx, *args, **kwargs):
            lock = command_locks.setdefault(name, False)
            if lock:
                return
            command_locks[name] = True
            try:
                await func(ctx, *args, **kwargs)
            finally:
                command_locks[name] = False
        return wrapper
    return decorator

@bot.command(name='create')
@command_lock('create')
async def create_panel(ctx):
    """Create the ticket selection panel - Admin only"""
    admin_roles = await get_admin_roles(ctx.guild.id)
    is_admin = any(r.id in admin_roles for r in ctx.author.roles)
    
    if not is_admin:
        await ctx.send("❌ You don't have permission to use this command.")
        return

    point_values = await get_point_values(ctx.guild.id)
    helper_slots = await get_helper_slots(ctx.guild.id)
    
    options = [
        discord.SelectOption(
            label=cat,
            value=cat,
            description=f"{point_values[cat]} points • {helper_slots.get(cat, DEFAULT_SLOTS)} helper slots"
        ) for cat in point_values.keys()
    ]

    class TicketSelect(Select):
        def __init__(self):
            super().__init__(
                placeholder="Select a service to create a ticket...",
                min_values=1,
                max_values=1,
                options=options
            )
        async def callback(self, interaction: Interaction):
            category = self.values[0]
            await interaction.response.send_modal(TicketModal(category, interaction.guild.id))

    embed = Embed(
        title="🎮 In-game Assistance",
        description=(
            "Select a service below to create a help ticket. Our helpers will assist you!\n\n"
            "📜 **Guidelines & Rules:** Use !Hrules, !Rrules, and !proof commands"
        ),
        color=discord.Color.blue()
    )
    embed.add_field(
        name="📋 Available Services",
        value="\n".join([f"- **{cat}** — {pts} points" for cat, pts in point_values.items()]),
        inline=False
    )
    embed.add_field(
        name="ℹ️ How it works",
        value="1. Select a service\n2. Fill out the form\n3. Wait for helpers to join\n4. Get help in your private ticket!",
        inline=False
    )
    view = View(timeout=None)
    view.add_item(TicketSelect())
    await ctx.send(embed=embed, view=view)

@bot.command(name='delete')
@command_lock('delete')
async def delete_panel(ctx, message_id: int = None):
    """Delete a bot message panel - Admin only"""
    admin_roles = await get_admin_roles(ctx.guild.id)
    is_admin = any(r.id in admin_roles for r in ctx.author.roles)
    
    if not is_admin:
        await ctx.send("❌ You don't have permission to use this command.")
        return
    if message_id is None:
        await ctx.send("❌ Please provide a message ID. Usage: `!delete <message_id>`")
        return
    try:
        message = await ctx.channel.fetch_message(message_id)
        if message.author != bot.user:
            await ctx.send("❌ I can only delete my own messages.")
            return
        await message.delete()
        await ctx.send(f"✅ Panel with message ID `{message_id}` has been deleted.")
    except discord.NotFound:
        await ctx.send("❌ Message not found. Make sure the message ID is correct and in this channel.")
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to delete that message.")
    except Exception as e:
        await ctx.send(f"❌ Error deleting panel: {str(e)}")

@bot.command(name='mypoints')
@command_lock('mypoints')
async def check_my_points(ctx):
    """Check your own points"""
    user_points = await db.get_user_points(ctx.guild.id, ctx.author.id)
    # Also check legacy points for backward compatibility
    legacy_user_points = legacy_points.get(str(ctx.author.id), 0)
    total_points = user_points + legacy_user_points
    
    embed = Embed(
        title="📊 Your Helper Points",
        description=f"You have **{total_points}** points",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

def is_admin_legacy(user, guild_id):
    """Check if user is admin using both new and legacy systems"""
    # This is a simplified check - you may want to expand this
    return any(r.name.lower() in ['admin', 'administrator', 'owner'] for r in user.roles)

@bot.command(name='add')
@command_lock('add')
async def add_points(ctx, member: discord.Member, amount: int):
    """Add points to a user - Admin only"""
    admin_roles = await get_admin_roles(ctx.guild.id)
    is_admin = any(r.id in admin_roles for r in ctx.author.roles) or is_admin_legacy(ctx.author, ctx.guild.id)
    
    if not is_admin:
        await ctx.send("❌ You don't have permission to use this command.")
        return
    if amount <= 0:
        await ctx.send("❌ Amount must be positive.")
        return
    
    # Add to both systems for compatibility
    await db.add_user_points(ctx.guild.id, member.id, amount)
    user_id = str(member.id)
    legacy_points[user_id] = legacy_points.get(user_id, 0) + amount
    save_legacy_points(legacy_points)
    
    total_points = await db.get_user_points(ctx.guild.id, member.id) + legacy_points.get(user_id, 0)
    
    embed = Embed(
        title="✅ Points Added",
        description=f"Added **{amount}** points to {member.mention}",
        color=discord.Color.green()
    )
    embed.add_field(name="New Total", value=f"{total_points} points", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='remove')
@command_lock('remove')
async def remove_points(ctx, member: discord.Member, amount: int):
    """Remove points from a user - Admin only"""
    admin_roles = await get_admin_roles(ctx.guild.id)
    is_admin = any(r.id in admin_roles for r in ctx.author.roles) or is_admin_legacy(ctx.author, ctx.guild.id)
    
    if not is_admin:
        await ctx.send("❌ You don't have permission to use this command.")
        return
    if amount <= 0:
        await ctx.send("❌ Amount must be positive.")
        return
    
    # Remove from database (with minimum 0)
    current_db_points = await db.get_user_points(ctx.guild.id, member.id)
    new_db_points = max(0, current_db_points - amount)
    await db.set_user_points(ctx.guild.id, member.id, new_db_points)
    
    # Also handle legacy points
    user_id = str(member.id)
    current_legacy = legacy_points.get(user_id, 0)
    remaining_to_remove = amount - (current_db_points - new_db_points)
    if remaining_to_remove > 0:
        new_legacy = max(0, current_legacy - remaining_to_remove)
        legacy_points[user_id] = new_legacy
        save_legacy_points(legacy_points)
    
    total_points = new_db_points + legacy_points.get(user_id, 0)
    
    embed = Embed(
        title="✅ Points Removed",
        description=f"Removed **{amount}** points from {member.mention}",
        color=discord.Color.orange()
    )
    embed.add_field(name="New Total", value=f"{total_points} points", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='setpoints')
@command_lock('setpoints')
async def set_points(ctx, member: discord.Member, amount: int):
    """Set a user's points to a specific amount - Admin only"""
    admin_roles = await get_admin_roles(ctx.guild.id)
    is_admin = any(r.id in admin_roles for r in ctx.author.roles) or is_admin_legacy(ctx.author, ctx.guild.id)
    
    if not is_admin:
        await ctx.send("❌ You don't have permission to use this command.")
        return
    if amount < 0:
        await ctx.send("❌ Amount cannot be negative.")
        return
    
    # Set in database and clear legacy
    await db.set_user_points(ctx.guild.id, member.id, amount)
    user_id = str(member.id)
    legacy_points[user_id] = 0
    save_legacy_points(legacy_points)
    
    embed = Embed(
        title="✅ Points Set",
        description=f"Set {member.mention}'s points to **{amount}**",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

@bot.command(name='resetpoints')
@command_lock('resetpoints')
async def reset_points(ctx, member: discord.Member = None):
    """Reset points for a user or all users - Admin only"""
    admin_roles = await get_admin_roles(ctx.guild.id)
    is_admin = any(r.id in admin_roles for r in ctx.author.roles) or is_admin_legacy(ctx.author, ctx.guild.id)
    
    if not is_admin:
        await ctx.send("❌ You don't have permission to use this command.")
        return
    
    if member:
        await db.set_user_points(ctx.guild.id, member.id, 0)
        user_id = str(member.id)
        if user_id in legacy_points:
            del legacy_points[user_id]
            save_legacy_points(legacy_points)
        await ctx.send(f"✅ Reset {member.mention}'s points to 0.")
    else:
        await ctx.send("⚠️ Are you sure you want to reset ALL points? Type `confirm` to proceed.")
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == 'confirm'
        try:
            await bot.wait_for('message', check=check, timeout=30.0)
            await db.clear_all_points(ctx.guild.id)
            legacy_points.clear()
            save_legacy_points(legacy_points)
            await ctx.send("✅ All points have been reset.")
        except asyncio.TimeoutError:
            await ctx.send("❌ Confirmation timed out. Points were not reset.")

@bot.command(name='removeuser')
@command_lock('removeuser')
async def remove_user(ctx, member: discord.Member):
    """Remove a user from the leaderboard - Admin only"""
    admin_roles = await get_admin_roles(ctx.guild.id)
    is_admin = any(r.id in admin_roles for r in ctx.author.roles) or is_admin_legacy(ctx.author, ctx.guild.id)
    
    if not is_admin:
        await ctx.send("❌ You don't have permission to use this command.")
        return
    
    await db.set_user_points(ctx.guild.id, member.id, 0)
    user_id = str(member.id)
    if user_id in legacy_points:
        del legacy_points[user_id]
        save_legacy_points(legacy_points)
        await ctx.send(f"✅ {member.mention} was removed from the leaderboard.")
    else:
        await ctx.send(f"✅ {member.mention} was removed from the leaderboard.")

@bot.command(name='restartleaderboard')
@command_lock('restartleaderboard')
async def restart_leaderboard(ctx):
    """Reset the entire leaderboard - Admin only"""
    admin_roles = await get_admin_roles(ctx.guild.id)
    is_admin = any(r.id in admin_roles for r in ctx.author.roles) or is_admin_legacy(ctx.author, ctx.guild.id)
    
    if not is_admin:
        await ctx.send("❌ You don't have permission to use this command.")
        return
    
    await ctx.send("⚠️ Are you sure you want to RESET the leaderboard? Type `confirm` to proceed.")
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == 'confirm'
    try:
        await bot.wait_for('message', check=check, timeout=30.0)
        await db.clear_all_points(ctx.guild.id)
        legacy_points.clear()
        save_legacy_points(legacy_points)
        await ctx.send("✅ The leaderboard has been reset.")
    except asyncio.TimeoutError:
        await ctx.send("❌ Confirmation timed out. Leaderboard was not reset.")

@bot.command(name='help')
@command_lock('help')
async def help_command(ctx):
    """Show all available commands"""
    embed = Embed(
        title="✨ Bot Commands & Help",
        description="Welcome! Here are all the commands you can use.",
        color=discord.Color.purple()
    )
    embed.add_field(
        name="🎫 Ticket Commands",
        value=(
            "\n"
            "- `!create` — Create ticket panel (*admin only*)\n"
            "- `!delete <message_id>` — Delete ticket panel (*admin only*)\n"
            "- `!removehelper @user` — Remove helper from ticket (*admin only*)"
        ),
        inline=False
    )
    embed.add_field(
        name="📊 Points & Leaderboard",
        value=(
            "- `!leaderboard` — View top helpers\n"
            "- `!mypoints` — See your own points\n"
            "- `!points [@user]` — See someone's points\n"
            "- `!add @user amount` — Add points (*admin*)\n"
            "- `!remove @user amount` — Remove points (*admin*)\n"
            "- `!setpoints @user amount` — Set points (*admin*)\n"
            "- `!resetpoints [@user]` — Reset points (*admin*)\n"
            "- `!removeuser @user` — Remove user from leaderboard (*admin*)\n"
            "- `!restartleaderboard` — Reset all leaderboard (*admin*)"
        ),
        inline=False
    )
    embed.add_field(
        name="📜 Rules & Setup",
        value=(
            "- `!Hrules` — Helper guidelines\n"
            "- `!Rrules` — Requester guidelines\n"
            "- `!proof` — Proof requirements\n"
            "- `!setrule <type> <content>` — Update rules (*admin*)\n"
            "- `!setup` — Configure server settings (*admin*)"
        ),
        inline=False
    )
    embed.set_footer(text="Need more help? Contact an admin!")
    await ctx.send(embed=embed)

# Check and reset ticket numbers for inactive tickets
async def check_and_reset_ticket_numbers(guild, category):
    category_name = category.lower().replace(" ", "-").replace("'", "")
    existing_tickets = []
    
    config = await get_server_config(guild.id)
    if not config or not config.get('ticket_category_id'):
        return
    
    ticket_category = guild.get_channel(config['ticket_category_id'])
    if not ticket_category:
        return
    
    for channel in ticket_category.text_channels:
        if channel.name.startswith(category_name + "-"):
            parts = channel.name.split("-")
            if len(parts) >= 2 and parts[-1].isdigit():
                existing_tickets.append(channel)
    
    if not existing_tickets:
        await db.reset_ticket_number(guild.id, category)
        print(f"Reset ticket counter for {category} in guild {guild.id} - no active tickets found")

# Start the web server and bot
if __name__ == "__main__":
    start_server()
    bot.run(TOKEN)
