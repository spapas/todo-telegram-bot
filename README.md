# Todo Telegram Bot

A simple Telegram bot for managing personal tasks using SQLite. Supports adding, listing, updating, and completing tasks with optional metadata (who, category, tags).

## Features
- Add tasks with free-text and optional metadata
- List tasks with filters (by text, who, category, tags)
- Mark tasks as completed
- Update task fields
- All data stored locally in `tasks.db` (SQLite)
- Telegram command autocomplete

## Commands
```
/add <task description> [who=..., category=..., tags=...]
    Add a new task. Free-text first, optional key=value after.

/list [task=..., who=..., category=..., tags=..., show_completed=1]
    List tasks with optional filters. By default completed tasks are hidden.

/done <task_id>
    Mark a task as completed.

/update <task_id> <new task description> [who=..., category=..., tags=...]
    Update task fields.

/help
    Show help message.
```

## Setup
1. Clone the repository and enter the project folder.
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Copy `.env.template` to `.env` and add your Telegram bot token:
   ```
   TELEGRAM_BOT_TOKEN='your_token_here'
   ```
4. Run the bot:
   ```
   python tbot.py
   ```

## File Structure
- `tbot.py` — Main bot source code
- `requirements.txt` — Python dependencies
- `.env.template` — Environment variable template
- `tasks.db` — SQLite database (created automatically)

## Requirements
- Python 3.10+
- Telegram bot token

## License
See `LICENSE` for details.
