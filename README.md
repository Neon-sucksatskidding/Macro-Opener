# Macro Opener (Discord Edition)

A cleaner and more Discord-friendly macro launcher bot for Bee Swarm Simulator.

## What improved

- Uses modern `discord.py` (v2+) APIs.
- Supports both **prefix commands** and **slash commands**.
- Restricts macro control to one authorized Discord user ID.
- Uses process state tracking so duplicate starts are blocked.
- Adds graceful process shutdown and signal handling.

## Commands

Assuming `MACRO_COMMAND_PREFIX=!om`:

- Prefix commands:
  - `!om start`
  - `!om stop`
  - `!om status`
- Slash commands:
  - `/macro-start`
  - `/macro-stop`
  - `/macro-status`

## Setup

1. Create a Discord bot in the Developer Portal.
2. Enable **Message Content Intent**.
3. Invite the bot to your server with application command scope.
4. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

5. Set environment variables:

```bash
export DISCORD_TOKEN="your_bot_token"
export AUTHORIZED_USER_ID="your_discord_user_id"
export MACRO_PATH="/absolute/path/to/your/macro.exe"
export MACRO_COMMAND_PREFIX="!om"  # optional
```

6. Start the bot:

```bash
python macro_opener_bot.py
```

## Notes

- `MACRO_PATH` can be a full command string (for example with arguments).
- Only `AUTHORIZED_USER_ID` can start/stop the macro.
- The bot responds with ephemeral messages for slash commands.
