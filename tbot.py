import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
import os
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_NAME = "tasks.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task TEXT NOT NULL,
            who TEXT,
            category TEXT,
            tags TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            completed_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def parse_params(text: str):
    pattern = r'(who|category|tags)\s*=\s*(.*?)(?=\s+\w+\s*=|$)'
    return {k.lower(): v.strip() for k, v in re.findall(pattern, text)}


def parse_add_command(text: str):
    pattern = r'\b(who|category|tags)\s*='
    match = re.search(pattern, text)
    if match:
        idx = match.start()
        task = text[:idx].strip()
        param_text = text[idx:].strip()
        params = parse_params(param_text)
    else:
        task = text.strip()
        params = {}
    return task, params


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    user_id = update.message.from_user.id
    text = " ".join(context.args)

    if not text:
        await update.message.reply_text("You must provide a task description.")
        return

    task, params = parse_add_command(text)

    if not task:
        await update.message.reply_text("Task description cannot be empty.")
        return

    who = params.get("who", "")
    category = params.get("category", "")
    tags = params.get("tags", "")
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "INSERT INTO tasks (user_id, task, who, category, tags, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, task, who, category, tags, created_at),
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(f"Task added: {task}")


async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    user_id = update.message.from_user.id
    filters = parse_params(" ".join(context.args))

    query = "SELECT id, task, who, category, tags, created_at, updated_at, completed_at FROM tasks WHERE user_id=?"
    params = [user_id]

    if "task" in filters:
        query += " AND task LIKE ?"
        params.append(f"%{filters['task']}%")
    if "who" in filters:
        query += " AND who LIKE ?"
        params.append(f"%{filters['who']}%")
    if "category" in filters:
        query += " AND category LIKE ?"
        params.append(f"%{filters['category']}%")
    if "tags" in filters:
        query += " AND tags LIKE ?"
        params.append(f"%{filters['tags']}%")
    if filters.get("show_completed") != "1":
        query += " AND completed_at IS NULL"

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(query, tuple(params))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("No tasks found.")
        return

    message = ""
    for r in rows:
        tid, task, who, category, tags, created_at, updated_at, completed_at = r
        status = "✅" if completed_at else "❌"
        message += (
            f"<b>{tid}.</b> {task} | who: {who or '-'} | category: {category or '-'} | "
            f"tags: {tags or '-'} | created: {created_at} | updated: {updated_at or '-'} | "
            f"completed: {completed_at or '-'} | {status}\n"
        )

    await update.message.reply_text(message, parse_mode="HTML")


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    user_id = update.message.from_user.id
    if not context.args:
        await update.message.reply_text("Specify the task ID to complete: /done <id>")
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid task ID")
        return

    completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "UPDATE tasks SET completed_at=? WHERE id=? AND user_id=? AND completed_at IS NULL",
        (completed_at, task_id, user_id),
    )
    if c.rowcount == 0:
        await update.message.reply_text("Task not found or already completed")
    else:
        await update.message.reply_text(f"Task {task_id} marked as completed.")
    conn.commit()
    conn.close()


async def update_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    user_id = update.message.from_user.id
    if not context.args:
        await update.message.reply_text(
            "Specify the task ID and fields: /update <id> key=value,..."
        )
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid task ID")
        return

    text = " ".join(context.args[1:])
    task_text, params = parse_add_command(text)
    fields = []
    values = []

    if task_text:
        fields.append("task=?")
        values.append(task_text)

    allowed_fields = ["who", "category", "tags"]
    for k, v in params.items():
        if k in allowed_fields:
            fields.append(f"{k}=?")
            values.append(v)

    if not fields:
        await update.message.reply_text("No valid fields to update.")
        return

    fields.append("updated_at=?")
    values.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    values.append(task_id)
    values.append(user_id)

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    query = f"UPDATE tasks SET {', '.join(fields)} WHERE id=? AND user_id=?"
    c.execute(query, tuple(values))
    if c.rowcount == 0:
        await update.message.reply_text("Task not found or nothing updated.")
    else:
        await update.message.reply_text(f"Task {task_id} updated.")
    conn.commit()
    conn.close()


async def delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    user_id = update.message.from_user.id
    if not context.args:
        await update.message.reply_text("Specify the task ID to delete: /delete <id>")
        return

    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid task ID")
        return

    keyboard = [
        [
            InlineKeyboardButton("✅ Yes", callback_data=f"delete_yes:{task_id}:{user_id}"),
            InlineKeyboardButton("❌ No", callback_data=f"delete_no:{task_id}:{user_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Are you sure you want to delete task <b>{task_id}</b>?",
        parse_mode="HTML",
        reply_markup=reply_markup
    )


async def handle_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    assert query is not None
    await query.answer()

    assert query is not None
    data = query.data.split(":")
    action, task_id, user_id = data[0], int(data[1]), int(data[2])
    requesting_user = query.from_user.id

    if requesting_user != user_id:
        await query.edit_message_text("❌ You are not allowed to confirm this deletion.")
        return

    if action == "delete_yes":
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM tasks WHERE id=? AND user_id=?", (task_id, user_id))
        conn.commit()
        conn.close()
        await query.edit_message_text(f"🗑️ Task <b>{task_id}</b> deleted.", parse_mode="HTML")

    elif action == "delete_no":
        await query.edit_message_text(f"❎ Deletion of task <b>{task_id}</b> canceled.", parse_mode="HTML")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    help_text = """
Todo Bot Commands:

/add - <task description> [who=..., category=..., tags=...] - Add a new task.
/list - [task=..., who=..., category=..., tags=..., show_completed=1] - List tasks.
/done - <task_id> - Mark a task as completed.
/delete - <task_id> - Delete a task (with confirmation).
/update - <task_id> <new task description> [who=..., category=..., tags=...] - Update task.
/help - Show this help.
/start - Show this help.
"""
    await update.message.reply_text(help_text)


commands = [
    BotCommand("add", "Add a new task"),
    BotCommand("list", "List your tasks"),
    BotCommand("done", "Mark a task as completed"),
    BotCommand("delete", "Delete a task"),
    BotCommand("update", "Update task fields"),
    BotCommand("start", "Show help"),
    BotCommand("help", "Show help"),
]


async def post_init(app):
    await app.bot.set_my_commands(commands)
    print("Bot running with autocomplete!")


if __name__ == "__main__":
    init_db()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("Error: TELEGRAM_BOT_TOKEN environment variable not set.")
        exit(1)

    app = ApplicationBuilder().token(bot_token).post_init(post_init).build()
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("list", list_tasks))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CommandHandler("update", update_task))
    app.add_handler(CommandHandler("delete", delete_task))
    app.add_handler(CallbackQueryHandler(handle_delete_callback, pattern=r"^delete_"))
    app.add_handler(CommandHandler("start", help_command))
    app.add_handler(CommandHandler("help", help_command))

    app.run_polling()
