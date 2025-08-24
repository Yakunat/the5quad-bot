import os
import logging
import random
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from database import FootballDatabase

# Load environment variables from .env file
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get bot token and admin IDs from environment
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = set(map(int, os.getenv('ADMIN_IDS', '').split(',')))

# Initialize database
db = FootballDatabase()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    user_id = user.id
    
    # Check if user is admin
    admin_status = "🔧 Admin" if user_id in ADMIN_IDS else "⚽ Player"
    
    await update.message.reply_html(
        f"Hi {user.mention_html()}! ⚽\n\n"
        f"Welcome to The5Squad Bot!\n"
        f"Status: {admin_status}\n\n"
        f"I help organize your football games.\n\n"
        f"Commands:\n"
        f"/events - Show upcoming events\n"
        f"/mystatus - Check your registrations\n"
        f"/join <event_id> - Join by ID\n"
        f"/leave <event_id> - Leave by ID\n"
        f"/help - Show all commands\n"
        f"/create_event - Create a new game (admin only)"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    help_text = """⚽ The5Squad Bot Commands

For Everyone:
/start - Get started with the bot
/help - Show this help message
/events - Show upcoming events
/mystatus - Check your registrations
/join <event_id> - Join by ID
/leave <event_id> - Leave by ID

For Admins Only:
/create_event DD/MM/YYYY HH:MM max_players [description]
/cancel_event - Cancel an event
/randomize_teams event_id - Create random teams

Examples:
/create_event 25/12/2024 19:00 10 Christmas game
/create_event 01/01/2025 15:00 8
/join 12
/leave 12

How it works:
1. Admin creates an event
2. Players use /events → Details → Join (or /join <id>)
3. First come, first served for main list
4. Extra players go to reserve list
5. Admin can create random teams

Let's play football! ⚽"""
    await update.message.reply_text(help_text)

async def create_event_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create a new football event (admin only)."""
    user_id = update.effective_user.id
    
    # Check if user is admin
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Only admins can create events!")
        return
    
    # Parse command arguments
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "❌ Usage: /create_event DD/MM/YYYY HH:MM max_players [description]\n\n"
            "Examples:\n"
            "/create_event 25/12/2024 19:00 10 Christmas game\n"
            "/create_event 01/01/2025 15:00 8"
        )
        return
    
    try:
        date_str = args[0]
        time_str = args[1]
        max_players = int(args[2])
        description = " ".join(args[3:]) if len(args) > 3 else ""
        
        # Validate date format
        datetime.strptime(date_str, "%d/%m/%Y")
        
        # Validate time format
        datetime.strptime(time_str, "%H:%M")
        
        # Validate max_players
        if max_players < 2 or max_players > 50:
            await update.message.reply_text("❌ Max players must be between 2 and 50")
            return
        
        # Create event in database
        event_id = db.create_event(date_str, time_str, max_players, user_id, description)
        
        # Create message with join button (send as a new message)
        event_text = format_event_message(event_id)
        keyboard = get_event_keyboard(event_id)
        
        await update.message.reply_text(
            event_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        
    except ValueError as e:
        await update.message.reply_text(
            "❌ Invalid format!\n\n"
            "Usage: /create_event DD/MM/YYYY HH:MM max_players [description]\n"
            "Date format: 25/12/2024\n"
            "Time format: 19:00"
        )

async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all upcoming events."""
    events = db.get_active_events()
    
    if not events:
        await update.message.reply_text("📅 No upcoming events scheduled.\n\nAsk an admin to create one!")
        return

    # If exactly one event, show full detail card with Join/Leave
    if len(events) == 1:
        event_id, date, time, max_players, description, created_by, created_at = events[0]
        event_text = format_event_message(event_id)
        keyboard = get_event_keyboard(event_id)
        await update.message.reply_text(event_text, reply_markup=keyboard, parse_mode='HTML')
        return

    # If multiple events, show compact list with Details buttons
    message = format_events_list(events)
    keyboard = get_events_list_keyboard(events)
    await update.message.reply_text(message, reply_markup=keyboard, parse_mode='HTML')

async def mystatus_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's registration status."""
    user_id = update.effective_user.id
    registrations = db.get_user_registrations(user_id)
    
    if not registrations:
        await update.message.reply_text("📊 You're not registered for any events yet.")
        return
    
    message = "📊 <b>Your Registrations:</b>\n\n"
    
    for event_id, date, time, reg_type in registrations:
        status_emoji = "✅" if reg_type == "main" else "⏳"
        status_text = "Main List" if reg_type == "main" else "Reserve List"
        
        message += f"{status_emoji} <b>Event {event_id}</b>\n"
        message += f"📅 {date} at {time}\n"
        message += f"📍 Status: {status_text}\n\n"
    
    await update.message.reply_text(message, parse_mode='HTML')

async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Power-user join by ID: /join <event_id>"""
    user = update.effective_user
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("❌ Usage: /join <event_id>")
        return
    try:
        event_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Event ID must be a number.")
        return

    success = db.register_user(event_id, user.id, user.username, user.first_name)
    if success:
        await update.message.reply_text(f"✅ Joined event {event_id}.")
        # Send updated event card
        event_text = format_event_message(event_id)
        keyboard = get_event_keyboard(event_id)
        await update.message.reply_text(event_text, reply_markup=keyboard, parse_mode='HTML')
    else:
        await update.message.reply_text("❌ You're already registered for this event or the event is unavailable.")

async def leave_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Power-user leave by ID: /leave <event_id>"""
    user = update.effective_user
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("❌ Usage: /leave <event_id>")
        return
    try:
        event_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Event ID must be a number.")
        return

    success = db.unregister_user(event_id, user.id)
    if success:
        await update.message.reply_text(f"✅ Left event {event_id}.")
        # Send updated event card
        event_text = format_event_message(event_id)
        keyboard = get_event_keyboard(event_id)
        await update.message.reply_text(event_text, reply_markup=keyboard, parse_mode='HTML')
    else:
        await update.message.reply_text("❌ You're not registered for this event or the event is unavailable.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user

    # New: open details as a new message (do not edit list)
    if data.startswith("view_"):
        event_id = int(data.split("_")[1])
        event = db.get_event(event_id)
        if not event:
            await query.message.reply_text("❌ This event is no longer available.")
            return
        new_text = format_event_message(event_id)
        keyboard = get_event_keyboard(event_id)
        await query.message.reply_text(new_text, reply_markup=keyboard, parse_mode='HTML')
        return
    
    if data.startswith("join_"):
        event_id = int(data.split("_")[1])
        # Try to register user
        success = db.register_user(event_id, user.id, user.username, user.first_name)
        
        if success:
            # Send updated event card as a new message (avoid edits)
            new_text = format_event_message(event_id)
            keyboard = get_event_keyboard(event_id)
            await query.message.reply_text(new_text, reply_markup=keyboard, parse_mode='HTML')
        else:
            await query.answer("❌ You're already registered for this event!", show_alert=True)
    
    elif data.startswith("leave_"):
        event_id = int(data.split("_")[1])
        
        # Try to unregister user
        success = db.unregister_user(event_id, user.id)
        
        if success:
            # Send updated event card as a new message (avoid edits)
            new_text = format_event_message(event_id)
            keyboard = get_event_keyboard(event_id)
            await query.message.reply_text(new_text, reply_markup=keyboard, parse_mode='HTML')
        else:
            await query.answer("❌ You're not registered for this event!", show_alert=True)

async def randomize_teams_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create random teams for an event (admin only)."""
    user_id = update.effective_user.id
    
    # Check if user is admin
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Only admins can randomize teams!")
        return
    
    # Parse command arguments
    if not context.args:
        await update.message.reply_text("❌ Usage: /randomize_teams event_id")
        return
    
    try:
        event_id = int(context.args[0])
        
        # Get event details
        event = db.get_event(event_id)
        if not event:
            await update.message.reply_text("❌ Event not found!")
            return
        
        # Get players
        players = db.get_players_for_teams(event_id)
        
        if len(players) < 2:
            await update.message.reply_text("❌ Need at least 2 players to create teams!")
            return
        
        # Shuffle players
        random.shuffle(players)
        
        # Split into two teams
        mid_point = len(players) // 2
        team1 = players[:mid_point]
        team2 = players[mid_point:]
        
        # If odd number, add extra player to team1
        if len(players) % 2 == 1:
            team1.append(team2.pop())
        
        # Format teams message
        message = f"⚽ <b>Random Teams for Event {event_id}</b>\n\n"
        message += f"🔴 <b>Team 1 ({len(team1)} players):</b>\n"
        for i, player in enumerate(team1, 1):
            message += f"{i}. {player['display_name']}\n"
        
        message += f"\n🔵 <b>Team 2 ({len(team2)} players):</b>\n"
        for i, player in enumerate(team2, 1):
            message += f"{i}. {player['display_name']}\n"
        
        message += "\nGood luck and have fun! ⚽"
        
        await update.message.reply_text(message, parse_mode='HTML')
        
    except ValueError:
        await update.message.reply_text("❌ Invalid event ID!")

def format_event_message(event_id: int) -> str:
    """Format event information for display."""
    event = db.get_event(event_id)
    if not event:
        return "❌ Event not found!"
    
    event_id, date, time, max_players, description, created_by, created_at, status = event
    registrations = db.get_event_registrations(event_id)
    
    message = f"⚽ <b>Football Event {event_id}</b>\n"
    message += f"📅 {date} at {time}\n"
    if description:
        message += f"📝 {description}\n"
    
    message += f"\n👥 <b>Players ({len(registrations['main'])}/{max_players}):</b>\n"
    
    if registrations['main']:
        for i, player in enumerate(registrations['main'], 1):
            name = player['first_name'] or player['username'] or str(player['user_id'])
            message += f"{i}. {name}\n"
    else:
        message += "<i>No players yet</i>\n"
    
    if registrations['reserve']:
        message += f"\n⏳ <b>Reserve List ({len(registrations['reserve'])}):</b>\n"
        for i, player in enumerate(registrations['reserve'], 1):
            name = player['first_name'] or player['username'] or str(player['user_id'])
            message += f"{i}. {name}\n"
    
    return message

def truncate(text: str, max_len: int = 100) -> str:
    if not text:
        return ""
    return text if len(text) <= max_len else text[:max_len - 1] + "…"

def format_events_list(events) -> str:
    """Render a compact list of multiple upcoming events."""
    # events: list of tuples [event_id, date, time, max_players, description, created_by, created_at]
    lines = ["📅 <b>Upcoming Events</b>", ""]
    for event in events:
        event_id, date, time, max_players, description, created_by, created_at = event
        regs = db.get_event_registrations(event_id)
        main_count = len(regs['main'])
        reserve_count = len(regs['reserve'])
        lines.append(f"#{event_id} • {date}, {time}")
        if reserve_count > 0:
            lines.append(f"👥 {main_count}/{max_players} (+{reserve_count})")
        else:
            lines.append(f"👥 {main_count}/{max_players}")
        if description:
            lines.append(f"📝 {truncate(description, 100)}")
        lines.append("")  # blank line between events
    return "\n".join(lines).strip()

def get_events_list_keyboard(events):
    """Create inline keyboard with 'Details #id' buttons for each event."""
    buttons = []
    row = []
    for idx, event in enumerate(events, start=1):
        event_id = event[0]
        row.append(InlineKeyboardButton(f"Details #{event_id}", callback_data=f"view_{event_id}"))
        # 2 buttons per row for compactness
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

def get_event_keyboard(event_id: int):
    """Create inline keyboard for event."""
    keyboard = [
        [
            InlineKeyboardButton("⚽ Join", callback_data=f"join_{event_id}"),
            InlineKeyboardButton("❌ Leave", callback_data=f"leave_{event_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main():
    """Start the bot."""
    # Check if bot token is loaded
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN not found in .env file!")
        return
    
    if not ADMIN_IDS or ADMIN_IDS == {0}:
        print("⚠️ Warning: No admin IDs found in .env file!")
    
    print(f"⚽ Starting The5Squad Bot...")
    print(f"📝 Admin IDs: {ADMIN_IDS}")
    
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("create_event", create_event_command))
    application.add_handler(CommandHandler("events", events_command))
    application.add_handler(CommandHandler("mystatus", mystatus_command))
    application.add_handler(CommandHandler("randomize_teams", randomize_teams_command))
    # New power-user commands
    application.add_handler(CommandHandler("join", join_command))
    application.add_handler(CommandHandler("leave", leave_command))
    
    # Register button handler
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Register error handler
    application.add_error_handler(error_handler)

    # Run the bot
    print("✅ Bot is running! Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == '__main__':
    main()
