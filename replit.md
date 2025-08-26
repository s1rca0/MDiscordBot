# Discord Bot Project

## Overview

This is a Discord bot application built with Python using the discord.py library. The bot follows a modular architecture with a cog-based command system, allowing for organized and extensible functionality. The project includes basic commands like ping, hello, and info commands, with a foundation for adding more complex features.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Core Architecture
- **Main Entry Point**: `main.py` serves as the application entry point with proper error handling and logging setup
- **Bot Core**: `DiscordBot` class in `bot.py` manages the Discord client, event handling, and bot lifecycle
- **Configuration Management**: Centralized configuration system using environment variables with `.env` file support
- **Modular Command System**: Cog-based architecture for organizing commands into logical groups

### Command System
- **Cog Pattern**: Commands are organized into separate cog files (e.g., `basic_commands.py`) for better modularity
- **Command Prefix**: Configurable command prefix system (default: `!`)
- **Aliases**: Support for command aliases to improve user experience
- **Error Handling**: Built-in error handling with logging integration

### Event Management
- **Discord Events**: Centralized event handling in the main bot class
- **Status Management**: Automatic bot status updates and presence management
- **Guild Tracking**: Basic guild membership tracking and logging

### Logging System
- **Multi-destination Logging**: Logs to both file (`bot.log`) and console
- **Configurable Log Levels**: Environment variable controlled logging levels
- **Structured Logging**: Consistent logging format across all components

### Configuration Design
- **Environment-based**: All configuration through environment variables
- **Validation**: Built-in configuration validation with meaningful error messages
- **Defaults**: Sensible default values for optional settings
- **Security**: Proper handling of sensitive data like bot tokens

## External Dependencies

### Core Libraries
- **discord.py**: Main Discord API wrapper for Python
- **python-dotenv**: Environment variable management from .env files
- **psutil**: System information gathering for bot status commands
- **asyncio**: Asynchronous programming support for Discord interactions

### Discord API Integration
- **Bot Permissions**: Configured with message content, guild, and member intents
- **Embed Support**: Rich embed messages for enhanced user experience
- **Real-time Communication**: WebSocket-based real-time Discord gateway connection

### System Dependencies
- **Python 3.7+**: Minimum Python version requirement
- **Environment Variables**: Configuration through DISCORD_BOT_TOKEN and optional settings
- **File System**: Local file logging and configuration file support