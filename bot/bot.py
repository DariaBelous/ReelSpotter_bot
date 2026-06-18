import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BACKEND_URL = "http://127.0.0.1:8000"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

user_context = {}

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "Привет! Я ReelSpotter 🥡🥢\n\n"
        "Отправь мне скриншот из рилса или тиктока — я попробую определить место.\n\n"
        "Команды:\n"
        "/history — история твоих запросов\n"
        "/hint — подсказать мне где снято"
    )

@dp.message(F.photo)
async def handle_photo(message: Message):
    ctx = user_context.get(message.from_user.id, {})
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"
    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            image_bytes = await resp.read()
    if ctx.get("last_result") and not ctx.get("waiting_hint"):
        user_context[message.from_user.id] = {**ctx, "pending_photo": image_bytes.hex()}
        await message.answer("Это другой ракурс того же места или новое место? 🍵\n\nНапиши другой ракурс или новое место")
        return
    photos = ctx.get("photos", [])
    photos.append(image_bytes.hex())
    await message.answer("анализирую фото... 🦭")
    async with aiohttp.ClientSession() as session:
        data = aiohttp.FormData()
        data.add_field("file", image_bytes, filename="photo.jpg", content_type="image/jpeg")
        async with session.post(f"{BACKEND_URL}/analyze", params={"user_id": str(message.from_user.id)}, data=data) as resp:
            result = await resp.json()
    location = result.get("location", "Не удалось определить место")
    user_context[message.from_user.id] = {"last_result": location, "photos": photos}
    await message.answer(f"📍 {location}")
    await message.answer("Угадал? Если нет — напиши /hint или пришли ещё фото 🗺")

@dp.message(F.text & F.text.lower.in_({"другой ракурс", "новое место"}))
async def handle_angle_choice(message: Message):
    ctx = user_context.get(message.from_user.id, {})
    pending = ctx.get("pending_photo")
    if not pending:
        await message.answer("Отправь фото!")
        return
    image_bytes = bytes.fromhex(pending)
    if "новое место" in message.text.lower():
        user_context[message.from_user.id] = {}
        await message.answer("Окей, начинаем заново! Анализирую... 🪷")
    else:
        photos = ctx.get("photos", [])
        photos.append(pending)
        user_context[message.from_user.id] = {**ctx, "photos": photos}
        await message.answer("Понял, смотрю с другого ракурса... 🦭")
    async with aiohttp.ClientSession() as session:
        data = aiohttp.FormData()
        data.add_field("file", image_bytes, filename="photo.jpg", content_type="image/jpeg")
        previous = ctx.get("last_result", "") if "другой ракурс" in message.text.lower() else ""
        params = {"user_id": str(message.from_user.id)}
        if previous:
            params["previous_guess"] = previous
        async with session.post(f"{BACKEND_URL}/analyze", params=params, data=data) as resp:
            result = await resp.json()
    location = result.get("location", "Не удалось определить место")
    user_context[message.from_user.id] = {"last_result": location, "photos": ctx.get("photos", [])}
    await message.answer(f"📍 {location}")
    await message.answer("Угадал теперь? 🫵🏻")

@dp.message(Command("hint"))
async def handle_hint(message: Message):
    ctx = user_context.get(message.from_user.id, {})
    await message.answer("Расскажи подробнее — в какой стране, городе или что за место? Я попробую уточнить 🧭")
    user_context[message.from_user.id] = {**ctx, "waiting_hint": True}

@dp.message(Command("history"))
async def handle_history(message: Message):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BACKEND_URL}/history", params={"user_id": str(message.from_user.id)}) as resp:
            result = await resp.json()
    history = result.get("history", [])
    if not history:
        await message.answer("История пуста.")
        return
    text = "📋 Твои последние запросы:\n\n"
    for item in history:
        text += f"🕐 {item['created_at']}\n{item['result']}\n\n"
    await message.answer(text)

@dp.message(F.text)
async def handle_text(message: Message):
    ctx = user_context.get(message.from_user.id, {})
    text_lower = message.text.lower()
    positive_words = ["угадал", "да", "верно", "точно", "правильно", "yes", "yep", "так и есть"]
    negative_words = ["не угадал", "нет", "неверно", "не то", "ошибся", "промахнулся", "такого нет"]
    is_positive = any(word in text_lower for word in positive_words)
    is_negative = any(word in text_lower for word in negative_words)
    if ctx.get("waiting_hint"):
        hint = message.text
        photo_offer_words = ["фото", "photo", "пришлю", "прислать", "скрин", "картинку"]
        if any(w in hint.lower() for w in photo_offer_words):
            await message.answer("Да, пришли фото! 🍋")
            user_context[message.from_user.id] = {**ctx, "waiting_hint": False}
            return
        last = ctx.get("last_result", "")
        user_context[message.from_user.id] = {}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BACKEND_URL}/refine",
                json={"user_id": str(message.from_user.id), "hint": hint, "previous": last}
            ) as resp:
                result = await resp.json()
        location = result.get("location", "Не удалось уточнить")
        user_context[message.from_user.id] = {"last_result": location}
        await message.answer(f"📍 С учётом подсказки: {location}")
        await message.answer("Угадал? Если нет — снова /hint или пришли фото 🗺")
    elif is_positive and ctx.get("last_result"):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BACKEND_URL}/celebrate",
                json={"place": ctx.get("last_result")}
            ) as resp:
                result = await resp.json()
        celebration = result.get("text", "Ура 🫰🏻")
        user_context[message.from_user.id] = {"last_result": ctx.get("last_result"), "celebrated": True}
        await message.answer(celebration)
    elif is_negative and ctx.get("last_result"):
        await message.answer("Ой, промахнулся 🪼 Напиши /hint — расскажи где это было, попробую уточнить!")
        user_context[message.from_user.id] = {"last_result": ctx.get("last_result"), "waiting_hint": True}
    elif ctx.get("celebrated") and any(w in text_lower for w in ["хотя", "погоди", "стоп", "подожди", "не то"]):
        await message.answer("Ой, подожди! Напиши /hint и уточни 🧭")
        user_context[message.from_user.id] = {"last_result": ctx.get("last_result"), "waiting_hint": True}
    elif any(w in text_lower for w in ["фото", "photo", "пришлю", "прислать", "скрин"]):
        await message.answer("Да, пришли! 🧸")
    else:
        await message.answer("Отправь мне скриншот 🪩 или используй /hint чтобы уточнить место.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())