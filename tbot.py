import sqlite3
from openpyxl import Workbook
import tempfile
import os
import re
from datetime import datetime
from dotenv import load_dotenv

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    Update,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

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
    """
    Parse key=value pairs (who, category, tags). Values may contain spaces/commas.
    Example: "who=Alice category=Work tags=urgent,homework"
    """
    pattern = r"(task|who|category|tags|show_completed)\s*=\s*(.*?)(?=\s+\w+\s*=|$)"
    return {k.lower(): v.strip() for k, v in re.findall(pattern, text)}


def parse_add_command(text: str):
    """
    Split free-text task description from trailing key=value params.
    Example:
      "Buy milk, eggs who=Alice tags=grocery,food"
    Returns: task (str), params (dict)
    """
    pattern = r"\b(who|category|tags)\s*="
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


def format_tasks(user_id: int, filters: dict) -> str:
    """
    Build the text message for tasks belonging to user_id applying filters dict.
    Returns a string (HTML formatted) ready to be sent with parse_mode="HTML".
    """
    query = "SELECT id, task, who, category, tags, created_at, updated_at, completed_at FROM tasks WHERE user_id=?"
    params = [user_id]
    print("Filters:", filters)

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
        return "No tasks found."

    message_lines = []
    for r in rows:
        tid, task, who, category, tags, created_at, updated_at, completed_at = r
        status = "✅" if completed_at else "❌"
        line = (
            f"<b>{tid}.</b> {escape_html(task)} | who: {escape_html_or_dash(who)} | "
            f"category: {escape_html_or_dash(category)} | tags: {escape_html_or_dash(tags)} | "
            f"created: {created_at} | updated: {updated_at or '-'} | completed: {completed_at or '-'} | {status}"
        )
        message_lines.append(line)
    return "\n".join(message_lines)


def escape_html(text: str) -> str:
    """Basic HTML-escape for the small set of characters that break parse_mode='HTML'."""
    if text is None:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def escape_html_or_dash(text: str) -> str:
    if not text:
        return "-"
    return escape_html(text)


# ---------------- Command handlers ----------------

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
    filters = parse_params(" ".join(context.args)) if context.args else {}
    message = format_tasks(user_id, filters)
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
            "Specify the task ID and fields: /update <id> <new description> [who=..., category=..., tags=...]"
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

    # Add updated_at
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


# ---------------- Delete with confirmation ----------------

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
            InlineKeyboardButton("❌ No", callback_data=f"delete_no:{task_id}:{user_id}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Are you sure you want to delete task <b>{task_id}</b>?",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


async def handle_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    assert query is not None
    await query.answer()

    data = query.data.split(":")
    action, task_id, user_id = data[0], int(data[1]), int(data[2])
    requesting_user = query.from_user.id

    # Only allow the user who requested the delete to confirm
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


# ---------------- Menu & menu handling ----------------

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    keyboard = [
        [InlineKeyboardButton("➕ Add Task", callback_data="menu_add")],
        [InlineKeyboardButton("📋 List Tasks", callback_data="menu_list")],
        [InlineKeyboardButton("✅ Mark Done", callback_data="menu_done")],
        [InlineKeyboardButton("🗑️ Delete Task", callback_data="menu_delete")],
        [InlineKeyboardButton("⬇️ Download Tasks", callback_data="menu_download")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="menu_help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📌 Main Menu — choose an action:", reply_markup=reply_markup)


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    assert query is not None
    await query.answer()

    if query.data == "menu_add":
        await query.edit_message_text("✍️ Use /add <task description> [who=..., category=..., tags=...]")
        return

    if query.data == "menu_list":
        # show tasks directly
        message = format_tasks(query.from_user.id, {})
        await query.edit_message_text(message, parse_mode="HTML")
        return

    if query.data == "menu_done":
        await query.edit_message_text("✅ Use /done <id> to mark a task as completed.")
        return

    if query.data == "menu_delete":
        await query.edit_message_text("🗑️ Use /delete <id> to remove a task.")
        return

    if query.data == "menu_help":
        await query.edit_message_text("ℹ️ Use /help to see all commands.")
        return
    
    if query.data == "menu_download":
        # Reuse the download command logic
        fake_update = Update(update.update_id, message=query.message)
        await download(fake_update, context)
        return


async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    user_id = update.message.from_user.id

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "SELECT id, task, who, category, tags, created_at, updated_at, completed_at FROM tasks WHERE user_id=?",
        (user_id,),
    )
    rows = c.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("No tasks to download.")
        return

    # Create Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Tasks"

    headers = [
        "ID",
        "Task",
        "Who",
        "Category",
        "Tags",
        "Created At",
        "Updated At",
        "Completed At",
    ]
    ws.append(headers)

    for row in rows:
        ws.append(row)

    # Save to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        filename = tmp.name
        wb.save(filename)

    # Send to user
    await update.message.reply_document(
        document=open(filename, "rb"),
        filename="tasks.xlsx",
        caption="📥 Here are your tasks.",
    )

    # Clean up
    os.remove(filename)

# ---------------- Help / start ----------------

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    help_text = """
Todo Bot Commands:

/add <task description> [who=..., category=..., tags=...] - Add a new task.
/list [task=..., who=..., category=..., tags=..., show_completed=1] - List tasks.
/done <task_id> - Mark a task as completed.
/delete <task_id> - Delete a task (with confirmation).
/update <task_id> <new task description> [who=..., category=..., tags=...] - Update task.
/menu - Open main menu.
/start - Show menu.
"""
    await update.message.reply_text(help_text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # show menu on /start
    await menu(update, context)


# ---------------- Commands registration & run ----------------

commands = [
    BotCommand("add", "Add a new task"),
    BotCommand("list", "List your tasks"),
    BotCommand("download", "Download your tasks"),
    BotCommand("done", "Mark a task as completed"),
    BotCommand("delete", "Delete a task"),
    BotCommand("update", "Update task fields"),
    BotCommand("menu", "Open main menu"),
    BotCommand("start", "Show menu/help"),
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

    # command handlers
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("list", list_tasks))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CommandHandler("update", update_task))
    app.add_handler(CommandHandler("delete", delete_task))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("download", download))

    # callback query handlers
    app.add_handler(CallbackQueryHandler(handle_delete_callback, pattern=r"^delete_"))
    app.add_handler(CallbackQueryHandler(handle_menu, pattern=r"^menu_"))

    app.run_polling()
