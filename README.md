# Multi-Tool Telegram Bot

A Telegram bot with Age Calculator + Video Downloader. Deployable on Render.com free tier.

## Features
- 📅 **Age Calculator** – Enter your birthdate, get exact age
- 📹 **Video Downloader** – Supports YouTube, Instagram, TikTok, Twitter, Vimeo, and more

## Deploy on Render.com

1. Fork this repository to GitHub
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your GitHub repo
4. Settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python app.py`
5. Add Environment Variable:
   - Key: `TELEGRAM_TOKEN`
   - Value: `your_bot_token_from_BotFather`
6. Click **Deploy**

## Local Testing
```bash
pip install -r requirements.txt
export TELEGRAM_TOKEN="your_token"
python app.py
