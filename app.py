import os
import re
import asyncio
from datetime import datetime, timedelta  # ✅ Correct import - NO "import timedelta" line
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== FLASK APP ==========
app = Flask(__name__)

# ========== BOT SETUP ==========
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable not set!")

# Build the bot application
application = Application.builder().token(TOKEN).build()

# ========== TOOL FUNCTIONS ==========
def calculate_age(birth_date_str):
    try:
        birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d")
        today = datetime.now()
        years = today.year - birth_date.year
        months = today.month - birth_date.month
        days = today.day - birth_date.day
        
        if days < 0:
            months -= 1
            prev_month = today.replace(day=1) - timedelta(days=1)
            days += prev_month.day
        if months < 0:
            years -= 1
            months += 12
            
        return f"🎂 You are **{years}** years, **{months}** months, and **{days}** days old!"
    except ValueError:
        return None

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
        print(f"Download error: {e}")
        return None

# ========== COMMAND HANDLERS ==========
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
        context.user_data['waiting_for_age'] = False
    else:
        await update.message.reply_text(
            "❌ Invalid format! Please use:\n`YYYY-MM-DD`",
            parse_mode="Markdown"
        )

async def handle_video_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_age'):
        return
    url = update.message.text.strip()
    if not re.match(r'https?://[^\s]+', url):
        return
    
    await update.message.reply_text("⏳ Downloading video... Please wait.")
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
        await update.message.reply_text("❌ Could not download video. Make sure the link is valid.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 **Available Commands:**\n\n"
        "/start - Show welcome message\n"
        "/age - Calculate your exact age\n"
        "/help - Show this help\n\n"
        "📹 **Video Downloader:**\nJust paste any video URL."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Error: {context.error}")

# Register all handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("age", age_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_age_input))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_video_url))
application.add_error_handler(error_handler)

# ========== FLASK ROUTES ==========
@app.route('/')
def home():
    return "🤖 Bot is running! Webhook is ready."

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming Telegram messages via Webhook."""
    try:
        json_data = request.get_json(force=True)
        update = Update.de_json(json_data, application.bot)
        asyncio.run(application.process_update(update))
    except Exception as e:
        print(f"Webhook error: {e}")
    return "OK", 200

@app.route('/set_webhook')
def set_webhook():
    """Manually set the webhook URL."""
    render_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    if not render_host:
        return "❌ RENDER_EXTERNAL_HOSTNAME not found. Make sure you are on Render.", 500
    
    webhook_url = f"https://{render_host}/webhook"
    try:
        asyncio.run(application.bot.set_webhook(webhook_url))
        return f"✅ Webhook set successfully to: {webhook_url}"
    except Exception as e:
        return f"❌ Failed to set webhook: {e}", 500

# ========== START SERVER ==========
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    # Auto-set webhook on Render
    if os.environ.get('RENDER_EXTERNAL_HOSTNAME'):
        render_host = os.environ['RENDER_EXTERNAL_HOSTNAME']
        webhook_url = f"https://{render_host}/webhook"
        try:
            asyncio.run(application.bot.set_webhook(webhook_url))
            print(f"✅ Webhook auto-set to: {webhook_url}")
        except Exception as e:
            print(f"❌ Could not auto-set webhook: {e}")
    
    print(f"🌐 Flask server starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
