
"""
Full Premium Number Lookup Telegram Bot
Features:
 - Styled line-by-line info
 - Force Owner = "Baharul"
 - Remove unwanted/ads/telegram/channel fields from API result
 - Inline buttons: Refresh, Save Report, Clear
 - Anti-spam (cooldown per user)
 - Auto-detect numbers in groups and reply
 - Save lookup history per user in history.json
 - /menu, /history, /about commands
 - Welcome photo on /start
 - Robust error handling
"""

import re
import time
import json
import os
import requests
from datetime import datetime

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaPhoto
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from telegram.constants import ParseMode

# ---------------------------
# CONFIG - change these
# ---------------------------
BOT_TOKEN = "8444267803:AAFMzp9NIwMCXOUsv9PnErhdNn9sSwWUoNc"  # change if needed
API_URL = "https://subhxmouktik-number-api.onrender.com/api?key=BAHARUL&type=mobile&term="
OWNER_NAME = "@Hack_boy_04"
HISTORY_FILE = "history.json"    # saved in same folder
COOLDOWN_SECONDS = 5             # per-user cooldown (anti-spam)
WELCOME_PHOTO_URL = "https://i.imgur.com/3fJ1P4R.png"  # replace if you want custom

# ---------------------------
# Utilities
# ---------------------------
def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_history(all_hist):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(all_hist, f, indent=2, ensure_ascii=False)

def add_history(user_id: str, number: str, summary: str):
    all_hist = load_history()
    if user_id not in all_hist:
        all_hist[user_id] = []
    all_hist[user_id].insert(0, {
        "number": number,
        "summary": summary,
        "time": datetime.utcnow().isoformat() + "Z"
    })
    # cap history to last 50 items per user
    all_hist[user_id] = all_hist[user_id][:50]
    save_history(all_hist)

def cleanup_api_data(data: dict) -> dict:
    """ Remove unwanted keys and force owner name later """
    # keys to remove (common ad/telegram/channel keys)
    unwanted = {"owner","telegram","tg","channel","owner_channel","owner_telegram","ads","ad","promo","promote","website"}
    cleaned = {}
    for k, v in data.items():
        if k.lower() in unwanted:
            continue
        cleaned[k] = v
    return cleaned

def format_info_message(number: str, api_data: dict) -> str:
    """
    Builds a nice markdown message from api_data.
    Forces Owner = OWNER_NAME
    """
    lines = []
    lines.append("📱 *Number Lookup Report*")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(f"👤 *Owner:* {OWNER_NAME}")
    lines.append(f"📞 *Number:* `{number}`")

    # show each field line-by-line
    for key, value in api_data.items():
        # skip empty values
        if value is None or (isinstance(value, str) and value.strip() == ""):
            continue
        clean_key = key.replace("_", " ").title()
        # convert dict/list to readable text
        if isinstance(value, (dict, list)):
            value_text = json.dumps(value, ensure_ascii=False)
        else:
            value_text = str(value)
        lines.append(f"• *{clean_key}:* {value_text}")

    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("🔎 Lookup Completed")
    return "\n".join(lines)

def extract_first_number(text: str) -> str | None:
    """
    Find a 10-digit / 11-digit / international-like number in text.
    Returns the first found numeric string (digits only).
    """
    # look for sequences of digits length 7-15 to be flexible, then pick common 10-digit
    matches = re.findall(r"\d{7,15}", text)
    if not matches:
        return None
    # prefer 10-digit or 11-digit if present
    for m in matches:
        if len(m) in (10,11):
            return m
    # else return first
    return matches[0]

# in-memory cooldown tracking
last_request_time = {}  # user_id -> timestamp

# ---------------------------
# Handlers
# ---------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome photo and message"""
    try:
        chat = update.effective_chat
        msg = (
            f"👋 *Welcome!* I am your Number Lookup Bot.\n\n"
            "Send any mobile number (or just paste text containing a number) and I'll fetch details.\n\n"
            "Type /menu to see available commands."
        )
        # send photo + caption
        await context.bot.send_photo(
            chat_id=chat.id,
            photo=WELCOME_PHOTO_URL,
            caption=msg,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        # fallback plain text
        await update.message.reply_text("Welcome! Send any mobile number to lookup.", parse_mode=ParseMode.MARKDOWN)

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "🔹 *About this Bot*\n"
        f"Owner: *{OWNER_NAME}*\n"
        "This bot looks up mobile number information from a connected API.\n"
        "It filters out promotions/telegram channels and always shows Owner as Baharul.\n\n"
        "Commands: /menu /history /about\n"
    )
    await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN)

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "📘 *Bot Menu*\n"
        "• Send a number or paste text containing a number to lookup\n"
        "• /history - show your last lookups\n"
        "• /about - about this bot\n\n"
        "Auto-Reply: If you paste a number in a group, I will reply automatically."
    )
    await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN)

async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    all_hist = load_history()
    user_hist = all_hist.get(str(user.id), [])
    if not user_hist:
        await update.message.reply_text("📚 You have no lookup history yet.")
        return
    lines = ["📚 *Your Lookup History*"]
    for i, item in enumerate(user_hist[:20], start=1):
        t = item.get("time", "")[:19].replace("T", " ")
        lines.append(f"{i}. `{item.get('number')}` — {item.get('summary')} ({t} UTC)")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main handler for incoming messages (private or group)"""
    message = update.effective_message
    text = message.text or message.caption or ""
    if not text:
        return

    # extract first found number
    number = extract_first_number(text)
    if not number:
        return  # ignore messages without number

    user = update.effective_user
    user_id = str(user.id)

    # anti-spam cooldown
    now = time.time()
    last = last_request_time.get(user_id, 0)
    if now - last < COOLDOWN_SECONDS:
        remain = int(COOLDOWN_SECONDS - (now - last))
        await message.reply_text(f"⚠️ Please wait {remain}s before next lookup.")
        return
    last_request_time[user_id] = now

    # perform lookup and reply with buttons
    await perform_lookup_and_reply(chat_id=message.chat_id, message=message, number=number, context=context, user_id=user_id)

async def perform_lookup_and_reply(chat_id, message, number, context: ContextTypes.DEFAULT_TYPE, user_id: str):
    """Calls API, formats response, sends message with inline buttons"""
    # call API
    api_endpoint = API_URL + number
    try:
        res = requests.get(api_endpoint, timeout=10)
        res.raise_for_status()
        data = res.json() if res.text else {}
    except Exception:
        # API failure handling
        await message.reply_text("❌ API Error — couldn't fetch data right now. Please try later.")
        return

    if not isinstance(data, dict):
        # sometimes API may return string or list
        # normalize to dict
        data = {"raw": data}

    # clean and remove unwanted fields
    cleaned = cleanup_api_data(data)

    # build message
    text = format_info_message(number, cleaned)
    # inline buttons (refresh, save, clear)
    keyboard = [
        [
            InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh|{number}"),
            InlineKeyboardButton("💾 Save Report", callback_data=f"save|{number}"),
            InlineKeyboardButton("🗑 Clear", callback_data=f"clear|{number}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # send as Markdown
    try:
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
      )
    except Exception as e:
        # fallback: send plain text
        await context.bot.send_message(chat_id=chat_id, text=text)

    # auto-save a short summary to history (not full) — optional
    summary = cleaned.get("status") or cleaned.get("sim") or list(cleaned.values())[:1]
    # make summary text compact
    if isinstance(summary, (list, dict)):
        summary_text = json.dumps(summary, ensure_ascii=False)[:100]
    else:
        summary_text = str(summary) if summary else "No summary"
    add_history(user_id, number, summary_text)

# ---------------------------
# CallbackQuery handlers for inline buttons
# ---------------------------
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # acknowledge

    data = query.data or ""
    parts = data.split("|", 1)
    if len(parts) != 2:
        return
    action, number = parts[0], parts[1]

    user = update.effective_user
    user_id = str(user.id)

    if action == "refresh":
        # re-run lookup and edit message to new content
        api_endpoint = API_URL + number
        try:
            res = requests.get(api_endpoint, timeout=10)
            res.raise_for_status()
            d = res.json() if res.text else {}
        except Exception:
            await query.edit_message_text("❌ API Error while refreshing. Try again later.")
            return

        cleaned = cleanup_api_data(d if isinstance(d, dict) else {"raw": d})
        new_text = format_info_message(number, cleaned)
        try:
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh|{number}"),
                    InlineKeyboardButton("💾 Save Report", callback_data=f"save|{number}"),
                    InlineKeyboardButton("🗑 Clear", callback_data=f"clear|{number}")
                ]
            ]
            await query.edit_message_text(new_text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            await query.edit_message_text(new_text)

    elif action == "save":
        # Save the item again to history with timestamp
        # For save, try to call API to get short summary
        try:
            res = requests.get(API_URL + number, timeout=10)
            res.raise_for_status()
            d = res.json() if res.text else {}
        except Exception:
            await query.answer("❌ Cannot reach API to save.", show_alert=True)
            return
        cleaned = cleanup_api_data(d if isinstance(d, dict) else {"raw": d})
        summary = cleaned.get("status") or cleaned.get("sim") or list(cleaned.values())[:1]
        if isinstance(summary, (list, dict)):
            summary_text = json.dumps(summary, ensure_ascii=False)[:100]
        else:
            summary_text = str(summary) if summary else "No summary"
        add_history(user_id, number, summary_text)
        await query.answer("Saved to your history ✅", show_alert=False)

    elif action == "clear":
        # delete the message (if bot has rights) or edit to 'cleared'
        try:
            await query.delete_message()
        except Exception:
            try:
                await query.edit_message_text("🗑 Cleared by user.")
            except Exception:
                pass

# ---------------------------
# Main
# ---------------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("history", history_cmd))

    # messages (both private and groups)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    # callback queries for inline buttons
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    print("Bot started...")
    app.run_polling()  # Termux friendly (no asyncio.run)


if __name__ == "__main__":
    main()
  
