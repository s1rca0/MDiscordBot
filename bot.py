"""
Discord Bot Core Implementation
Main bot class with command handling and event management.
"""

import os
import logging
import discord
from discord.ext import commands
from config import BotConfig

class DiscordBot:
    """Main Discord bot class."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.config = BotConfig()
        
        # Configure bot intents (using only default intents to avoid privileged intent requirements)
        intents = discord.Intents.default()
        
        # Initialize bot with command prefix
        self.bot = commands.Bot(
            command_prefix=self.config.COMMAND_PREFIX,
            intents=intents,
            help_command=None  # We'll create a custom help command
        )
        
        # Register event handlers
        self.setup_events()
        
    def setup_events(self):
        """Set up bot event handlers."""
        
        @self.bot.event
        async def on_ready():
            """Called when the bot is ready and connected."""
            self.logger.info(f'{self.bot.user} has connected to Discord!')
            self.logger.info(f'Bot is in {len(self.bot.guilds)} guilds')
            
            # Set bot status
            activity = discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{self.config.COMMAND_PREFIX}help for commands"
            )
            await self.bot.change_presence(activity=activity, status=discord.Status.online)
            
        @self.bot.event
        async def on_guild_join(guild):
            """Called when bot joins a new guild."""
            self.logger.info(f'Joined guild: {guild.name} (ID: {guild.id})')
            
        @self.bot.event
        async def on_guild_remove(guild):
            """Called when bot leaves a guild."""
            self.logger.info(f'Left guild: {guild.name} (ID: {guild.id})')
            
        @self.bot.event
        async def on_message(message):
            """Handle incoming messages."""
            # Ignore messages from bots
            if message.author.bot:
                return
                
            # Log message for debugging (be careful with privacy)
            if self.config.DEBUG_MODE:
                self.logger.debug(f'Message from {message.author}: {message.content[:50]}...')
            
            # Process commands
            await self.bot.process_commands(message)
            
        @self.bot.event
        async def on_command_error(ctx, error):
            """Handle command errors."""
            if isinstance(error, commands.CommandNotFound):
                await ctx.send(f"❌ Command not found. Use `{self.config.COMMAND_PREFIX}help` to see available commands.")
            elif isinstance(error, commands.MissingRequiredArgument):
                await ctx.send(f"❌ Missing required argument. Use `{self.config.COMMAND_PREFIX}help {ctx.command}` for usage.")
            elif isinstance(error, commands.MissingPermissions):
                await ctx.send("❌ You don't have permission to use this command.")
            elif isinstance(error, commands.BotMissingPermissions):
                await ctx.send("❌ I don't have the required permissions to execute this command.")
            elif isinstance(error, commands.CommandOnCooldown):
                await ctx.send(f"❌ Command on cooldown. Try again in {error.retry_after:.2f} seconds.")
            else:
                self.logger.error(f'Unhandled command error: {error}')
                await ctx.send("❌ An unexpected error occurred while processing your command.")
    
    async def load_cogs(self):
        """Load all cogs (command modules)."""
        cogs_to_load = [
            'cogs.basic_commands'
        ]
        
        for cog in cogs_to_load:
            try:
                await self.bot.load_extension(cog)
                self.logger.info(f'Loaded cog: {cog}')
            except Exception as e:
                self.logger.error(f'Failed to load cog {cog}: {e}')
    
    async def start_bot(self):
        """Start the Discord bot."""
        try:
            # Load cogs before starting
            await self.load_cogs()
            
            # Start the bot
            await self.bot.start(self.config.BOT_TOKEN)
            
        except discord.LoginFailure:
            self.logger.error("Invalid bot token provided")
            raise
        except discord.HTTPException as e:
            self.logger.error(f"HTTP error occurred: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error starting bot: {e}")
            raise
        finally:
            await self.bot.close()
