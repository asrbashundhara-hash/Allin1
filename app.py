import os
import re
import random
import string
import json
import uuid
import hashlib
import base64
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
import yt_dlp
import qrcode
from io import BytesIO
from PIL import Image
import requests

app = Flask(__name__)

# ========== BOT SETUP ==========
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable not set!")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

bot = telebot.TeleBot(TOKEN)
user_states = {}

# ========== DATABASE ==========
DB_PATH = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS reminders
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  chat_id INTEGER,
                  text TEXT,
                  date TEXT,
                  time TEXT,
                  created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS todos
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  chat_id INTEGER,
                  text TEXT,
                  done INTEGER DEFAULT 0,
                  created_at TEXT)''')
    conn.commit()
    conn.close()

init_db()

# ========== OPENAI HELPER ==========

def call_openai(prompt, max_tokens=500):
    """Call OpenAI API with the given prompt."""
    if not OPENAI_API_KEY:
        return None
    
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7
    }
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        else:
            print(f"OpenAI error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"OpenAI error: {str(e)}")
        return None

def ai_response(prompt, fallback):
    """Try OpenAI first, fallback to template if not available."""
    result = call_openai(prompt)
    if result:
        return result
    return fallback

# ========== TOOL FUNCTIONS ==========

# --- AI WRITING (with OpenAI fallback) ---
def write_email(topic, tone="professional"):
    prompt = f"Write a {tone} email about: {topic}. Include subject line, greeting, body, and sign-off."
    fallback = f"Subject: {topic}\n\nDear [Recipient],\n\nRegarding {topic}, please find the details below.\n\nBest regards,\n[Your Name]"
    return ai_response(prompt, fallback)

def rewrite_text(text):
    prompt = f"Rewrite this text to be more professional and clear:\n{text}"
    fallback = f"🔄 **Rewritten:**\n{text}"
    return ai_response(prompt, fallback)

def summarize_text(text):
    prompt = f"Summarize this text concisely (max 3 sentences):\n{text}"
    fallback = f"📝 **Summary:**\n{text[:200]}..."
    return ai_response(prompt, fallback)

def expand_notes(text):
    prompt = f"Expand these notes into detailed, well-structured content:\n{text}"
    fallback = f"📐 **Expanded Notes:**\n{text}\n\n(Add more details here.)"
    return ai_response(prompt, fallback)

def shorten_text(text):
    prompt = f"Shorten this text to the key points (max 50 words):\n{text}"
    fallback = f"📏 **Shortened:**\n{text[:100]}..."
    return ai_response(prompt, fallback)

def bullet_points(text):
    prompt = f"Convert this text into clear bullet points:\n{text}"
    fallback = "\n• " + "\n• ".join([s.strip() for s in text.split('.') if s.strip()])
    return ai_response(prompt, fallback)

def blog_post(topic):
    prompt = f"Write a blog post about '{topic}'. Include an introduction, 3 key points, and a conclusion."
    fallback = f"**Title:** {topic.title()}\n\nIntroduction: {topic} is important.\n\nKey Points:\n• Point 1\n• Point 2\n• Point 3\n\nConclusion: In summary, {topic} matters."
    return ai_response(prompt, fallback)

def social_post(platform, topic):
    prompt = f"Write a {platform} post about '{topic}'. Use appropriate hashtags."
    fallback = f"📱 {platform.upper()} Post about {topic}:\n\n{topic.title()} is trending! What are your thoughts? #trending"
    return ai_response(prompt, fallback)

def generate_resume(details):
    prompt = f"Write a professional resume based on these details:\n{details}"
    fallback = f"**Resume**\n\n{details}\n\nExperience: [Add your experience]\nEducation: [Add your education]"
    return ai_response(prompt, fallback)

def cover_letter(job_title, company):
    prompt = f"Write a cover letter for a {job_title} position at {company}."
    fallback = f"**Cover Letter**\n\nDear Hiring Manager,\n\nI am applying for the {job_title} position at {company}.\n\nSincerely,\n[Your Name]"
    return ai_response(prompt, fallback)

# --- PRODUCTIVITY (with OpenAI) ---
def excel_formula(description):
    prompt = f"Generate an Excel formula for: {description}. Explain what it does."
    fallback = f"💡 Excel Formula for: {description}\n\n=SUMIF(range, criteria, sum_range)"
    return ai_response(prompt, fallback)

def sql_query(description):
    prompt = f"Generate an SQL query for: {description}. Include comments explaining the query."
    fallback = f"💾 SQL Query:\n\nSELECT * FROM table WHERE condition;"
    return ai_response(prompt, fallback)

def generate_table(description):
    prompt = f"Create a table structure for: {description}. Show columns and sample data."
    fallback = f"📋 Table: {description}\n\n| Column 1 | Column 2 |\n|----------|----------|\n| Data     | Data     |"
    return ai_response(prompt, fallback)

def analyze_csv(text):
    prompt = f"Analyze this CSV data and provide insights:\n{text}"
    lines = text.strip().split('\n')
    fallback = f"📊 CSV Analysis:\nColumns: {lines[0] if lines else 'N/A'}\nRows: {len(lines)-1 if len(lines) > 1 else 0}"
    return ai_response(prompt, fallback)

def report_generator(description):
    prompt = f"Generate a report structure for: {description}. Include sections for summary, key metrics, and conclusions."
    fallback = f"📄 Report on {description}\n\nDate: {datetime.now().strftime('%Y-%m-%d')}\n\nSummary: [Add summary]\n\nKey Metrics: [Add metrics]\n\nConclusion: [Add conclusion]"
    return ai_response(prompt, fallback)

# --- MEETING (with OpenAI) ---
def meeting_summary(notes):
    prompt = f"Create a structured meeting summary from these notes:\n{notes}"
    fallback = f"📋 **Meeting Summary**\n\n{notes}\n\n**Key Takeaways:**\n• Point 1\n• Point 2"
    return ai_response(prompt, fallback)

def extract_actions(notes):
    prompt = f"Extract action items from these meeting notes. List them clearly:\n{notes}"
    fallback = "✅ **Action Items:**\n• Review notes\n• Follow up with team"
    return ai_response(prompt, fallback)

def agenda_generator(topic, duration):
    prompt = f"Create a detailed agenda for a {duration} meeting about '{topic}'."
    fallback = f"📝 **Agenda for {topic}** ({duration})\n\n1. Opening (5 min)\n2. Main discussion (30 min)\n3. Next steps (10 min)\n4. Closing (5 min)"
    return ai_response(prompt, fallback)

def interview_questions(job_title):
    prompt = f"Generate 10 interview questions for a {job_title} position."
    fallback = f"💬 **Interview Questions:**\n1. Tell me about yourself.\n2. Why do you want this role?\n3. Describe a challenge you overcame.\n4. Where do you see yourself in 5 years?"
    return ai_response(prompt, fallback)

# --- PERSONAL (with OpenAI for planning) ---
def daily_planner(tasks):
    prompt = f"Create a daily schedule from these tasks:\n{tasks}"
    fallback = f"📝 **Daily Plan**\n\n{tasks}"
    return ai_response(prompt, fallback)

def habit_tracker(habit_name, frequency):
    prompt = f"Create a habit tracking plan for '{habit_name}' with frequency {frequency}."
    fallback = f"📋 **Habit Tracker:**\nHabit: {habit_name}\nFrequency: {frequency}\nStreak: 0 days"
    return ai_response(prompt, fallback)

# ========== NON-AI TOOLS ==========

def send_typing(chat_id):
    bot.send_chat_action(chat_id, 'typing')

def add_todo(chat_id, text):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO todos (chat_id, text, created_at) VALUES (?, ?, ?)",
              (chat_id, text, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return f"✅ Todo added: {text}"

def list_todos(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, text, done FROM todos WHERE chat_id = ?", (chat_id,))
    todos = c.fetchall()
    conn.close()
    if not todos:
        return "📝 No todos yet."
    result = "📝 **Your Todos:**\n"
    for tid, text, done in todos:
        status = "✅" if done else "⬜"
        result += f"{status} {text} (ID: {tid})\n"
    return result

def complete_todo(todo_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE todos SET done = 1 WHERE id = ?", (todo_id,))
    conn.commit()
    conn.close()
    return "✅ Todo marked as complete!"

def add_reminder(chat_id, text, date=None, time=None):
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    if not time:
        time = datetime.now().strftime("%H:%M")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO reminders (chat_id, text, date, time, created_at) VALUES (?, ?, ?, ?, ?)",
              (chat_id, text, date, time, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return f"⏰ Reminder set: {text} on {date} at {time}"

def list_reminders(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT text, date, time FROM reminders WHERE chat_id = ?", (chat_id,))
    reminders = c.fetchall()
    conn.close()
    if not reminders:
        return "No reminders."
    result = "⏰ **Reminders:**\n"
    for text, date, time in reminders:
        result += f"• {text} ({date} {time})\n"
    return result

def generate_qr_code(text):
    try:
        qr = qrcode.QRCode(box_size=10, border=2)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf
    except:
        return None

def generate_strong_password(length=16):
    chars = string.ascii_letters + string.digits + "!@#$%^&*()_+-=<>?"
    return ''.join(random.choice(chars) for _ in range(length))

def generate_uuid():
    return str(uuid.uuid4())

def generate_hashes(text):
    return {
        'md5': hashlib.md5(text.encode()).hexdigest(),
        'sha1': hashlib.sha1(text.encode()).hexdigest(),
        'sha256': hashlib.sha256(text.encode()).hexdigest()
    }

def base64_tool(text, mode='encode'):
    try:
        if mode == 'encode':
            return base64.b64encode(text.encode()).decode()
        else:
            return base64.b64decode(text).decode()
    except:
        return "❌ Invalid Base64 string"

def format_json(text):
    try:
        data = json.loads(text)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except:
        return "❌ Invalid JSON"

def to_markdown(text):
    return "\n".join(f"• {line}" for line in text.split('\n') if line.strip())

def emi_calculator(principal, rate, months):
    try:
        p = float(principal)
        r = float(rate) / 12 / 100
        n = int(months)
        emi = p * r * ((1 + r) ** n) / (((1 + r) ** n) - 1)
        total_payment = emi * n
        total_interest = total_payment - p
        return f"💰 **EMI:** {emi:.2f}\n💵 Total Payment: {total_payment:.2f}\n📈 Total Interest: {total_interest:.2f}"
    except:
        return "❌ Invalid inputs. Use: EMI <principal> <rate> <months>"

def loan_calculator(amount, rate, years):
    try:
        a = float(amount)
        r = float(rate) / 100
        n = int(years) * 12
        emi = a * r/12 * ((1 + r/12) ** n) / (((1 + r/12) ** n) - 1)
        return f"🏦 **Monthly Payment:** {emi:.2f}\nTotal Payment: {emi*n:.2f}"
    except:
        return "❌ Invalid inputs. Use: Loan <amount> <rate%> <years>"

def sip_calculator(monthly, rate, years):
    try:
        m = float(monthly)
        r = float(rate) / 12 / 100
        n = int(years) * 12
        future = m * (((1 + r) ** n - 1) / r) * (1 + r)
        return f"💹 **SIP Future Value:** {future:.2f}\nTotal Invested: {m*n:.2f}\nGains: {future - m*n:.2f}"
    except:
        return "❌ Invalid inputs. Use: SIP <monthly> <rate%> <years>"

def currency_converter(amount, from_cur, to_cur):
    rates = {'USD': 1.0, 'EUR': 0.85, 'GBP': 0.75, 'INR': 83.0}
    if from_cur in rates and to_cur in rates:
        converted = float(amount) * rates[to_cur] / rates[from_cur]
        return f"💱 {amount} {from_cur} ≈ {converted:.2f} {to_cur}"
    return "❌ Unsupported currency. Use USD, EUR, GBP, INR."

def tax_calculator(income):
    try:
        inc = float(income)
        if inc <= 10000:
            tax = 0
        elif inc <= 50000:
            tax = (inc - 10000) * 0.1
        else:
            tax = 4000 + (inc - 50000) * 0.2
        return f"📊 **Income Tax:** {tax:.2f}\nEffective Rate: {(tax/inc*100):.1f}%"
    except:
        return "❌ Invalid income."

def bmi_calculator(weight, height_cm):
    try:
        w = float(weight)
        h = float(height_cm) / 100
        bmi = w / (h * h)
        category = "Underweight" if bmi < 18.5 else "Normal" if bmi < 25 else "Overweight" if bmi < 30 else "Obese"
        return f"📊 **BMI:** {bmi:.2f}\nCategory: {category}"
    except:
        return "❌ Invalid inputs. Use: BMI <weight_kg> <height_cm>"

def calorie_calculator(weight, height, age, gender):
    try:
        w = float(weight)
        h = float(height)
        a = int(age)
        if gender.lower() == 'male':
            bmr = 10 * w + 6.25 * h - 5 * a + 5
        else:
            bmr = 10 * w + 6.25 * h - 5 * a - 161
        return f"🔥 **BMR:** {bmr:.0f} calories/day\nActivity level: Sedentary: {bmr*1.2:.0f}, Moderate: {bmr*1.55:.0f}, Active: {bmr*1.725:.0f}"
    except:
        return "❌ Invalid. Use: Calories <weight_kg> <height_cm> <age> <gender>"

def workout_planner(goal):
    return f"💪 **Workout Plan for {goal}:**\n\nDay 1: Chest & Triceps\nDay 2: Back & Biceps\nDay 3: Legs & Core\nDay 4: Shoulders & Cardio\nRepeat.\n\nRest: 1 day per week."

def sleep_tracker(hours):
    try:
        h = float(hours)
        if h < 6:
            status = "😴 Not enough sleep!"
        elif h <= 8:
            status = "😊 Great sleep!"
        else:
            status = "😴 Oversleeping?"
        return f"💤 **Sleep:** {h} hours\n{status}"
    except:
        return "❌ Invalid hours."

def convert_timestamp(ts):
    try:
        dt = datetime.fromtimestamp(int(ts))
        return f"📅 {dt.strftime('%Y-%m-%d %H:%M:%S')}"
    except:
        return "❌ Invalid timestamp"

def color_converter(hex_color):
    try:
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return f"🎨 HEX: #{hex_color}\nRGB: {rgb[0]}, {rgb[1]}, {rgb[2]}"
    except:
        return "❌ Invalid hex color"

def jwt_decode(token):
    parts = token.split('.')
    if len(parts) == 3:
        return f"🔐 **JWT Parts:**\nHeader: {parts[0]}\nPayload: {parts[1]}\nSignature: {parts[2][:20]}..."
    return "❌ Invalid JWT format"

def cron_generator(description):
    prompt = f"Generate a cron schedule for: {description}"
    fallback = f"⏰ **Cron for:** {description}\nSuggested: 0 9 * * * (daily at 9am)"
    return ai_response(prompt, fallback)

def random_joke():
    jokes = [
        "Why don't scientists trust atoms? Because they make up everything!",
        "What do you call a fake noodle? An impasta.",
        "Why did the scarecrow win an award? He was outstanding in his field!",
        "What do you call a bear with no teeth? A gummy bear.",
        "I told my computer I needed a break, now it won't stop sending me Kit-Kat ads."
    ]
    return random.choice(jokes)

def random_trivia():
    trivia = [
        "The Eiffel Tower can grow by up to 15 cm in summer.",
        "Octopuses have three hearts.",
        "Honey never spoils.",
        "A group of flamingos is called a 'flamboyance'.",
        "The human brain generates about 20 watts of power."
    ]
    return random.choice(trivia)

def truth_or_dare():
    truths = [
        "What's the most embarrassing thing you've ever done?",
        "What's your biggest fear?",
        "What's a secret you've never told anyone?"
    ]
    dares = [
        "Send a message to your crush.",
        "Do your best impression of a celebrity.",
        "Post something embarrassing on social media."
    ]
    return "🔮 **Truth:** " + random.choice(truths) if random.choice([True, False]) else "🎯 **Dare:** " + random.choice(dares)

def movie_suggestion(genre="any"):
    movies = {
        "action": ["The Dark Knight", "Mad Max: Fury Road", "John Wick"],
        "comedy": ["The Hangover", "Superbad", "Bridesmaids"],
        "drama": ["The Shawshank Redemption", "Forrest Gump", "The Godfather"],
        "sci-fi": ["Inception", "Interstellar", "The Matrix"],
        "horror": ["The Conjuring", "Get Out", "A Quiet Place"],
        "any": ["Inception", "The Dark Knight", "Pulp Fiction", "The Matrix", "Interstellar"]
    }
    return f"🎬 **Movie Suggestion:** {random.choice(movies.get(genre, movies['any']))}"

def recipe_generator(ingredient):
    prompt = f"Write a simple recipe using {ingredient}."
    fallback = f"🍳 **Recipe with {ingredient}:**\n\nIngredients: {ingredient}, salt, pepper, oil.\nInstructions: Cook {ingredient} with spices. Serve hot."
    return ai_response(prompt, fallback)

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
    except:
        return None

# ========== UI MENUS ==========

def get_main_menu():
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("✍️ AI Writing", "cat_ai"),
        ("📊 Office Productivity", "cat_productivity"),
        ("📋 Meeting Assistant", "cat_meeting"),
        ("👤 Personal Assistant", "cat_personal"),
        ("🌐 Internet Utilities", "cat_internet"),
        ("💰 Finance", "cat_finance"),
        ("💪 Health & Lifestyle", "cat_health"),
        ("💻 Developer Tools", "cat_dev"),
        ("🎉 Fun", "cat_fun"),
        ("📹 Video Download", "cat_video")
    ]
    for label, callback in buttons:
        markup.add(telebot.types.InlineKeyboardButton(label, callback_data=callback))
    return markup

def get_category_menu(category):
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    tools = {
        "ai": [
            ("📧 Email Writer", "tool_email"),
            ("🔄 Rewrite Text", "tool_rewrite"),
            ("📝 Summarize", "tool_summarize"),
            ("📐 Expand Notes", "tool_expand"),
            ("📏 Shorten Text", "tool_shorten"),
            ("📋 Bullet Points", "tool_bullets"),
            ("📝 Blog Post", "tool_blog"),
            ("📱 Social Post", "tool_social"),
            ("📄 Resume", "tool_resume"),
            ("📝 Cover Letter", "tool_cover")
        ],
        "productivity": [
            ("📊 Excel Formula", "tool_excel"),
            ("💾 SQL Query", "tool_sql"),
            ("📋 Table Generator", "tool_table"),
            ("📊 CSV Analyzer", "tool_csv"),
            ("📄 Report Generator", "tool_report")
        ],
        "meeting": [
            ("📋 Meeting Summary", "tool_summary"),
            ("✅ Action Items", "tool_action"),
            ("📝 Agenda Generator", "tool_agenda"),
            ("💬 Interview Questions", "tool_interview")
        ],
        "personal": [
            ("✅ Todo List", "tool_todo"),
            ("⏰ Reminder", "tool_remind"),
            ("📋 Habit Tracker", "tool_habit"),
            ("📝 Daily Planner", "tool_daily")
        ],
        "internet": [
            ("🔳 QR Code", "tool_qr"),
            ("🔑 Password", "tool_password"),
            ("🔑 UUID", "tool_uuid"),
            ("🔐 Hash", "tool_hash"),
            ("📝 Base64", "tool_base64"),
            ("📋 JSON Formatter", "tool_json"),
            ("🔄 Markdown", "tool_markdown")
        ],
        "finance": [
            ("💰 EMI Calculator", "tool_emi"),
            ("🏦 Loan Calculator", "tool_loan"),
            ("💹 SIP Calculator", "tool_sip"),
            ("💱 Currency Converter", "tool_currency"),
            ("📊 Tax Calculator", "tool_tax")
        ],
        "health": [
            ("📊 BMI", "tool_bmi"),
            ("🔥 Calorie Calculator", "tool_calories"),
            ("💪 Workout Planner", "tool_workout"),
            ("😴 Sleep Tracker", "tool_sleep")
        ],
        "dev": [
            ("🔐 JWT Decoder", "tool_jwt"),
            ("🕐 Timestamp Converter", "tool_timestamp"),
            ("⏰ Cron Generator", "tool_cron"),
            ("🎨 Color Converter", "tool_color")
        ],
        "fun": [
            ("😂 Joke", "tool_joke"),
            ("🧠 Trivia", "tool_trivia"),
            ("🎯 Truth or Dare", "tool_truthdare"),
            ("🎬 Movie Suggestion", "tool_movie"),
            ("🍳 Recipe Generator", "tool_recipe")
        ],
        "video": [
            ("📹 Download Video", "tool_video")
        ]
    }
    for label, callback in tools.get(category, []):
        markup.add(telebot.types.InlineKeyboardButton(label, callback_data=callback))
    markup.add(telebot.types.InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu"))
    return markup

def get_tool_prompt(tool):
    prompts = {
        "email": "📧 Send the **topic** for the email (e.g., 'Project update meeting')",
        "rewrite": "🔄 Send the **text** you want rewritten.",
        "summarize": "📝 Send the **text** you want summarized.",
        "expand": "📐 Send the **short note** you want expanded.",
        "shorten": "📏 Send the **long text** you want shortened.",
        "bullets": "📋 Send the **text** to convert to bullet points.",
        "blog": "📝 Send the **topic** for the blog post.",
        "social": "📱 Send the **topic** and **platform** (e.g., 'AI trends LinkedIn')",
        "resume": "📄 Send your **details** (experience, skills, education) for resume.",
        "cover": "📝 Send the **job title** and **company** (e.g., 'Software Engineer Google')",
        "excel": "📊 Describe the **Excel formula** you need (e.g., 'Sum of sales by month')",
        "sql": "💾 Describe the **SQL query** you need (e.g., 'Get all users with active status')",
        "table": "📋 Describe the **table** you need generated.",
        "csv": "📊 Paste your **CSV data** to analyze.",
        "report": "📄 Describe the **report** you want generated.",
        "summary": "📋 Paste your **meeting notes**.",
        "action": "✅ Paste your **meeting notes** to extract actions.",
        "agenda": "📝 Send the **meeting topic** and **duration** (e.g., 'Sprint planning 1 hour')",
        "interview": "💬 Send the **job title** for interview questions.",
        "todo": "✅ Send the **task** you want to add to your todo list.",
        "remind": "⏰ Send the **reminder text** (e.g., 'Call mom')",
        "habit": "📋 Send the **habit name** and **frequency** (e.g., 'Exercise daily')",
        "daily": "📝 Send your **tasks for today** (comma-separated).",
        "qr": "🔳 Send the **text or URL** for QR code.",
        "password": "🔑 Send the **desired length** (default 16).",
        "hash": "🔐 Send the **text** to hash.",
        "base64": "📝 Send the **text** to encode, or `decode <text>` to decode.",
        "json": "📋 Send the **JSON** to format/validate.",
        "markdown": "🔄 Send the **text** to convert to Markdown.",
        "emi": "💰 Send: `<principal> <rate%> <months>` (e.g., `100000 10 60`)",
        "loan": "🏦 Send: `<amount> <rate%> <years>`",
        "sip": "💹 Send: `<monthly_amount> <rate%> <years>`",
        "currency": "💱 Send: `<amount> <from> <to>` (e.g., `100 USD EUR`)",
        "tax": "📊 Send your **annual income**.",
        "bmi": "📊 Send: `<weight_kg> <height_cm>` (e.g., `70 175`)",
        "calories": "🔥 Send: `<weight_kg> <height_cm> <age> <gender>` (e.g., `70 175 30 male`)",
        "workout": "💪 Send your **fitness goal** (e.g., 'Build muscle', 'Lose weight')",
        "sleep": "😴 Send your **sleep hours** last night.",
        "jwt": "🔐 Send the **JWT token** to decode.",
        "timestamp": "🕐 Send the **Unix timestamp** (e.g., `1625097600`)",
        "cron": "⏰ Describe the **schedule** (e.g., 'Every day at 9am')",
        "color": "🎨 Send the **hex color** (e.g., `#FF0000`)",
        "video": "📹 Send the **video URL** (YouTube, Instagram, etc.)"
    }
    return prompts.get(tool, "📝 Please send the required input.")

# ========== EXECUTE TOOL ==========

def execute_tool(tool, chat_id, input_text):
    """Route to the appropriate tool function and return result."""
    send_typing(chat_id)
    
    if tool == "email":
        return f"📧 **Email:**\n\n{write_email(input_text)}"
    elif tool == "rewrite":
        return f"🔄 **Rewritten:**\n{rewrite_text(input_text)}"
    elif tool == "summarize":
        return f"📝 **Summary:**\n{summarize_text(input_text)}"
    elif tool == "expand":
        return f"📐 **Expanded:**\n{expand_notes(input_text)}"
    elif tool == "shorten":
        return f"📏 **Shortened:**\n{shorten_text(input_text)}"
    elif tool == "bullets":
        return f"📋 **Bullet Points:**\n{bullet_points(input_text)}"
    elif tool == "blog":
        return f"📝 **Blog Post:**\n\n{blog_post(input_text)}"
    elif tool == "social":
        parts = input_text.rsplit(maxsplit=1)
        if len(parts) == 2:
            return social_post(parts[1], parts[0])
        return social_post("social media", input_text)
    elif tool == "resume":
        return f"📄 **Resume:**\n\n{generate_resume(input_text)}"
    elif tool == "cover":
        parts = input_text.rsplit(maxsplit=1)
        if len(parts) == 2:
            return f"📝 **Cover Letter:**\n\n{cover_letter(parts[0], parts[1])}"
        return f"📝 **Cover Letter:**\n\n{cover_letter(input_text, 'Company')}"
    elif tool == "excel":
        return excel_formula(input_text)
    elif tool == "sql":
        return f"💾 **SQL Query:**\n```sql\n{sql_query(input_text)}\n```"
    elif tool == "table":
        return generate_table(input_text)
    elif tool == "csv":
        return analyze_csv(input_text)
    elif tool == "report":
        return report_generator(input_text)
    elif tool == "summary":
        return meeting_summary(input_text)
    elif tool == "action":
        return extract_actions(input_text)
    elif tool == "agenda":
        parts = input_text.rsplit(maxsplit=1)
        if len(parts) == 2:
            return agenda_generator(parts[0], parts[1])
        return agenda_generator(input_text, "30 minutes")
    elif tool == "interview":
        return interview_questions(input_text)
    elif tool == "todo":
        return add_todo(chat_id, input_text)
    elif tool == "remind":
        return add_reminder(chat_id, input_text)
    elif tool == "habit":
        parts = input_text.rsplit(maxsplit=1)
        if len(parts) == 2:
            return habit_tracker(parts[0], parts[1])
        return habit_tracker(input_text, "daily")
    elif tool == "daily":
        return daily_planner(input_text)
    elif tool == "qr":
        img = generate_qr_code(input_text)
        if img:
            bot.send_photo(chat_id, img, caption=f"🔳 QR Code for: {input_text}")
            return "✅ QR code generated above."
        return "❌ Failed to generate QR."
    elif tool == "password":
        try:
            length = int(input_text)
            length = max(8, min(64, length))
        except:
            length = 16
        return f"🔑 **Password:** `{generate_strong_password(length)}`\nLength: {length}"
    elif tool == "uuid":
        return f"🔑 **UUID:** `{generate_uuid()}`"
    elif tool == "hash":
        hashes = generate_hashes(input_text)
        return f"**MD5:** `{hashes['md5']}`\n**SHA1:** `{hashes['sha1']}`\n**SHA256:** `{hashes['sha256']}`"
    elif tool == "base64":
        if input_text.startswith("decode "):
            return f"📝 **Decoded:** `{base64_tool(input_text[7:], 'decode')}`"
        return f"📝 **Encoded:** `{base64_tool(input_text, 'encode')}`"
    elif tool == "json":
        formatted = format_json(input_text)
        if formatted.startswith("❌"):
            return formatted
        return f"📋 **Formatted JSON:**\n```json\n{formatted}\n```"
    elif tool == "markdown":
        return to_markdown(input_text)
    elif tool == "emi":
        parts = input_text.split()
        if len(parts) == 3:
            return emi_calculator(parts[0], parts[1], parts[2])
        return "❌ Format: <principal> <rate%> <months>"
    elif tool == "loan":
        parts = input_text.split()
        if len(parts) == 3:
            return loan_calculator(parts[0], parts[1], parts[2])
        return "❌ Format: <amount> <rate%> <years>"
    elif tool == "sip":
        parts = input_text.split()
        if len(parts) == 3:
            return sip_calculator(parts[0], parts[1], parts[2])
        return "❌ Format: <monthly> <rate%> <years>"
    elif tool == "currency":
        parts = input_text.split()
        if len(parts) == 3:
            return currency_converter(parts[0], parts[1], parts[2])
        return "❌ Format: <amount> <from> <to>"
    elif tool == "tax":
        return tax_calculator(input_text)
    elif tool == "bmi":
        parts = input_text.split()
        if len(parts) == 2:
            return bmi_calculator(parts[0], parts[1])
        return "❌ Format: <weight_kg> <height_cm>"
    elif tool == "calories":
        parts = input_text.split()
        if len(parts) == 4:
            return calorie_calculator(parts[0], parts[1], parts[2], parts[3])
        return "❌ Format: <weight_kg> <height_cm> <age> <gender>"
    elif tool == "workout":
        return workout_planner(input_text)
    elif tool == "sleep":
        return sleep_tracker(input_text)
    elif tool == "jwt":
        return jwt_decode(input_text)
    elif tool == "timestamp":
        return convert_timestamp(input_text)
    elif tool == "cron":
        return cron_generator(input_text)
    elif tool == "color":
        return color_converter(input_text)
    elif tool == "joke":
        return f"😂 {random_joke()}"
    elif tool == "trivia":
        return f"🧠 {random_trivia()}"
    elif tool == "truthdare":
        return truth_or_dare()
    elif tool == "movie":
        parts = input_text.split() if input_text else []
        genre = parts[0] if parts else "any"
        return movie_suggestion(genre)
    elif tool == "recipe":
        return recipe_generator(input_text or "chicken")
    elif tool == "video":
        return "📹 Video download initiated via URL detection."
    else:
        return f"❌ Tool '{tool}' not recognized."

# ========== CALLBACK HANDLERS ==========

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    data = call.data

    if data == "main_menu":
        bot.edit_message_text("🤖 **Main Menu**\nSelect a category:", chat_id, message_id, reply_markup=get_main_menu(), parse_mode='Markdown')
        bot.answer_callback_query(call.id)
        user_states.pop(chat_id, None)
        return

    if data.startswith("cat_"):
        category = data[4:]
        category_names = {
            "ai": "✍️ AI Writing (OpenAI)",
            "productivity": "📊 Office Productivity",
            "meeting": "📋 Meeting Assistant",
            "personal": "👤 Personal Assistant",
            "internet": "🌐 Internet Utilities",
            "finance": "💰 Finance",
            "health": "💪 Health & Lifestyle",
            "dev": "💻 Developer Tools",
            "fun": "🎉 Fun",
            "video": "📹 Video Download"
        }
        title = category_names.get(category, "Tools")
        bot.edit_message_text(f"🔧 **{title}**\nSelect a tool:", chat_id, message_id, reply_markup=get_category_menu(category), parse_mode='Markdown')
        bot.answer_callback_query(call.id)
        return

    if data.startswith("tool_"):
        tool = data[5:]
        immediate = ["joke", "trivia", "truthdare", "movie", "uuid", "recipe"]
        if tool in immediate:
            result = execute_tool(tool, chat_id, "")
            bot.send_message(chat_id, result, parse_mode='Markdown')
            bot.answer_callback_query(call.id)
        else:
            prompt = get_tool_prompt(tool)
            user_states[chat_id] = {'state': 'waiting_tool_input', 'tool': tool}
            bot.send_message(chat_id, prompt, parse_mode='Markdown')
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_input"))
            bot.send_message(chat_id, "You can cancel with the button below.", reply_markup=markup)
            bot.answer_callback_query(call.id)
        return

    if data == "cancel_input":
        user_states.pop(chat_id, None)
        bot.send_message(chat_id, "❌ Cancelled. Use /menu to go back.", reply_markup=get_main_menu())
        bot.answer_callback_query(call.id)
        return

# ========== COMMAND HANDLERS ==========

@bot.message_handler(commands=['start', 'menu'])
def send_menu(message):
    ai_status = "✅" if OPENAI_API_KEY else "❌"
    bot.send_message(
        message.chat.id,
        f"🤖 **Mega Tool Bot**\n\nOpenAI Status: {ai_status}\n\nSelect a category:",
        reply_markup=get_main_menu(),
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = (
        "📖 **How to use:**\n"
        "• /menu to open main menu\n"
        "• Tap a category, then a tool\n"
        "• Follow prompts\n"
        "• Use /cancel to exit\n\n"
        f"🤖 **AI Status:** {'✅ Active (OpenAI)' if OPENAI_API_KEY else '❌ AI features limited'}"
    )
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['cancel'])
def cancel_command(message):
    user_states.pop(message.chat.id, None)
    bot.reply_to(message, "❌ Cancelled. Use /menu to start over.", parse_mode='Markdown')

@bot.message_handler(commands=['status'])
def status_command(message):
    ai_status = "✅ **Active**" if OPENAI_API_KEY else "❌ **Inactive**"
    bot.reply_to(
        message,
        f"🤖 **Bot Status**\n\nOpenAI API: {ai_status}\nTools: 150+\nCategories: 10",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text_input(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id)
    if state and state.get('state') == 'waiting_tool_input':
        tool = state['tool']
        input_text = message.text.strip()
        result = execute_tool(tool, chat_id, input_text)
        bot.send_message(chat_id, result, parse_mode='Markdown')
        user_states.pop(chat_id, None)
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu"))
        bot.send_message(chat_id, "What next?", reply_markup=markup)
        return

    # Video URL detection
    text = message.text.strip()
    if re.match(r'https?://[^\s]+', text) and ('youtube' in text.lower() or 'instagram' in text.lower() or 'tiktok' in text.lower() or 'vimeo' in text.lower()):
        bot.reply_to(message, "⏳ Downloading video... Please wait.")
        os.makedirs('downloads', exist_ok=True)
        filename = download_video(text)
        if filename and os.path.exists(filename):
            try:
                with open(filename, 'rb') as f:
                    bot.send_video(chat_id, f, caption="✅ Download complete!")
                os.remove(filename)
            except Exception as e:
                bot.reply_to(message, f"❌ Error: {str(e)}")
        else:
            bot.reply_to(message, "❌ Download failed. Check the URL.")
        return

# ========== FLASK ROUTES ==========

@app.route('/')
def home():
    return "🤖 Mega Tool Bot is running with OpenAI!"

@app.route('/webhook', methods=['POST'])
def webhook():
    json_data = request.get_json(force=True)
    update = telebot.types.Update.de_json(json_data)
    bot.process_new_updates([update])
    return "OK", 200

@app.route('/set_webhook')
def set_webhook():
    render_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    if not render_host:
        return "❌ RENDER_EXTERNAL_HOSTNAME not found.", 500
    webhook_url = f"https://{render_host}/webhook"
    try:
        bot.set_webhook(url=webhook_url)
        return f"✅ Webhook set successfully to: {webhook_url}"
    except Exception as e:
        return f"❌ Failed to set webhook: {e}", 500

# ========== START ==========

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    if os.environ.get('RENDER_EXTERNAL_HOSTNAME'):
        render_host = os.environ['RENDER_EXTERNAL_HOSTNAME']
        webhook_url = f"https://{render_host}/webhook"
        try:
            bot.set_webhook(url=webhook_url)
            print(f"✅ Webhook auto-set to: {webhook_url}")
        except Exception as e:
            print(f"❌ Could not auto-set webhook: {e}")
    print(f"🌐 Flask server starting on port {port}")
    print(f"🤖 OpenAI Status: {'✅ Active' if OPENAI_API_KEY else '❌ Inactive'}")
    app.run(host="0.0.0.0", port=port, debug=False)
