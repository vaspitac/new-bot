# Overview

This is an enhanced Discord bot application designed for managing helper points and ticketing systems within Discord servers with full multi-server support. The bot allows server administrators to dynamically configure roles, track user points for various services, and manage support tickets through an interactive setup system. It features a web server component for health monitoring, database storage with migration capabilities, and advanced administrative tools for blocking users and managing helpers.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Application Structure
The application follows a modular architecture with clear separation of concerns:

- **main.py**: Core Discord bot implementation with command handlers and event listeners
- **database.py**: Database abstraction layer using SQLite with async support
- **migrate.py**: Data migration utilities for transitioning from JSON to database storage
- **server.py**: Flask web server for health monitoring and external connectivity

## Discord Bot Framework
Built on top of discord.py library with the following design choices:
- Uses command prefix "!" for bot commands
- Implements custom UI components (Views, Buttons, Modals) for interactive Discord interfaces
- Leverages Discord's slash commands and button interactions for modern user experience
- Enables all intents for comprehensive Discord API access

## Data Storage Architecture
The system implements a hybrid storage approach during migration:
- **Legacy**: JSON files (points.json, ticket_numbers.json) for backward compatibility
- **Current**: SQLite database with async operations using aiosqlite
- **Migration Strategy**: Gradual transition with backup mechanisms and data validation

## Database Schema Design
The SQLite database uses a normalized schema with the following key tables:
- **server_configs**: Guild-specific configuration settings including role IDs and channel mappings
- **admin_roles**: Many-to-many relationship for administrative role assignments
- **point_values**: Configurable point values per service type per guild
- **Additional tables**: Support for tickets, user points, and service tracking (implied from migration logic)

## Asynchronous Architecture
The application embraces async/await patterns throughout:
- Database operations use aiosqlite for non-blocking I/O
- Discord API interactions leverage discord.py's async capabilities
- Migration processes run asynchronously to prevent blocking

## Configuration Management
Environment-based configuration using python-dotenv:
- Discord bot token stored as environment variable
- Default fallback values defined for point systems and slot configurations
- Server-specific configurations stored in database for multi-guild support

## Error Handling and Logging
Implements comprehensive logging using Python's logging module:
- Structured logging across all modules
- Migration processes include backup creation before data transformation
- Graceful fallback mechanisms for missing configuration data

# External Dependencies

## Discord Platform
- **discord.py**: Primary library for Discord bot functionality and API interactions
- **Discord Developer Portal**: Bot token management and application configuration

## Database Technology
- **SQLite**: Embedded database for local data persistence
- **aiosqlite**: Async SQLite adapter for non-blocking database operations

## Web Framework
- **Flask**: Lightweight web server for health monitoring and external API endpoints
- **Deployment Platform**: Configured for platforms like Replit or Heroku (indicated by PORT environment variable usage)

## Development Tools
- **python-dotenv**: Environment variable management for secure configuration
- **JSON**: Legacy data format support during migration phase

## Infrastructure Components
- **Threading**: Multi-threaded architecture separating Discord bot and web server processes
- **File System**: JSON file backup and migration utilities
- **Environment Variables**: Secure token and configuration management