"""
Bot Configuration
Configuration settings and environment variable management.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class BotConfig:
    """Bot configuration class."""
    
    def __init__(self):
        # Discord Bot Token (REQUIRED)
        self.BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN', '')
        
        if not self.BOT_TOKEN:
            raise ValueError(
                "DISCORD_BOT_TOKEN environment variable is required. "
                "Please set it in your environment or .env file."
            )
        
        # Bot Settings
        self.COMMAND_PREFIX = os.getenv('COMMAND_PREFIX', '!')
        self.DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
        
        # Optional Settings
        self.MAX_MESSAGE_LENGTH = int(os.getenv('MAX_MESSAGE_LENGTH', '2000'))
        self.DEFAULT_EMBED_COLOR = int(os.getenv('DEFAULT_EMBED_COLOR', '0x3498db'), 16)
        
        # Logging Settings
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
        self.LOG_FILE = os.getenv('LOG_FILE', 'bot.log')
        
    def validate_config(self):
        """Validate configuration settings."""
        if len(self.BOT_TOKEN) < 50:
            raise ValueError("Invalid bot token format")
            
        if not self.COMMAND_PREFIX:
            raise ValueError("Command prefix cannot be empty")
            
        return True
