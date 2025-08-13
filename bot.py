# activator_bot_v3.2_pro_fixed.py
import logging
import datetime
import json
import asyncio
import os
from io import BytesIO  # <-- This is important for creating the in-memory file
from functools import lru_cache
from typing import Optional, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application, CommandHandler, ConversationHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)

# --- CONFIGURATION ---
# --- SECURITY WARNING ---
# It is highly recommended to NOT hard-code your token here.
# Use environment variables instead for better security.
# Example: ACTIVATOR_BOT_TOKEN = os.environ.get("ACTIVATOR_BOT_TOKEN")
ACTIVATOR_BOT_TOKEN = "8214572390:AAFDaJICbwdGCCpIuGR-ZFxSYzF48JyyKZc" # Replace with your token
ADMIN_CHANNEL_ID = "@twactivator"
ADMIN_USERNAME = "ceo_metaverse"
LICENSE_FILE = "licenses.json"
REMINDER_DAYS_BEFORE_EXPIRY = 7
BOT_VERSION = "3.2-PRO"

# --- PERFORMANCE OPTIMIZATIONS ---
license_cache = {}
cache_timestamp = None
CACHE_DURATION = 60  # seconds

# --- UI & MESSAGES ---
MESSAGES = {
    "welcome": (
        "<b>⚡ TW Activator Suite Pro</b>\n"
        "<i>Enterprise-grade bot deployment system.</i>\n\n"
        "» <b>🚀 Activate:</b> Deploy a new bot instance\n"
        "» <b>📊 Dashboard:</b> Manage your subscriptions\n"
        "» <b>🆘 Support:</b> Get instant assistance\n\n"
        f"<code>Version: {BOT_VERSION} | Response: &lt;1ms</code>"
    ),
    "help": (
        "<b>🆘 Help &amp; Support Center</b>\n\n"
        "This bot allows you to activate and manage your bot subscriptions with enterprise-level reliability.\n\n"
        "<b><u>Core Commands:</u></b>\n"
        "<code>/start</code> or <code>/menu</code> - Main menu\n"
        "<code>/mybots</code> - Subscription dashboard\n\n"
        "<b><u>Process Commands:</u></b>\n"
        "<code>/cancel</code> - Abort current operation"
    ),
    "ask_key": "<b>▌ STEP 1: LICENSE VALIDATION</b>\n\n🔑 Please provide your activation key:",
    "ask_token": "<b>▌ STEP 2: BOT CONFIGURATION</b>\n\n🤖 Please provide the API Token for your bot:",
    "ask_admin_id": "<b>▌ STEP 3: ADMIN SETUP</b>\n\n👤 Provide the numeric <b>User ID</b> for the primary administrator:",
    "ask_support_id": "<b>▌ STEP 4: SUPPORT SETUP</b>\n\n💬 Provide the numeric <b>User ID</b> for the support contact:",
    "ask_channel_id": "<b>▌ STEP 5: CHANNEL SETUP</b>\n\n📢 Provide the <b>Notification Channel</b> (<code>@username</code> or <code>-100...</code> ID):",
    "final_summary_header": "<b>▌ FINAL CONFIRMATION</b>\n\n⚡ Review your deployment configuration:",
    "final_summary_footer": "\n<i>⚠️ This action is final. License will be consumed.</i>",
    "activation_cancelled": "❌ Activation process cancelled.",
    "no_active_op": "ℹ️ No active operation to cancel.",
    "processing": "<code>⚡ Processing at light speed...</code>",
    "success_final": (
        "✅ <b>Deployment Successful!</b>\n\n"
        "🚀 Your bot configuration has been deployed.\n"
        "📊 Check your dashboard with /mybots\n\n"
        "<i>Processing time: &lt;100ms</i>"
    ),
    "invalid_key": "❌ <b>Invalid License Key</b>\n\nPlease check your key and try again. Ensure it is in UPPERCASE.",
    "key_already_used": "⚠️ <b>Key Already Used</b>\n\nThis license has already been activated.",
    "invalid_token": "❌ <b>Invalid Bot Token</b>\n\nPlease provide a valid Telegram bot token.",
    "invalid_id": "❌ <b>Invalid User ID</b>\n\nPlease provide a valid numeric user ID.",
    "invalid_channel": "❌ <b>Invalid Channel</b>\n\nPlease provide a valid channel username or ID."
}

# --- LOGGING ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- STATE DEFINITIONS ---
(AWAITING_KEY, AWAITING_BOT_CHOICE, AWAITING_TOKEN, AWAITING_ADMIN_ID,
 AWAITING_SUPPORT_ID, AWAITING_CHANNEL_ID, AWAITING_CONFIRMATION) = range(7)

# --- OPTIMIZED HELPER FUNCTIONS ---
@lru_cache(maxsize=128)
def read_licenses() -> Dict[str, Any]:
    global license_cache, cache_timestamp
    current_time = datetime.datetime.now(datetime.timezone.utc)
    if cache_timestamp and (current_time - cache_timestamp).seconds < CACHE_DURATION:
        return license_cache
    try:
        with open(LICENSE_FILE, "r") as f:
            license_cache = json.load(f)
            cache_timestamp = current_time
            return license_cache
    except (FileNotFoundError, json.JSONDecodeError):
        with open(LICENSE_FILE, "w") as f: json.dump({}, f)
        return {}

def write_licenses(data: Dict[str, Any]) -> None:
    global cache_timestamp
    with open(LICENSE_FILE, "w") as f: json.dump(data, f, indent=2)
    cache_timestamp = None
    read_licenses.cache_clear()

async def validate_license_key(key: str) -> Optional[Dict[str, Any]]:
    licenses = read_licenses()
    return licenses.get(key.strip().upper())

async def mark_key_as_used(key: str, user_id: int, user_data: dict) -> None:
    licenses = read_licenses()
    if key in licenses:
        licenses[key].update({
            "is_used": True,
            "activated_by_user_id": user_id,
            "activation_date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "expiration_date": (datetime.datetime.now(datetime.timezone.utc) +
                               datetime.timedelta(days=licenses[key]["duration_days"])).isoformat(),
            "bot_token": user_data.get("bot_token", ""),
            "admin_id": user_data.get("admin_id", ""),
            "support_id": user_data.get("support_id", ""),
            "channel_id": user_data.get("channel_id", "")
        })
        write_licenses(licenses)

async def check_expirations(context: ContextTypes.DEFAULT_TYPE) -> None:
    licenses = read_licenses()
    current_date = datetime.datetime.now(datetime.timezone.utc)
    for key, data in licenses.items():
        if data.get("is_used") and "expiration_date" in data:
            expiry_date = datetime.datetime.fromisoformat(data["expiration_date"])
            days_until_expiry = (expiry_date - current_date).days
            if 0 < days_until_expiry <= REMINDER_DAYS_BEFORE_EXPIRY:
                user_id = data.get("activated_by_user_id")
                if user_id:
                    try:
                        reminder_msg = (f"⚠️ <b>License Expiring Soon!</b>\n\n"
                                        f"Your {data['plan_name']} subscription expires in {days_until_expiry} days.\n"
                                        f"Contact @{ADMIN_USERNAME} to renew.")
                        await context.bot.send_message(chat_id=user_id, text=reminder_msg, parse_mode=ParseMode.HTML)
                    except Exception as e:
                        logger.error(f"Failed to send reminder to {user_id}: {e}")

# === CONVERSATION FLOW HANDLERS ===

async def start_activation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("⚡ Starting activation...")
    context.user_data.clear()
    context.user_data["user_id"] = query.from_user.id
    context.user_data["username"] = query.from_user.username or "Unknown"
    await query.edit_message_text(MESSAGES["ask_key"], parse_mode=ParseMode.HTML)
    return AWAITING_KEY

async def received_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    key = update.message.text.strip().upper()
    processing_msg = await update.message.reply_text(MESSAGES["processing"], parse_mode=ParseMode.HTML)
    license_data = await validate_license_key(key)
    if not license_data:
        await processing_msg.edit_text(MESSAGES["invalid_key"], parse_mode=ParseMode.HTML)
        return ConversationHandler.END
    if license_data.get("is_used", False):
        await processing_msg.edit_text(MESSAGES["key_already_used"], parse_mode=ParseMode.HTML)
        return ConversationHandler.END
    context.user_data["license_key"] = key
    context.user_data["license_data"] = license_data
    await processing_msg.edit_text(MESSAGES["ask_token"], parse_mode=ParseMode.HTML)
    return AWAITING_TOKEN

async def received_bot_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pass

async def received_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    token = update.message.text.strip()
    if not token or len(token) < 40 or ":" not in token:
        await update.message.reply_text(MESSAGES["invalid_token"], parse_mode=ParseMode.HTML)
        return AWAITING_TOKEN
    context.user_data["bot_token"] = token
    await update.message.reply_text(MESSAGES["ask_admin_id"], parse_mode=ParseMode.HTML)
    return AWAITING_ADMIN_ID

async def received_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    admin_id = update.message.text.strip()
    if not admin_id.isdigit():
        await update.message.reply_text(MESSAGES["invalid_id"], parse_mode=ParseMode.HTML)
        return AWAITING_ADMIN_ID
    context.user_data["admin_id"] = admin_id
    await update.message.reply_text(MESSAGES["ask_support_id"], parse_mode=ParseMode.HTML)
    return AWAITING_SUPPORT_ID

async def received_support_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    support_id = update.message.text.strip()
    if not support_id.isdigit():
        await update.message.reply_text(MESSAGES["invalid_id"], parse_mode=ParseMode.HTML)
        return AWAITING_SUPPORT_ID
    context.user_data["support_id"] = support_id
    await update.message.reply_text(MESSAGES["ask_channel_id"], parse_mode=ParseMode.HTML)
    return AWAITING_CHANNEL_ID

async def received_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    channel_id = update.message.text.strip()
    if not (channel_id.startswith("@") or (channel_id.startswith("-") and channel_id[1:].isdigit())):
        await update.message.reply_text(MESSAGES["invalid_channel"], parse_mode=ParseMode.HTML)
        return AWAITING_CHANNEL_ID
    context.user_data["channel_id"] = channel_id
    license_data = context.user_data["license_data"]
    summary = (
        f"{MESSAGES['final_summary_header']}\n\n"
        f"📋 <b>Plan:</b> {license_data['plan_name']}\n"
        f"🔑 <b>License:</b> <code>{context.user_data['license_key'][:8]}...</code>\n"
        f"🤖 <b>Bot Token:</b> <code>...{context.user_data['bot_token'][-8:]}</code>\n"
        f"👤 <b>Admin ID:</b> <code>{context.user_data['admin_id']}</code>\n"
        f"💬 <b>Support ID:</b> <code>{context.user_data['support_id']}</code>\n"
        f"📢 <b>Channel:</b> <code>{context.user_data['channel_id']}</code>\n"
        f"{MESSAGES['final_summary_footer']}"
    )
    keyboard = [
        [InlineKeyboardButton("✅ Confirm &amp; Deploy", callback_data="confirm_final")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return AWAITING_CONFIRMATION

async def final_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Final deployment confirmation. Sends a text summary AND a config.py file."""
    query = update.callback_query
    await query.answer("⚡ Deploying...")
    
    await query.edit_message_text(MESSAGES["processing"], parse_mode=ParseMode.HTML)
    
    await mark_key_as_used(
        context.user_data["license_key"],
        context.user_data["user_id"],
        context.user_data
    )
    
    # --- 1. SEND THE TEXT NOTIFICATION (Your current method) ---
    admin_notification_text = (
        f"🚀 <b>New Bot Deployment</b>\n\n"
        f"👤 <b>User:</b> @{context.user_data['username']} ({context.user_data['user_id']})\n"
        f"📋 <b>Plan:</b> {context.user_data['license_data']['plan_name']}\n"
        f"🔑 <b>License:</b> <code>{context.user_data['license_key']}</code>\n"
        f"🤖 <b>Token:</b> <code>{context.user_data['bot_token']}</code>\n"
        f"👤 <b>Admin:</b> <code>{context.user_data['admin_id']}</code>\n"
        f"💬 <b>Support:</b> <code>{context.user_data['support_id']}</code>\n"
        f"📢 <b>Channel:</b> <code>{context.user_data['channel_id']}</code>\n"
        f"⏰ <b>Time:</b> {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHANNEL_ID,
            text=admin_notification_text,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Failed to send admin text notification: {e}")

    # --- 2. CREATE AND SEND THE config.py FILE (Your old method) ---
    try:
        licenses = read_licenses()
        license_data = licenses[context.user_data['license_key']]
        expiration_date = datetime.datetime.fromisoformat(license_data['expiration_date'])
        expiration_timestamp = int(expiration_date.timestamp())
        
        config_content = (
            f"# This file was auto-generated by the Activator Bot.\n"
            f"# Activated on: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
            f'BOT_TOKEN = "{context.user_data["bot_token"]}"\n'
            f'INITIAL_ADMIN_ID = {context.user_data["admin_id"]}\n'
            f'ADMIN_CHANNEL = "{context.user_data["channel_id"]}"\n' 
            f'SUPPORT_ID = {context.user_data["support_id"]}\n\n'
            f"# --- License Information ---\n"
            f'LICENSE_KEY = "{context.user_data["license_key"]}"\n'
            f'PLAN_NAME = "{context.user_data["license_data"]["plan_name"]}"\n'
            f'EXPIRATION_TIMESTAMP = {expiration_timestamp} # Expires on: {expiration_date.strftime("%Y-%m-%d %H:%M:%S")} UTC\n'
        )
        
        config_file = BytesIO(config_content.encode('utf-8'))
        config_file.name = "config.py"
        
        file_caption = (
            f"✅ <b>New Bot Activation Request</b>\n\n"
            f"<b>User:</b> @{context.user_data['username']} ({context.user_data['user_id']})\n"
            f"<b>Plan:</b> {context.user_data['license_data']['plan_name']}\n"
            f"<b>Key Used:</b> {context.user_data['license_key']}\n\n"
            f"<i>The config.py file is attached. Please deploy the bot for this user.</i>"
        )
        
        await context.bot.send_document(
            chat_id=ADMIN_CHANNEL_ID,
            document=config_file,
            caption=file_caption,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Failed to create or send config.py file: {e}")

    # --- 3. SEND SUCCESS MESSAGE TO USER ---
    await query.edit_message_text(MESSAGES["success_final"], parse_mode=ParseMode.HTML)
    context.user_data.clear()
    return ConversationHandler.END

# === UI & COMMAND HANDLERS ===
async def start_and_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data: context.user_data.clear()
    keyboard = [
        [InlineKeyboardButton("🚀 Activate New Bot", callback_data="activate")],
        [InlineKeyboardButton("📊 Dashboard", callback_data="dashboard")],
        [InlineKeyboardButton("🆘 Help & Support", callback_data="support_menu")],
    ]
    if update.message:
        await update.message.reply_text(MESSAGES['welcome'], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(MESSAGES['welcome'], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [[InlineKeyboardButton(f"👤 Contact Admin (@{ADMIN_USERNAME})", url=f"https://t.me/{ADMIN_USERNAME}")]]
    if update.message:
        await update.message.reply_text(MESSAGES['help'], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(MESSAGES['help'], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def display_dashboard(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int) -> None:
    licenses = read_licenses()
    user_bots = [data for key, data in licenses.items() if data.get("activated_by_user_id") == user_id]
    if not user_bots:
        await context.bot.send_message(chat_id=chat_id, text="📊 <b>No Active Subscriptions</b>\n\nYou don't have any bot subscriptions yet.", parse_mode=ParseMode.HTML)
        return
    await context.bot.send_message(chat_id=chat_id, text="📊 <b>Subscription Dashboard</b>\n\n<i>Loading your bots...</i>", parse_mode=ParseMode.HTML)
    for bot_data in user_bots:
        try:
            expiry_date = datetime.datetime.fromisoformat(bot_data['expiration_date'])
            days_left = (expiry_date - datetime.datetime.now(datetime.timezone.utc)).days
            if days_left > 30: status, status_emoji = "✅ Active", "🟢"
            elif days_left > 7: status, status_emoji = "⚠️ Expiring Soon", "🟡"
            elif days_left > 0: status, status_emoji = "⚠️ Expiring Very Soon", "🟠"
            else: status, status_emoji = "❌ Expired", "🔴"
            expiry_text = f"{expiry_date.strftime('%Y-%m-%d')} ({days_left} days)" if days_left > 0 else f"Expired on {expiry_date.strftime('%Y-%m-%d')}"
            bot_info = (f"{status_emoji} <b>{bot_data['plan_name']}</b>\n"
                        f"├ <b>Status:</b> {status}\n"
                        f"├ <b>Expires:</b> <code>{expiry_text}</code>\n"
                        f"├ <b>Bot Token:</b> <code>...{bot_data.get('bot_token', 'N/A')[-8:]}</code>\n"
                        f"└ <b>Activated:</b> <code>{bot_data.get('activation_date', 'N/A')[:10]}</code>")
            keyboard = []
            if days_left <= 30: keyboard.append([InlineKeyboardButton("♻️ Renew Now", url=f"https://t.me/{ADMIN_USERNAME}")])
            await context.bot.send_message(chat_id=chat_id, text=bot_info, reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None, parse_mode=ParseMode.HTML)
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Error displaying bot data for user {user_id}: {e}")

async def my_bots_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await display_dashboard(context, user_id=update.effective_user.id, chat_id=update.effective_chat.id)

async def dashboard_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("⚡ Loading dashboard...")
    await display_dashboard(context, user_id=query.from_user.id, chat_id=query.message.chat_id)

async def support_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(MESSAGES['help'], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"👤 Contact Admin (@{ADMIN_USERNAME})", url=f"https://t.me/{ADMIN_USERNAME}")]]), parse_mode=ParseMode.HTML)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    was_in_conversation = bool(context.user_data)
    if was_in_conversation: context.user_data.clear()
    cancel_message = MESSAGES['activation_cancelled'] if was_in_conversation else MESSAGES['no_active_op']
    if update.callback_query:
        await update.callback_query.answer("Cancelled")
        await update.callback_query.edit_message_text(cancel_message, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(cancel_message, parse_mode=ParseMode.HTML)
    return ConversationHandler.END

# === ERROR HANDLER ===
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} caused error {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("⚠️ <b>An error occurred</b>\n\nPlease try again or contact support.", parse_mode=ParseMode.HTML)
    except: pass

# === MAIN FUNCTION ===
def main() -> None:
    application = (Application.builder().token(ACTIVATOR_BOT_TOKEN).concurrent_updates(True).pool_timeout(10.0)
                   .connect_timeout(10.0).read_timeout(10.0).write_timeout(10.0).build())
    
    job_queue = application.job_queue
    job_queue.run_repeating(check_expirations, interval=86400, first=10)
    
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_activation, pattern="^activate$")],
        states={
            AWAITING_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_key)],
            AWAITING_BOT_CHOICE: [CallbackQueryHandler(received_bot_choice, pattern="^bot_")],
            AWAITING_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_token)],
            AWAITING_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_admin_id)],
            AWAITING_SUPPORT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_support_id)],
            AWAITING_CHANNEL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_channel_id)],
            AWAITING_CONFIRMATION: [
                CallbackQueryHandler(final_confirmation, pattern="^confirm_final$"),
                CallbackQueryHandler(cancel_command, pattern="^cancel$")
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CallbackQueryHandler(cancel_command, pattern="^cancel$"),
            CommandHandler("start", start_and_menu_command),
            CommandHandler("menu", start_and_menu_command)
        ],
        per_user=True,
        per_chat=True,
        allow_reentry=True
    )
    
    application.add_handler(CommandHandler("start", start_and_menu_command))
    application.add_handler(CommandHandler("menu", start_and_menu_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("mybots", my_bots_command_handler))
    
    application.add_handler(CallbackQueryHandler(dashboard_callback_handler, pattern="^dashboard$"))
    application.add_handler(CallbackQueryHandler(support_menu_callback, pattern="^support_menu$"))
    application.add_handler(CallbackQueryHandler(start_and_menu_command, pattern="^menu$"))
    
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    
    logger.info(f"🚀 Activator Bot V{BOT_VERSION} is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()