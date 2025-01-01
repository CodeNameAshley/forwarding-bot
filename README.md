# Forwarding Bot

A Discord bot that forwards messages from one channel to another and manages source channels using a SQLite database.

## Features

- Forward messages from a source channel to a target channel.
- Add and remove source channels.
- List all source channels.
- Handles custom emojis in messages.

## Requirements

- Python 3.9+
- `discord.py`
- `aiosqlite`
- `python-dotenv`

## Installation

1. **Clone the repository:**
   ```sh
   git clone https://github.com/yourusername/forwarding-bot.git
   cd forwarding-bot