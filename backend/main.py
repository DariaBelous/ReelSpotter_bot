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

async def call_openrouter(messages, timeout=30):
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={"model": "openrouter/auto", "messages": messages}
        )
    resp_json = response.json()
    if "choices" not in resp_json:
        return None, resp_json.get("error", "Ошибка")
    return resp_json["choices"][0]["message"]["content"], None

@app.post("/analyze")
async def analyze(
    user_id: str,
    previous_guess: str | None = None,
    file: UploadFile = File(...)
):
    image_bytes = await file.read()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    if previous_guess:
        prompt = f"Ранее я предположил: {previous_guess}. Теперь смотрю на другой ракурс того же места. Уточни или подтверди местоположение. Отвечай на русском, начни с 'Возможно, это' или 'Это может быть'. Не ставь точку в конце последнего предложения."
    else:
        prompt = "Посмотри на это фото. Попробуй определить реальное место. Отвечай на русском. Начни с 'Возможно, это' или 'Это может быть'. Назови место, город, страну. Если не уверен — предложи 2-3 варианта. Если совсем не можешь определить — скажи честно. Не ставь точку в конце последнего предложения. Выделяй названия мест жирным через **название**."

    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
        ]
    }]

    result, error = await call_openrouter(messages)
    if error:
        result = "Не удалось определить место"

    conn = sqlite3.connect("history.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO requests (user_id, result) VALUES (?, ?)", (user_id, result))
    conn.commit()
    conn.close()
    return {"location": result}

@app.post("/refine")
async def refine(data: dict):
    hint = data.get("hint", "")
    previous = data.get("previous", "")

    messages = [{
        "role": "user",
        "content": f"""Я анализирую фото места. Мой предыдущий ответ: "{previous}".
Пользователь написал: "{hint}".

Важно: если пользователь называет место которого не существует или написал с ошибкой — мягко скажи что не можешь найти такое место и попроси уточнить. Не придумывай несуществующие места.

Если место реальное и конкретное — подтверди его и расскажи 1-2 интересных факта. Не используй фразу "с учётом подсказки". Пиши как будто ты это и так знал.

Если подсказка неполная (только страна или город) — уточни конкретнее, задай один вопрос.

Выделяй названия мест жирным через **название**.
Не ставь точку в конце последнего предложения.
Отвечай на русском, коротко и живо."""
    }]

    result, error = await call_openrouter(messages)
    if error:
        result = "Не удалось уточнить"
    return {"location": result, "text": result}

@app.post("/celebrate")
async def celebrate(data: dict):
    place = data.get("place", "это место")

    messages = [{
        "role": "user",
        "content": f"""Ты бот который определяет места по фото. Пользователь подтвердил место: {place}.
Напиши короткую живую реакцию на русском — 1-2 предложения. 
Стиль: спокойный, немного атмосферный, как будто тебе самому интересно это место.
Без кринжа, без пафоса, без мата, без восклицаний типа "юху", "вау", "отлично!".
Используй максимум одно эмодзи из этого списка: 🎐 🫰🏻 🍜 🪼 🍵 🍋 🧸 🥡 🪷
Не ставь точку в конце последнего предложения
Не спрашивай нужна ли помощь — это сделает бот отдельно."""
    }]

    result, error = await call_openrouter(messages)
    if error:
        result = "Нашли 🎐"
    return {"text": result}

@app.post("/intent")
async def detect_intent(data: dict):
    text = data.get("text", "")

    messages = [{
        "role": "user",
        "content": f"""Пользователь написал: "{text}"

Определи намерение. Ответь ТОЛЬКО одним словом из списка:
- POSITIVE — угадал, верно, да это оно, точно, правильно, да, ага, хочу, давай, супер, именно
- NEGATIVE — нет, не то, ошибся, не угадал, неверно, не хочу, хватит, пока, всё
- NEW_PLACE — новое место, другое место, начнём заново, другое фото
- SAME_ANGLE — другой ракурс, то же место, ещё фото отсюда, с другой стороны, то же самое, та же локация
- PHOTO_OFFER — могу прислать фото, пришлю скрин, есть ещё фотка, хочешь фото
- HINT — называет конкретное место, город, страну, достопримечательность, район
- OTHER — вопрос, непонятная фраза, всё остальное

Отвечай ТОЛЬКО одним словом."""
    }]

    result, error = await call_openrouter(messages)
    if error:
        return {"intent": "OTHER"}

    intent = result.strip().upper().split()[0] if result else "OTHER"
    valid = {"POSITIVE", "NEGATIVE", "NEW_PLACE", "SAME_ANGLE", "PHOTO_OFFER", "HINT", "OTHER"}
    if intent not in valid:
        intent = "OTHER"
    return {"intent": intent}

@app.get("/history")
def get_history(user_id: str):
    conn = sqlite3.connect("history.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT result, created_at FROM requests WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return {"history": [{"result": r[0], "created_at": r[1]} for r in rows]}

@app.post("/chat")
async def chat(data: dict):
    text = data.get("text", "")
    context = data.get("context", "")

    ctx_part = f"Контекст: мы сейчас ищем место '{context}'." if context else ""

    messages = [{
        "role": "user",
        "content": f"""Ты бот ReelSpotter — помогаешь определять места по фото из рилсов и тиктоков.
{ctx_part}
Пользователь написал: "{text}"

Ответь коротко и по-человечески на русском. Стиль спокойный, живой, без кринжа.
Если пользователь шутит или спрашивает что-то не по теме — можешь мягко поддержать но верни разговор к делу.
Используй максимум одно эмодзи из списка: 🎐 🫰🏻 🍜 🪼 🍵 🍋 🧸 🥡 🪷
Не ставь точку в конце."""
    }]

    result, error = await call_openrouter(messages)
    if error:
        result = "Пришли скриншот 🪩 или напиши /hint"
    return {"text": result}
