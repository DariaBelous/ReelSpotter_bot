# ReelSpotter Bot 📍

Telegram bot that identifies real-world locations from reel/tiktok screenshots using AI.

## Features

- Location detection from screenshots using AI Vision (OpenRouter)
- Multi-turn conversation: hints, follow-up photos from different angles, new place detection
- Intent recognition — bot understands free-form user replies, not just fixed commands
- Friendly reactions when the guess is confirmed
- Request history stored in SQLite
- FastAPI backend + Telegram bot frontend

## Project Structure

```
reelspotter-bot/
├── backend/
│   └── main.py          # FastAPI: /analyze, /refine, /celebrate, /intent, /chat, /history
├── bot/
│   └── bot.py          
├── .env               
├── .gitignore
├── requirements.txt
└── README.md
```

## Installation

```
pip install -r requirements.txt
```

## Run the Project

### 1. Add your keys to .env file

```
TELEGRAM_TOKEN=your_token
OPENROUTER_API_KEY=your_key
```

### 2. Run FastAPI backend

```
cd backend
uvicorn main:app --reload
```

### 3. Run Telegram bot

```
cd bot
python bot.py
```

## Tech Stack

- FastAPI
- aiogram 3
- OpenRouter AI (Vision)
- SQLite
