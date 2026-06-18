from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os
import base64
import httpx
from dotenv import load_dotenv

from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def init_db():
    conn = sqlite3.connect("history.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.post("/analyze")
async def analyze(user_id: str, file: UploadFile = File(...)):
    image_bytes = await file.read()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openrouter/auto",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Look at this screenshot. Try to identify the real-world location shown. Always respond in Russian. Start with 'Возможно, это' или 'Это может быть'. Give 2-3 possible locations if unsure. Return the place name and city/country. If you cannot determine the location at all, say so honestly in Russian."},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                        ]
                    }
                ]
            }
        )
    resp_json = response.json()
    print("OpenRouter response:", resp_json)
    if "choices" not in resp_json:
        result = str(resp_json.get("error", "Не удалось определить место"))
    else:
        result = resp_json["choices"][0]["message"]["content"]
    conn = sqlite3.connect("history.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO requests (user_id, result) VALUES (?, ?)", (user_id, result))
    conn.commit()
    conn.close()
    return {"location": result}

@app.post("/refine")
async def refine(data: dict):
    user_id = data.get("user_id")
    hint = data.get("hint")
    previous = data.get("previous")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openrouter/auto",
                "messages": [
                    {
                        "role": "user",
                        "content": f"""Пользователь прислал фото места. Мой предыдущий ответ был: "{previous}". 
Пользователь написал: "{hint}".

Если пользователь называет конкретное место (улицу, район, достопримечательность) — просто подтверди это место, скажи что-то интересное о нём в 1-2 предложениях. Не пиши "с учётом подсказки" — просто отвечай как будто ты это знал.

Если пользователь даёт неполную подсказку (страна, город) — уточни конкретнее.

Отвечай на русском, коротко."""
                    }
                ]
            }
        )
    resp_json = response.json()
    result = resp_json["choices"][0]["message"]["content"] if "choices" in resp_json else "Не удалось уточнить"
    return {"location": result}

@app.post("/celebrate")
async def celebrate(data: dict):
    place = data.get("place", "это место")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openrouter/auto",
                "messages": [
                    {
                        "role": "user",
                        "content": f"Ты крутой бот который определяет места по фото. Пользователь подтвердил что ты угадал: {place}. Напиши короткую радостную реакцию на русском — максимум 2 предложения, без мата, без пафоса, можно использовать только эти эмодзи если хочешь: 🫰🏻 🪩 🍋‍🟩 🪼 🎐 🍜 🧚🏻 💅🏻 — максимум одно. В конце коротко спроси нужна ли ещё помощь."
                    }
                ]
            }
        )
    resp_json = response.json()
    result = resp_json["choices"][0]["message"]["content"] if "choices" in resp_json else "Ура! Я угадал! 🎉 Нужна ещё помощь?"
    return {"text": result}

@app.get("/history")
def get_history(user_id: str):
    conn = sqlite3.connect("history.db")
    cursor = conn.cursor()
    cursor.execute("SELECT result, created_at FROM requests WHERE user_id = ? ORDER BY created_at DESC LIMIT 10", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return {"history": [{"result": r[0], "created_at": r[1]} for r in rows]}

@app.post("/intent")
async def detect_intent(data: dict):
    text = data.get("text")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "openrouter/auto",
                "messages": [{
                    "role": "user",
                    "content": f"""Пользователь написал: "{text}"
Определи намерение. Ответь ТОЛЬКО одним словом из списка:
- POSITIVE (угадал, верно, да это оно, точно)
- NEGATIVE (нет, не то, ошибся, не угадал)
- NEW_PLACE (новое место, другое место, начнём заново)
- SAME_ANGLE (другой ракурс, ещё фото того же места, с другой стороны)
- PHOTO_OFFER (могу прислать фото, пришлю скрин, есть ещё фотка)
- HINT (подсказка, это в москве, это россия, это около арбата)
- OTHER"""
                }]
            }
        )
    resp_json = response.json()
    intent = resp_json["choices"][0]["message"]["content"].strip().upper()
    valid = {"POSITIVE", "NEGATIVE", "NEW_PLACE", "SAME_ANGLE", "PHOTO_OFFER", "HINT", "OTHER"}
    if intent not in valid:
        intent = "OTHER"
    return {"intent": intent}