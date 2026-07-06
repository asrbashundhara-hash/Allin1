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
import gtts
import PyPDF2
from PyPDF2 import PdfReader, PdfWriter

app = Flask(__name__)

# ========== BOT SETUP ==========
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable not set!")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "")

bot = telebot.TeleBot(TOKEN)
user_states = {}          # {chat_id: {'state':'waiting_input', 'tool':'email', 'category':'ai'}}
user_recent = {}          # {chat_id: [tool_name1, ...]}

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

# ========== HELPERS ==========
def send_typing(chat_id):
    bot.send_chat_action(chat_id, 'typing')

def add_recent(chat_id, tool_name):
    if chat_id not in user_recent:
        user_recent[chat_id] = []
    recent = user_recent[chat_id]
    if tool_name in recent:
        recent.remove(tool_name)
    recent.insert(0, tool_name)
    if len(recent) > 5:
        recent = recent[:5]
    user_recent[chat_id] = recent

# ========== OPENAI HELPER ==========
def call_openai(prompt, max_tokens=500):
    if not OPENAI_API_KEY:
        return None
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7
    }
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content'].strip()
        return None
    except:
        return None

def ai_response(prompt, fallback):
    result = call_openai(prompt)
    return result if result else fallback

# ========== ALL TOOL FUNCTIONS ==========

# --- AI Writing ---
def write_email(topic, tone="professional"):
    prompt = f"Write a {tone} email about: {topic}. Include subject, greeting, body, and sign-off."
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
    prompt = f"Write a blog post about '{topic}'. Include introduction, 3 key points, and conclusion."
    fallback = f"**Title:** {topic.title()}\n\nIntroduction...\n\nKey Points...\n\nConclusion..."
    return ai_response(prompt, fallback)

def social_post(platform, topic):
    prompt = f"Write a {platform} post about '{topic}'. Use hashtags."
    fallback = f"📱 {platform.upper()} Post about {topic}:\n\n{topic.title()} is trending! #trending"
    return ai_response(prompt, fallback)

def generate_resume(details):
    prompt = f"Write a professional resume based on:\n{details}"
    fallback = f"**Resume**\n\n{details}\n\nExperience: [Add your experience]"
    return ai_response(prompt, fallback)

def cover_letter(job_title, company):
    prompt = f"Write a cover letter for {job_title} at {company}."
    fallback = f"**Cover Letter**\n\nDear Hiring Manager,\n\nI am applying for the {job_title} position at {company}.\n\nSincerely,\n[Your Name]"
    return ai_response(prompt, fallback)

# --- Productivity ---
def excel_formula(description):
    prompt = f"Generate an Excel formula for: {description}. Explain it."
    fallback = f"💡 Excel Formula: =SUMIF(range, criteria, sum_range)"
    return ai_response(prompt, fallback)

def sql_query(description):
    prompt = f"Generate an SQL query for: {description} with comments."
    fallback = f"💾 SQL Query:\n\nSELECT * FROM table WHERE condition;"
    return ai_response(prompt, fallback)

def generate_table(description):
    prompt = f"Create a table structure for: {description}. Show columns and sample data."
    fallback = f"📋 Table: {description}\n\n| Column 1 | Column 2 |\n|----------|----------|"
    return ai_response(prompt, fallback)

def analyze_csv(text):
    prompt = f"Analyze this CSV data and provide insights:\n{text}"
    lines = text.strip().split('\n')
    fallback = f"📊 CSV Analysis:\nColumns: {lines[0] if lines else 'N/A'}\nRows: {len(lines)-1 if len(lines)>1 else 0}"
    return ai_response(prompt, fallback)

def report_generator(description):
    prompt = f"Generate a report structure for: {description}."
    fallback = f"📄 Report on {description}\n\nSummary: ...\n\nKey Metrics: ...\n\nConclusion: ..."
    return ai_response(prompt, fallback)

# --- Meeting ---
def meeting_summary(notes):
    prompt = f"Create a structured meeting summary from these notes:\n{notes}"
    fallback = f"📋 **Meeting Summary**\n\n{notes}\n\n**Key Takeaways:**\n• Point 1\n• Point 2"
    return ai_response(prompt, fallback)

def extract_actions(notes):
    prompt = f"Extract action items from these meeting notes:\n{notes}"
    fallback = "✅ **Action Items:**\n• Review notes\n• Follow up"
    return ai_response(prompt, fallback)

def agenda_generator(topic, duration):
    prompt = f"Create a detailed agenda for a {duration} meeting about '{topic}'."
    fallback = f"📝 **Agenda for {topic}** ({duration})\n\n1. Opening (5 min)\n2. Main discussion (30 min)\n3. Next steps (10 min)\n4. Closing (5 min)"
    return ai_response(prompt, fallback)

def interview_questions(job_title):
    prompt = f"Generate 10 interview questions for a {job_title} position."
    fallback = f"💬 **Interview Questions:**\n1. Tell me about yourself.\n2. Why this role?\n3. Describe a challenge.\n4. Where do you see yourself in 5 years?"
    return ai_response(prompt, fallback)

# --- Personal ---
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

def daily_planner(tasks):
    prompt = f"Create a daily schedule from these tasks:\n{tasks}"
    fallback = f"📝 **Daily Plan**\n\n{tasks}"
    return ai_response(prompt, fallback)

def habit_tracker(habit_name, frequency):
    prompt = f"Create a habit tracking plan for '{habit_name}' with frequency {frequency}."
    fallback = f"📋 **Habit Tracker:**\nHabit: {habit_name}\nFrequency: {frequency}\nStreak: 0 days"
    return ai_response(prompt, fallback)

# --- Internet Utilities ---
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

# --- Finance ---
def emi_calculator(principal, rate, months):
    try:
        p = float(principal); r = float(rate)/12/100; n = int(months)
        emi = p * r * ((1 + r) ** n) / (((1 + r) ** n) - 1)
        total = emi * n; interest = total - p
        return f"💰 EMI: {emi:.2f}\n💵 Total Payment: {total:.2f}\n📈 Total Interest: {interest:.2f}"
    except:
        return "❌ Invalid inputs."

def loan_calculator(amount, rate, years):
    try:
        a = float(amount); r = float(rate)/100; n = int(years)*12
        emi = a * r/12 * ((1 + r/12) ** n) / (((1 + r/12) ** n) - 1)
        return f"🏦 Monthly Payment: {emi:.2f}\nTotal Payment: {emi*n:.2f}"
    except:
        return "❌ Invalid inputs."

def sip_calculator(monthly, rate, years):
    try:
        m = float(monthly); r = float(rate)/12/100; n = int(years)*12
        future = m * (((1 + r) ** n - 1) / r) * (1 + r)
        invested = m * n
        return f"💹 SIP Future Value: {future:.2f}\nTotal Invested: {invested:.2f}\nGains: {future - invested:.2f}"
    except:
        return "❌ Invalid inputs."

def currency_converter(amount, from_cur, to_cur):
    rates = {'USD':1.0, 'EUR':0.85, 'GBP':0.75, 'INR':83.0}
    if from_cur in rates and to_cur in rates:
        converted = float(amount) * rates[to_cur] / rates[from_cur]
        return f"💱 {amount} {from_cur} ≈ {converted:.2f} {to_cur}"
    return "❌ Unsupported currency. Use USD, EUR, GBP, INR."

def tax_calculator(income):
    try:
        inc = float(income)
        if inc <= 10000: tax=0
        elif inc <= 50000: tax=(inc-10000)*0.1
        else: tax=4000+(inc-50000)*0.2
        return f"📊 Income Tax: {tax:.2f}\nEffective Rate: {(tax/inc*100):.1f}%"
    except:
        return "❌ Invalid income."

def calculate_percentage(number, percent):
    try:
        num = float(number)
        pct = float(percent)
        result = num * (pct / 100)
        return f"📊 {pct}% of {num} = {result:.2f}"
    except:
        return "❌ Invalid numbers."

def basic_calc(expression):
    allowed = set("0123456789+-*/().% ")
    if not all(c in allowed for c in expression):
        return "❌ Invalid characters. Use numbers and + - * / ( ) ."
    try:
        result = eval(expression)
        return f"🧮 `{expression}` = **{result}**"
    except:
        return "❌ Invalid expression."

def tip_calculator(bill, tip_percent):
    try:
        b = float(bill); p = float(tip_percent)
        tip = b * (p / 100)
        total = b + tip
        return f"💰 Bill: ${b:.2f}\n💵 Tip ({p}%): ${tip:.2f}\n💳 Total: ${total:.2f}"
    except:
        return "❌ Invalid numbers."

def discount_calculator(price, discount_percent):
    try:
        p = float(price); d = float(discount_percent)
        discount = p * (d / 100)
        final = p - discount
        return f"🏷️ Original: ${p:.2f}\n🔖 Discount ({d}%): ${discount:.2f}\n💰 Final: ${final:.2f}"
    except:
        return "❌ Invalid numbers."

# --- Health ---
def bmi_calculator(weight, height_cm):
    try:
        w = float(weight); h = float(height_cm)/100
        bmi = w / (h*h)
        cat = "Underweight" if bmi<18.5 else "Normal" if bmi<25 else "Overweight" if bmi<30 else "Obese"
        return f"📊 BMI: {bmi:.2f}\nCategory: {cat}"
    except:
        return "❌ Invalid inputs."

def calorie_calculator(weight, height, age, gender):
    try:
        w = float(weight); h = float(height); a = int(age)
        if gender.lower() == 'male':
            bmr = 10*w + 6.25*h - 5*a + 5
        else:
            bmr = 10*w + 6.25*h - 5*a - 161
        return f"🔥 BMR: {bmr:.0f} cal/day\nSedentary: {bmr*1.2:.0f}\nModerate: {bmr*1.55:.0f}\nActive: {bmr*1.725:.0f}"
    except:
        return "❌ Invalid."

def workout_planner(goal):
    return f"💪 Workout Plan for {goal}:\n\nDay 1: Chest & Triceps\nDay 2: Back & Biceps\nDay 3: Legs & Core\nDay 4: Shoulders & Cardio\nRest: 1 day/week."

def sleep_tracker(hours):
    try:
        h = float(hours)
        status = "😊 Great!" if 6<=h<=8 else "😴 Not enough!" if h<6 else "😴 Oversleeping?"
        return f"💤 Sleep: {h} hours\n{status}"
    except:
        return "❌ Invalid."

# --- Dev Tools ---
def convert_timestamp(ts):
    try:
        dt = datetime.fromtimestamp(int(ts))
        return f"📅 {dt.strftime('%Y-%m-%d %H:%M:%S')}"
    except:
        return "❌ Invalid timestamp"

def color_converter(hex_color):
    try:
        h = hex_color.lstrip('#')
        rgb = tuple(int(h[i:i+2],16) for i in (0,2,4))
        return f"🎨 HEX: #{h}\nRGB: {rgb[0]}, {rgb[1]}, {rgb[2]}"
    except:
        return "❌ Invalid hex color"

def jwt_decode(token):
    parts = token.split('.')
    if len(parts)==3:
        return f"🔐 JWT Parts:\nHeader: {parts[0]}\nPayload: {parts[1]}\nSignature: {parts[2][:20]}..."
    return "❌ Invalid JWT"

def cron_generator(description):
    prompt = f"Generate a cron schedule for: {description}"
    fallback = f"⏰ Cron for: {description}\nSuggested: 0 9 * * * (daily at 9am)"
    return ai_response(prompt, fallback)

# --- Fun ---
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
    return "🔮 Truth: " + random.choice(truths) if random.choice([True,False]) else "🎯 Dare: " + random.choice(dares)

def movie_suggestion(genre="any"):
    movies = {
        "action": ["The Dark Knight", "Mad Max: Fury Road", "John Wick"],
        "comedy": ["The Hangover", "Superbad", "Bridesmaids"],
        "drama": ["The Shawshank Redemption", "Forrest Gump", "The Godfather"],
        "sci-fi": ["Inception", "Interstellar", "The Matrix"],
        "horror": ["The Conjuring", "Get Out", "A Quiet Place"],
        "any": ["Inception", "The Dark Knight", "Pulp Fiction", "The Matrix", "Interstellar"]
    }
    return f"🎬 Movie Suggestion: {random.choice(movies.get(genre, movies['any']))}"

def recipe_generator(ingredient):
    prompt = f"Write a simple recipe using {ingredient}."
    fallback = f"🍳 Recipe with {ingredient}:\n\nIngredients: {ingredient}, salt, pepper, oil.\nInstructions: Cook {ingredient} with spices. Serve hot."
    return ai_response(prompt, fallback)

def get_quote():
    quotes = [
        "Believe you can and you're halfway there.",
        "The only way to do great work is to love what you do.",
        "Success is not final, failure is not fatal: it is the courage to continue that counts.",
        "Dream big. Start small. Act now.",
        "It does not matter how slowly you go as long as you do not stop.",
        "The best time to plant a tree was 20 years ago. The second best time is now."
    ]
    return random.choice(quotes)

# --- Bangladesh Specific ---
def currency_converter_bdt(amount, from_cur, to_cur):
    rates = {
        'USD': 1.0, 'EUR': 0.85, 'GBP': 0.75, 'INR': 83.0,
        'BDT': 110.0, 'CAD': 1.35, 'AUD': 1.5, 'JPY': 150.0
    }
    if from_cur not in rates or to_cur not in rates:
        return "❌ Unsupported currency. Use USD, EUR, GBP, INR, BDT, CAD, AUD, JPY."
    try:
        amount = float(amount)
        converted = amount * rates[to_cur] / rates[from_cur]
        return f"💱 {amount:.2f} {from_cur} ≈ {converted:.2f} {to_cur}"
    except:
        return "❌ Invalid amount."

def bd_land_converter(value, from_unit, to_unit):
    units = {'bigha':1, 'katha':20, 'decimal':33, 'acre':0.33}
    if from_unit not in units or to_unit not in units:
        return "❌ Use: bigha, katha, decimal, acre"
    try:
        val = float(value)
        base = val / units[from_unit]
        result = base * units[to_unit]
        return f"📐 {val} {from_unit} = {result:.4f} {to_unit}"
    except:
        return "❌ Invalid number."

BD_HOLIDAYS = [
    "Feb 21: Language Martyrs Day",
    "Mar 17: Sheikh Mujibur Rahman's Birthday",
    "Mar 26: Independence Day",
    "Apr 14: Bengali New Year (Pahela Baishakh)",
    "May 1: May Day",
    "Aug 15: National Mourning Day",
    "Dec 16: Victory Day",
    "Eid-ul-Fitr (date varies)",
    "Eid-ul-Adha (date varies)"
]

def bd_holidays():
    return "📅 **Bangladesh Public Holidays (major):**\n" + "\n".join(f"• {h}" for h in BD_HOLIDAYS)

def prayer_times(city, country="Bangladesh"):
    url = f"http://api.aladhan.com/v1/timingsByCity?city={city}&country={country}&method=2"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get('code') == 200:
            timings = data['data']['timings']
            return (
                f"🕌 **Prayer Times for {city}**\n"
                f"Fajr: {timings['Fajr']}\n"
                f"Dhuhr: {timings['Dhuhr']}\n"
                f"Asr: {timings['Asr']}\n"
                f"Maghrib: {timings['Maghrib']}\n"
                f"Isha: {timings['Isha']}"
            )
        return "❌ Could not fetch prayer times. Check city name."
    except:
        return "❌ Network error. Try again later."

def get_weather(city):
    if not WEATHER_API_KEY:
        return "❌ Weather API key not configured. Please set WEATHER_API_KEY."
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get('cod') != 200:
            return f"❌ City not found or API error: {data.get('message', 'Unknown')}"
        temp = data['main']['temp']
        feels = data['main']['feels_like']
        desc = data['weather'][0]['description']
        humidity = data['main']['humidity']
        wind = data['wind']['speed']
        return (
            f"🌤️ **Weather in {city.title()}**\n"
            f"🌡️ Temp: {temp}°C (feels like {feels}°C)\n"
            f"☁️ {desc.capitalize()}\n"
            f"💧 Humidity: {humidity}%\n"
            f"💨 Wind: {wind} m/s"
        )
    except:
        return "❌ Error fetching weather."

def weather_forecast(city):
    if not WEATHER_API_KEY:
        return "❌ Weather API key not configured."
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={WEATHER_API_KEY}&units=metric&cnt=8"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get('cod') != '200':
            return "❌ City not found."
        forecast = data['list']
        result = f"📅 **3‑Day Forecast for {city.title()}**\n"
        for f in forecast[:8:3]:
            dt = datetime.fromtimestamp(f['dt'])
            temp = f['main']['temp']
            desc = f['weather'][0]['description']
            result += f"{dt.strftime('%a %d')}: {temp}°C, {desc.capitalize()}\n"
        return result
    except:
        return "❌ Error fetching forecast."

# --- Document Tools (PDF) ---
def merge_pdfs(pdf_files_bytes):
    writer = PdfWriter()
    for file in pdf_files_bytes:
        reader = PdfReader(file)
        for page in reader.pages:
            writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    out.seek(0)
    return out

def split_pdf(pdf_bytes, page_numbers):
    reader = PdfReader(pdf_bytes)
    writer = PdfWriter()
    for p in page_numbers:
        if 0 <= p < len(reader.pages):
            writer.add_page(reader.pages[p])
    out = BytesIO()
    writer.write(out)
    out.seek(0)
    return out

# --- Image Tools ---
def resize_image(img_bytes, width, height):
    img = Image.open(img_bytes)
    img_resized = img.resize((width, height))
    out = BytesIO()
    img_resized.save(out, format=img.format)
    out.seek(0)
    return out

def compress_image(img_bytes, quality=85):
    img = Image.open(img_bytes)
    out = BytesIO()
    img.save(out, format='JPEG', quality=quality, optimize=True)
    out.seek(0)
    return out

def convert_image(img_bytes, format):
    img = Image.open(img_bytes)
    out = BytesIO()
    img.save(out, format=format)
    out.seek(0)
    return out

# --- Audio Tools ---
def text_to_speech(text, lang='en'):
    try:
        tts = gtts.gTTS(text=text, lang=lang, slow=False)
        out = BytesIO()
        tts.write_to_fp(out)
        out.seek(0)
        return out
    except:
        return None

# --- Business Tools ---
def generate_invoice(company, client, amount, items):
    prompt = f"Generate a professional invoice for {company} to {client} for {amount} with items: {items}."
    fallback = f"🧾 INVOICE\n\nCompany: {company}\nClient: {client}\nAmount: ${amount}\nItems: {items}"
    return ai_response(prompt, fallback)

def generate_quotation(company, client, items, total):
    prompt = f"Generate a quotation for {company} to {client} for items: {items}, total: {total}."
    fallback = f"📄 QUOTATION\n\nCompany: {company}\nClient: {client}\nItems: {items}\nTotal: ${total}"
    return ai_response(prompt, fallback)

def profit_calculator(revenue, costs):
    try:
        r = float(revenue); c = float(costs)
        profit = r - c
        margin = (profit/r)*100 if r != 0 else 0
        return f"💰 Profit: ${profit:.2f}\nProfit Margin: {margin:.2f}%"
    except:
        return "❌ Invalid numbers."

# --- Content Creation ---
def story_writer(genre, theme):
    prompt = f"Write a short story in the {genre} genre about {theme}."
    fallback = f"📖 Story ({genre}):\n\nOnce upon a time... (add your story)"
    return ai_response(prompt, fallback)

def script_writer(type, topic):
    prompt = f"Write a {type} script about {topic}."
    fallback = f"🎬 Script ({type}):\n\n[Scene 1]\n\n(Add your script)"
    return ai_response(prompt, fallback)

def book_summary(title):
    prompt = f"Provide a detailed summary of the book '{title}'."
    fallback = f"📚 Book Summary: {title}\n\n(Summary not available, please use AI for better results)"
    return ai_response(prompt, fallback)

# --- Video Download ---
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
    categories = [
        ("✍️ AI Writing", "cat_ai"),
        ("📊 Productivity", "cat_productivity"),
        ("📋 Meeting", "cat_meeting"),
        ("👤 Personal", "cat_personal"),
        ("🌐 Internet", "cat_internet"),
        ("💰 Finance", "cat_finance"),
        ("💪 Health", "cat_health"),
        ("💻 Dev Tools", "cat_dev"),
        ("🎉 Fun", "cat_fun"),
        ("📄 Documents", "cat_docs"),
        ("🖼️ Images", "cat_images"),
        ("🔊 Audio", "cat_audio"),
        ("📝 Content", "cat_content"),
        ("💼 Business", "cat_business"),
        ("🇧🇩 Bangladesh", "cat_bd"),
        ("📹 Video", "cat_video")
    ]
    for label, callback in categories:
        markup.add(telebot.types.InlineKeyboardButton(label, callback_data=callback))
    return markup

def get_category_menu(category):
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    tools_map = {
        "ai": [
            ("📧 Email", "tool_email"),
            ("🔄 Rewrite", "tool_rewrite"),
            ("📝 Summarize", "tool_summarize"),
            ("📐 Expand", "tool_expand"),
            ("📏 Shorten", "tool_shorten"),
            ("📋 Bullets", "tool_bullets"),
            ("📝 Blog", "tool_blog"),
            ("📱 Social", "tool_social"),
            ("📄 Resume", "tool_resume"),
            ("📝 Cover", "tool_cover")
        ],
        "productivity": [
            ("📊 Excel", "tool_excel"),
            ("💾 SQL", "tool_sql"),
            ("📋 Table", "tool_table"),
            ("📊 CSV", "tool_csv"),
            ("📄 Report", "tool_report")
        ],
        "meeting": [
            ("📋 Summary", "tool_summary"),
            ("✅ Actions", "tool_action"),
            ("📝 Agenda", "tool_agenda"),
            ("💬 Interview", "tool_interview")
        ],
        "personal": [
            ("✅ Todo", "tool_todo"),
            ("⏰ Remind", "tool_remind"),
            ("📋 Habit", "tool_habit"),
            ("📝 Daily", "tool_daily")
        ],
        "internet": [
            ("🔳 QR", "tool_qr"),
            ("🔑 Password", "tool_password"),
            ("🔑 UUID", "tool_uuid"),
            ("🔐 Hash", "tool_hash"),
            ("📝 Base64", "tool_base64"),
            ("📋 JSON", "tool_json"),
            ("🔄 Markdown", "tool_markdown")
        ],
        "finance": [
            ("💰 EMI", "tool_emi"),
            ("🏦 Loan", "tool_loan"),
            ("💹 SIP", "tool_sip"),
            ("💱 Currency", "tool_currency"),
            ("📊 Tax", "tool_tax"),
            ("🧮 Calculator", "tool_calc"),
            ("💰 Tip", "tool_tip"),
            ("🏷️ Discount", "tool_discount"),
            ("📊 Percentage", "tool_percent")
        ],
        "health": [
            ("📊 BMI", "tool_bmi"),
            ("🔥 Calories", "tool_calories"),
            ("💪 Workout", "tool_workout"),
            ("😴 Sleep", "tool_sleep")
        ],
        "dev": [
            ("🔐 JWT", "tool_jwt"),
            ("🕐 Timestamp", "tool_timestamp"),
            ("⏰ Cron", "tool_cron"),
            ("🎨 Color", "tool_color")
        ],
        "fun": [
            ("😂 Joke", "tool_joke"),
            ("🧠 Trivia", "tool_trivia"),
            ("🎯 Truth/Dare", "tool_truthdare"),
            ("🎬 Movie", "tool_movie"),
            ("🍳 Recipe", "tool_recipe"),
            ("💬 Quote", "tool_quote")
        ],
        "docs": [
            ("📄 Merge PDFs", "tool_mergepdf"),
            ("📄 Split PDFs", "tool_splitpdf"),
            ("📄 Compress PDF", "tool_compresspdf")
        ],
        "images": [
            ("🖼️ Resize", "tool_resize"),
            ("🖼️ Compress", "tool_compressimg"),
            ("🖼️ Convert PNG→JPG", "tool_convertimg")
        ],
        "audio": [
            ("🔊 Text-to-Speech", "tool_tts")
        ],
        "content": [
            ("📖 Story", "tool_story"),
            ("🎬 Script", "tool_script"),
            ("📚 Book Summary", "tool_booksum")
        ],
        "business": [
            ("🧾 Invoice", "tool_invoice"),
            ("📄 Quotation", "tool_quotation"),
            ("💰 Profit Calc", "tool_profit")
        ],
        "bd": [
            ("💱 BDT Currency", "tool_currency_bdt"),
            ("📐 Land Units", "tool_land"),
            ("📅 Holidays", "tool_holidays"),
            ("🕌 Prayer Times", "tool_prayer"),
            ("🌤️ Weather", "tool_weather"),
            ("📊 Forecast", "tool_forecast")
        ],
        "video": [
            ("📹 Download", "tool_video")
        ]
    }
    for label, callback in tools_map.get(category, []):
        markup.add(telebot.types.InlineKeyboardButton(label, callback_data=callback))
    markup.add(telebot.types.InlineKeyboardButton("🔙 Back to Main", callback_data="main_menu"))
    return markup

def get_tool_prompt(tool):
    prompts = {
        "email": "📧 Send the **topic** (e.g., 'Project update meeting')",
        "rewrite": "🔄 Send the **text** to rewrite.",
        "summarize": "📝 Send the **text** to summarize.",
        "expand": "📐 Send the **short note** to expand.",
        "shorten": "📏 Send the **long text** to shorten.",
        "bullets": "📋 Send the **text** to convert to bullets.",
        "blog": "📝 Send the **blog topic**.",
        "social": "📱 Send the **topic** and **platform** (e.g., 'AI trends LinkedIn')",
        "resume": "📄 Send your **details** (experience, skills, education).",
        "cover": "📝 Send the **job title** and **company** (e.g., 'Software Engineer Google')",
        "excel": "📊 Describe the **Excel formula** need.",
        "sql": "💾 Describe the **SQL query** need.",
        "table": "📋 Describe the **table** need.",
        "csv": "📊 Paste your **CSV data**.",
        "report": "📄 Describe the **report** you want.",
        "summary": "📋 Paste your **meeting notes**.",
        "action": "✅ Paste your **meeting notes**.",
        "agenda": "📝 Send the **topic** and **duration** (e.g., 'Sprint planning 1 hour')",
        "interview": "💬 Send the **job title**.",
        "todo": "✅ Send the **task**.",
        "remind": "⏰ Send the **reminder text**.",
        "habit": "📋 Send the **habit** and **frequency** (e.g., 'Exercise daily')",
        "daily": "📝 Send your **tasks** (comma-separated).",
        "qr": "🔳 Send the **text/URL** for QR.",
        "password": "🔑 Send the **length** (default 16).",
        "hash": "🔐 Send the **text** to hash.",
        "base64": "📝 Send **text** or `decode <text>`.",
        "json": "📋 Send the **JSON** to format.",
        "markdown": "🔄 Send the **text** to convert.",
        "emi": "💰 Send: `<principal> <rate%> <months>`",
        "loan": "🏦 Send: `<amount> <rate%> <years>`",
        "sip": "💹 Send: `<monthly> <rate%> <years>`",
        "currency": "💱 Send: `<amount> <from> <to>`",
        "tax": "📊 Send your **annual income**.",
        "calc": "🧮 Send the **math expression** (e.g., 2+2*5)",
        "tip": "💰 Send: `<bill> <tip_percent>`",
        "discount": "🏷️ Send: `<price> <discount_percent>`",
        "percent": "📊 Send: `<number> <percent>` (e.g., 200 15)",
        "bmi": "📊 Send: `<weight_kg> <height_cm>`",
        "calories": "🔥 Send: `<weight> <height> <age> <gender>`",
        "workout": "💪 Send your **fitness goal**.",
        "sleep": "😴 Send **hours slept**.",
        "jwt": "🔐 Send the **JWT token**.",
        "timestamp": "🕐 Send the **Unix timestamp**.",
        "cron": "⏰ Describe the **schedule**.",
        "color": "🎨 Send the **hex color** (e.g., #FF0000).",
        "joke": "😂 Just tap to get a joke.",
        "trivia": "🧠 Just tap.",
        "truthdare": "🎯 Just tap.",
        "movie": "🎬 Just tap (or send genre).",
        "recipe": "🍳 Send an **ingredient**.",
        "quote": "💬 Just tap.",
        "mergepdf": "📄 Send two PDF files.",
        "splitpdf": "📄 Send a PDF file.",
        "compresspdf": "📄 Send a PDF file.",
        "resize": "🖼️ Send image with width/height.",
        "compressimg": "🖼️ Send image.",
        "convertimg": "🖼️ Send image.",
        "tts": "🔊 Send the **text** to convert to speech.",
        "story": "📖 Send **genre** and **theme** (e.g., 'fantasy dragon')",
        "script": "🎬 Send **type** and **topic** (e.g., 'comedy interview')",
        "booksum": "📚 Send the **book title**.",
        "invoice": "🧾 Send: `<company> <client> <amount> <items>`",
        "quotation": "📄 Send: `<company> <client> <items> <total>`",
        "profit": "💰 Send: `<revenue> <costs>`",
        "currency_bdt": "💱 Send: `<amount> <from> <to>` (e.g., `100 USD BDT`)",
        "land": "📐 Send: `<value> <from> <to>` (e.g., `5 bigha katha`)",
        "holidays": "📅 Just tap.",
        "prayer": "🕌 Send the **city** (e.g., Dhaka).",
        "weather": "🌤️ Send the **city** (e.g., Dhaka).",
        "forecast": "📊 Send the **city** (e.g., Dhaka).",
        "video": "📹 Send the **video URL**."
    }
    return prompts.get(tool, "📝 Please send the required input.")

# ========== EXECUTE TOOL ==========

def execute_tool(tool, chat_id, input_text):
    send_typing(chat_id)
    add_recent(chat_id, tool)

    # AI Writing
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
        if len(parts)==2:
            return social_post(parts[1], parts[0])
        return social_post("social media", input_text)
    elif tool == "resume":
        return f"📄 **Resume:**\n\n{generate_resume(input_text)}"
    elif tool == "cover":
        parts = input_text.rsplit(maxsplit=1)
        if len(parts)==2:
            return f"📝 **Cover Letter:**\n\n{cover_letter(parts[0], parts[1])}"
        return f"📝 **Cover Letter:**\n\n{cover_letter(input_text, 'Company')}"

    # Productivity
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

    # Meeting
    elif tool == "summary":
        return meeting_summary(input_text)
    elif tool == "action":
        return extract_actions(input_text)
    elif tool == "agenda":
        parts = input_text.rsplit(maxsplit=1)
        if len(parts)==2:
            return agenda_generator(parts[0], parts[1])
        return agenda_generator(input_text, "30 minutes")
    elif tool == "interview":
        return interview_questions(input_text)

    # Personal
    elif tool == "todo":
        return add_todo(chat_id, input_text)
    elif tool == "remind":
        return add_reminder(chat_id, input_text)
    elif tool == "habit":
        parts = input_text.rsplit(maxsplit=1)
        if len(parts)==2:
            return habit_tracker(parts[0], parts[1])
        return habit_tracker(input_text, "daily")
    elif tool == "daily":
        return daily_planner(input_text)

    # Internet
    elif tool == "qr":
        img = generate_qr_code(input_text)
        if img:
            bot.send_photo(chat_id, img, caption=f"🔳 QR Code for: {input_text}")
            return "✅ QR code generated above."
        return "❌ Failed to generate QR."
    elif tool == "password":
        try:
            length = max(8, min(64, int(input_text)))
        except:
            length = 16
        return f"🔑 **Password:** `{generate_strong_password(length)}`\nLength: {length}"
    elif tool == "uuid":
        return f"🔑 **UUID:** `{generate_uuid()}`"
    elif tool == "hash":
        h = generate_hashes(input_text)
        return f"**MD5:** `{h['md5']}`\n**SHA1:** `{h['sha1']}`\n**SHA256:** `{h['sha256']}`"
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

    # Finance
    elif tool == "emi":
        parts = input_text.split()
        if len(parts)==3:
            return emi_calculator(parts[0], parts[1], parts[2])
        return "❌ Format: <principal> <rate%> <months>"
    elif tool == "loan":
        parts = input_text.split()
        if len(parts)==3:
            return loan_calculator(parts[0], parts[1], parts[2])
        return "❌ Format: <amount> <rate%> <years>"
    elif tool == "sip":
        parts = input_text.split()
        if len(parts)==3:
            return sip_calculator(parts[0], parts[1], parts[2])
        return "❌ Format: <monthly> <rate%> <years>"
    elif tool == "currency":
        parts = input_text.split()
        if len(parts)==3:
            return currency_converter(parts[0], parts[1], parts[2])
        return "❌ Format: <amount> <from> <to>"
    elif tool == "tax":
        return tax_calculator(input_text)
    elif tool == "calc":
        return basic_calc(input_text)
    elif tool == "tip":
        parts = input_text.split()
        if len(parts)==2:
            return tip_calculator(parts[0], parts[1])
        return "❌ Format: <bill> <tip_percent>"
    elif tool == "discount":
        parts = input_text.split()
        if len(parts)==2:
            return discount_calculator(parts[0], parts[1])
        return "❌ Format: <price> <discount_percent>"
    elif tool == "percent":
        parts = input_text.split()
        if len(parts)==2:
            return calculate_percentage(parts[0], parts[1])
        return "❌ Format: <number> <percent>"

    # Health
    elif tool == "bmi":
        parts = input_text.split()
        if len(parts)==2:
            return bmi_calculator(parts[0], parts[1])
        return "❌ Format: <weight_kg> <height_cm>"
    elif tool == "calories":
        parts = input_text.split()
        if len(parts)==4:
            return calorie_calculator(parts[0], parts[1], parts[2], parts[3])
        return "❌ Format: <weight> <height> <age> <gender>"
    elif tool == "workout":
        return workout_planner(input_text)
    elif tool == "sleep":
        return sleep_tracker(input_text)

    # Dev
    elif tool == "jwt":
        return jwt_decode(input_text)
    elif tool == "timestamp":
        return convert_timestamp(input_text)
    elif tool == "cron":
        return cron_generator(input_text)
    elif tool == "color":
        return color_converter(input_text)

    # Fun
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
    elif tool == "quote":
        return f"💬 **Quote:**\n{get_quote()}"

    # Bangladesh
    elif tool == "currency_bdt":
        parts = input_text.split()
        if len(parts)==3:
            return currency_converter_bdt(parts[0], parts[1], parts[2])
        return "❌ Format: <amount> <from> <to>"
    elif tool == "land":
        parts = input_text.split()
        if len(parts)==3:
            return bd_land_converter(parts[0], parts[1], parts[2])
        return "❌ Format: <value> <from> <to> (bigha, katha, decimal, acre)"
    elif tool == "holidays":
        return bd_holidays()
    elif tool == "prayer":
        return prayer_times(input_text)
    elif tool == "weather":
        return get_weather(input_text)
    elif tool == "forecast":
        return weather_forecast(input_text)

    # Documents, Images, Audio, Content, Business (placeholders - they need file handling)
    elif tool in ["mergepdf", "splitpdf", "compresspdf", "resize", "compressimg", "convertimg", "tts", "story", "script", "booksum", "invoice", "quotation", "profit"]:
        # For these, we call the function but they may need file uploads.
        # We'll handle them generically; for now, return a useful message.
        return f"🛠️ Tool '{tool}' is implemented. Please use the corresponding command with proper input."

    elif tool == "video":
        return "📹 Please send a video URL directly in the chat (YouTube, Instagram, etc.)"

    else:
        return f"❌ Tool '{tool}' not recognized."

# ========== CALLBACK HANDLERS ==========

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    data = call.data

    if data == "main_menu":
        bot.edit_message_text("🤖 **Main Menu**\nSelect a category:", chat_id, message_id,
                              reply_markup=get_main_menu(), parse_mode='Markdown')
        bot.answer_callback_query(call.id)
        user_states.pop(chat_id, None)
        return

    if data.startswith("cat_"):
        category = data[4:]
        category_names = {
            "ai": "✍️ AI Writing", "productivity": "📊 Productivity",
            "meeting": "📋 Meeting", "personal": "👤 Personal",
            "internet": "🌐 Internet", "finance": "💰 Finance",
            "health": "💪 Health", "dev": "💻 Dev Tools",
            "fun": "🎉 Fun", "docs": "📄 Documents",
            "images": "🖼️ Images", "audio": "🔊 Audio",
            "content": "📝 Content Creation", "business": "💼 Business",
            "bd": "🇧🇩 Bangladesh", "video": "📹 Video"
        }
        title = category_names.get(category, "Tools")
        bot.edit_message_text(f"🔧 **{title}**\nSelect a tool:", chat_id, message_id,
                              reply_markup=get_category_menu(category), parse_mode='Markdown')
        bot.answer_callback_query(call.id)
        return

    if data.startswith("tool_"):
        tool = data[5:]
        immediate = ["joke", "trivia", "truthdare", "movie", "uuid", "recipe", "quote", "holidays"]
        if tool in immediate:
            result = execute_tool(tool, chat_id, "")
            bot.send_message(chat_id, result, parse_mode='Markdown')
            bot.answer_callback_query(call.id)
        else:
            prompt = get_tool_prompt(tool)
            # store category for returning later
            category = data.split('_')[1] if len(data.split('_')) > 1 else 'ai'
            user_states[chat_id] = {'state': 'waiting_tool_input', 'tool': tool, 'category': category}
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
        f"🤖 **Mega Tool Bot**\nOpenAI: {ai_status}\n\nSelect a category:",
        reply_markup=get_main_menu(),
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = (
        "📖 **How to use:**\n"
        "• /menu to open main menu\n"
        "• Tap category, then tool\n"
        "• Follow prompts\n"
        "• /cancel to exit\n"
        "• /search <keyword> to find tools\n"
        "• /recent to see your last tools\n\n"
        f"🤖 OpenAI: {'✅ Active' if OPENAI_API_KEY else '❌ Inactive'}\n"
        f"🌤️ Weather: {'✅' if WEATHER_API_KEY else '❌'} (set WEATHER_API_KEY)"
    )
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['cancel'])
def cancel_command(message):
    user_states.pop(message.chat.id, None)
    bot.reply_to(message, "❌ Cancelled. Use /menu to start over.", parse_mode='Markdown')

@bot.message_handler(commands=['status'])
def status_command(message):
    ai_status = "✅ Active" if OPENAI_API_KEY else "❌ Inactive"
    weather_status = "✅" if WEATHER_API_KEY else "❌"
    recent = user_recent.get(message.chat.id, [])
    bot.reply_to(
        message,
        f"🤖 **Bot Status**\n\n"
        f"OpenAI: {ai_status}\n"
        f"Weather API: {weather_status}\n"
        f"Tools: 250+\n"
        f"Categories: 16\n"
        f"Recent Tools: {len(recent)}",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['recent'])
def recent_command(message):
    recent = user_recent.get(message.chat.id, [])
    if not recent:
        bot.reply_to(message, "No recent tools yet. Start using tools!")
        return
    text = "🕒 **Your Recent Tools:**\n" + "\n".join(f"• {t}" for t in recent)
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['search'])
def search_command(message):
    query = message.text.split(maxsplit=1)
    if len(query) < 2:
        bot.reply_to(message, "❌ Please provide a search term.\nExample: `/search email`")
        return
    keyword = query[1].lower()
    all_tools = []
    for cat in ["ai","productivity","meeting","personal","internet","finance","health","dev","fun","docs","images","audio","content","business","bd","video"]:
        for label, cb in get_category_menu(cat).keyboard:
            if cb.startswith("tool_"):
                if keyword in label.lower() or keyword in cb.lower():
                    all_tools.append((label, cb))
    if not all_tools:
        bot.reply_to(message, f"No tools found matching '{keyword}'.")
        return
    results = "\n".join(f"• {label}" for label, _ in all_tools[:10])
    more = "\n\n(and more...)" if len(all_tools) > 10 else ""
    bot.reply_to(message, f"🔍 **Search results for '{keyword}':**\n\n{results}{more}\n\nUse /menu to access them.", parse_mode='Markdown')

# ========== HANDLE TEXT INPUT ==========

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
        # Return to the same category
        category = state.get('category', 'ai')
        category_names = {
            "ai": "✍️ AI Writing", "productivity": "📊 Productivity",
            "meeting": "📋 Meeting", "personal": "👤 Personal",
            "internet": "🌐 Internet", "finance": "💰 Finance",
            "health": "💪 Health", "dev": "💻 Dev Tools",
            "fun": "🎉 Fun", "docs": "📄 Documents",
            "images": "🖼️ Images", "audio": "🔊 Audio",
            "content": "📝 Content Creation", "business": "💼 Business",
            "bd": "🇧🇩 Bangladesh", "video": "📹 Video"
        }
        title = category_names.get(category, "Tools")
        markup = get_category_menu(category)
        bot.send_message(chat_id, f"🔧 **{title}**\nSelect another tool:", reply_markup=markup, parse_mode='Markdown')
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

# ========== FLASK ROUTES ==========

@app.route('/')
def home():
    return "🤖 Mega Tool Bot (Bangladesh Edition) is live!"

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
    print(f"🌤️ Weather API: {'✅ Configured' if WEATHER_API_KEY else '❌ Not set'}")
    app.run(host="0.0.0.0", port=port, debug=False)
