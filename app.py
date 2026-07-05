import os
import re
import threading
import asyncio
from datetime import datetime
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ========== FLASK WEB SERVER (keeps Render alive) ==========
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

# ========== TELEGRAM BOT ==========
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable not set!")

# --- Age Calculator ---
def calculate_age(birth_date_str):
    try:
        birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d")
        today = datetime.now()
        years = today.year - birth_date.year
        months = today.month - birth_date.month
        days = today.day - birth_date.day
        
        if days < 0:
            months -= 1
            # Get days in previous month
            prev_month = today.replace(day=1) - timedelta(days=1)
            days += prev_month.day
        if months < 0:
            years -= 1
            months += 12
            
        return f"🎂 You are **{years}** years, **{months}** months, and **{days}** days old!"
    except ValueError:
        return None

# --- Video Downloader (yt-dlp) ---
async def download_video(url):
    import yt_dlp
    
    ydl_opts = {
        'format': 'best[height<=720]',
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename
    except Exception as e:
        return None

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "🤖 **Welcome to Multi-Tool Bot!**\n\n"
        "Here's what I can do:\n"
        "• `/age` - Calculate your exact age\n"
        "• Send any video URL - Download videos\n\n"
        "Just send me a YouTube/Instagram/TikTok link!"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")

async def age_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📅 Please send your birthdate in this format:\n`YYYY-MM-DD`\n\nExample: `2000-01-15`",
        parse_mode="Markdown"
    )
    context.user_data['waiting_for_age'] = True

async def handle_age_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_for_age'):
        return
    
    user_input = update.message.text.strip()
    result = calculate_age(user_input)
    
    if result:
        await update.message.reply_text(result, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "❌ Invalid format! Please use:\n`YYYY-MM-DD`\n\nExample: `2000-01-15`",
            parse_mode="Markdown"
        )
        return  # Keep waiting for correct input
    
    context.user_data['waiting_for_age'] = False

async def handle_video_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_age'):
        return  # User is in age-calculator mode
    
    url = update.message.text.strip()
    
    # Check if it looks like a URL
    if not re.match(r'https?://[^\s]+', url):
        return
    
    await update.message.reply_text("⏳ Downloading video... Please wait.")
    
    # Create downloads folder
    os.makedirs('downloads', exist_ok=True)
    
    filename = await download_video(url)
    
    if filename and os.path.exists(filename):
        try:
            with open(filename, 'rb') as f:
                await update.message.reply_video(video=f, caption="✅ Download complete!")
            os.remove(filename)
        except Exception as e:
            await update.message.reply_text(f"❌ Error sending video: {str(e)}")
    else:
        await update.message.reply_text(
            "❌ Could not download video. Make sure the link is valid.\n\n"
            "Supported: YouTube, Instagram, TikTok, Twitter, Vimeo, and more."
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 **Available Commands:**\n\n"
        "/start - Show welcome message\n"
        "/age - Calculate your exact age\n"
        "/help - Show this help\n\n"
        "📹 **Video Downloader:**\n"
        "Just paste any video URL (YouTube, Instagram, TikTok, etc.)"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# --- Error Handler ---
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Error: {context.error}")

# --- Build the Bot ---
def run_bot():
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("age", age_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_age_input))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_video_url))
    application.add_error_handler(error_handler)
    
    # Run with polling (simpler for Render)
    print("🤖 Bot started! Using polling mode.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

# ========== MAIN ENTRY ==========
if __name__ == "__main__":
    import timedelta
    from datetime import timedelta
    
    # Start Flask in a separate thread
    port = int(os.environ.get("PORT", 5000))
    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    )
    flask_thread.daemon = True
    flask_thread.start()
    print(f"🌐 Flask server running on port {port}")
    
    # Run the bot (this blocks)
    run_bot()
