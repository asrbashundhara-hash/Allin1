import os
import re
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
import yt_dlp

app = Flask(__name__)

# ========== BOT SETUP ==========
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable not set!")

bot = telebot.TeleBot(TOKEN)

# Store user states (simple in-memory dict)
user_states = {}

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

def download_video(url):
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

# ========== BOT COMMAND HANDLERS ==========
@bot.message_handler(commands=['start'])
def start(message):
    welcome = (
        "🤖 **Welcome to Multi-Tool Bot!**\n\n"
        "Here's what I can do:\n"
        "• `/age` - Calculate your exact age\n"
        "• Send any video URL - Download videos\n\n"
        "Just send me a YouTube/Instagram/TikTok link!"
    )
    bot.reply_to(message, welcome, parse_mode="Markdown")

@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = (
        "📖 **Available Commands:**\n\n"
        "/start - Show welcome message\n"
        "/age - Calculate your exact age\n"
        "/help - Show this help\n\n"
        "📹 **Video Downloader:**\nJust paste any video URL."
    )
    bot.reply_to(message, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['age'])
def age_command(message):
    bot.reply_to(
        message,
        "📅 Please send your birthdate in this format:\n`YYYY-MM-DD`\n\nExample: `2000-01-15`",
        parse_mode="Markdown"
    )
    user_states[message.chat.id] = 'waiting_for_age'

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    text = message.text.strip()
    
    # Check if user is in age calculator mode
    if user_states.get(chat_id) == 'waiting_for_age':
        result = calculate_age(text)
        if result:
            bot.reply_to(message, result, parse_mode="Markdown")
            user_states[chat_id] = None
        else:
            bot.reply_to(
                message,
                "❌ Invalid format! Please use:\n`YYYY-MM-DD`",
                parse_mode="Markdown"
            )
        return
    
    # Check if it's a video URL
    if re.match(r'https?://[^\s]+', text):
        bot.reply_to(message, "⏳ Downloading video... Please wait.")
        os.makedirs('downloads', exist_ok=True)
        
        filename = download_video(text)
        if filename and os.path.exists(filename):
            try:
                with open(filename, 'rb') as f:
                    bot.send_video(chat_id, f, caption="✅ Download complete!")
                os.remove(filename)
            except Exception as e:
                bot.reply_to(message, f"❌ Error sending video: {str(e)}")
        else:
            bot.reply_to(message, "❌ Could not download video. Make sure the link is valid.")
    else:
        # Ignore other messages
        pass

# ========== FLASK ROUTES ==========
@app.route('/')
def home():
    return "🤖 Bot is running! Webhook is ready."

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    """Handle incoming Telegram updates."""
    json_data = request.get_json(force=True)
    update = telebot.types.Update.de_json(json_data)
    bot.process_new_updates([update])
    return "OK", 200

@app.route('/set_webhook')
def set_webhook():
    """Set the webhook URL."""
    render_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    if not render_host:
        return "❌ RENDER_EXTERNAL_HOSTNAME not found. Make sure you are on Render.", 500
    
    webhook_url = f"https://{render_host}/{TOKEN}"
    try:
        bot.set_webhook(url=webhook_url)
        return f"✅ Webhook set successfully to: {webhook_url}"
    except Exception as e:
        return f"❌ Failed to set webhook: {e}", 500

# ========== START SERVER ==========
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    # Auto-set webhook on Render
    if os.environ.get('RENDER_EXTERNAL_HOSTNAME'):
        render_host = os.environ['RENDER_EXTERNAL_HOSTNAME']
        webhook_url = f"https://{render_host}/{TOKEN}"
        try:
            bot.set_webhook(url=webhook_url)
            print(f"✅ Webhook auto-set to: {webhook_url}")
        except Exception as e:
            print(f"❌ Could not auto-set webhook: {e}")
    
    print(f"🌐 Flask server starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
