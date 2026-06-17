# ReelSpotter Bot 📍

Telegram bot that identifies real-world locations from reel/tiktok screenshots using AI.

## Features

- Location detection from screenshots using AI (OpenRouter)
- Hint system — user can help the bot narrow down the location
- Request history stored in SQLite
- FastAPI backend + Telegram bot frontend

## Project Structure

backend/

└── main.py
bot/

└── bot.py

## Installation
pip install -r requirements.txt

## Run the Project

### 1. Add your keys to .env file
TELEGRAM_TOKEN=your_token

OPENROUTER_API_KEY=your_key
### 2. Run FastAPI backend
cd backend

uvicorn main:app --reload

### 3. Run Telegram bot
cd bot

python bot.py

## Tech Stack

- FastAPI
- aiogram 3
- OpenRouter AI (Vision)
- SQLite
