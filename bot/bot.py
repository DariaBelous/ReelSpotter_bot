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

BANNED = ["сук", "пизд", "хер", "бля", "нах", "еб", "жест", "капец", "йоу", "юху", "вау"]

def filter_response(text: str) -> str:
    lower = text.lower()
    for word in BANNED:
        if word in lower:
            return text.split(".")[0]
    return text


@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "Привет 🥢🥡\n\n"
        "Отправь скриншот из рилса или тиктока — я попробую определить место\n\n"
        "/hint — подсказать где снято\n"
        "/history — история запросов\n"
        "/reset — начать заново"
    )


@dp.message(Command("reset"))
async def handle_reset(message: Message):
    user_context[message.from_user.id] = {}
    await message.answer("Сброшено 🪷 Пришли новое фото")


@dp.message(Command("hint"))
async def handle_hint(message: Message):
    ctx = user_context.get(message.from_user.id, {})
    user_context[message.from_user.id] = {**ctx, "waiting_hint": True}
    await message.answer("Расскажи подробнее — страна, город, район или что это за место 🧭")


@dp.message(Command("history"))
async def handle_history(message: Message):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BACKEND_URL}/history",
            params={"user_id": str(message.from_user.id)}
        ) as resp:
            result = await resp.json()
    history = result.get("history", [])
    if not history:
        await message.answer("История пуста")
        return
    text = "📋 Последние запросы:\n\n"
    for item in history:
        text += f"🕐 {item['created_at']}\n{item['result']}\n\n"
    await message.answer(text)


@dp.message(F.photo)
async def handle_photo(message: Message):
    ctx = user_context.get(message.from_user.id, {})

    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"

    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            image_bytes = await resp.read()

    # Ждём фото с другого ракурса
    if ctx.get("expecting_angle"):
        await message.answer("Анализирую другой ракурс... 🦭")
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field("file", image_bytes, filename="photo.jpg", content_type="image/jpeg")
                params = {"user_id": str(message.from_user.id)}
                if ctx.get("last_result"):
                    params["previous_guess"] = ctx["last_result"]
                async with session.post(f"{BACKEND_URL}/analyze", params=params, data=data) as resp:
                    result = await resp.json()
            location = result.get("location", "Не удалось определить место")
        except asyncio.TimeoutError:
            location = "Не удалось определить место — попробуй ещё раз"
        user_context[message.from_user.id] = {**ctx, "last_result": location, "expecting_angle": False}
        await message.answer(f"📍 {location}", parse_mode="Markdown")
        await message.answer("Угадал? Если нет — /hint или пришли ещё фото 🗺")
        return

    # Есть активный контекст — спрашиваем
    if ctx.get("last_result") and not ctx.get("waiting_hint"):
        user_context[message.from_user.id] = {**ctx, "pending_photo": image_bytes.hex()}
        await message.answer("Это другой ракурс того же места или новое место? 🍵\n\nНапиши «то же место» или «новое место»")
        return

    # Обычный анализ
    thinking_task = asyncio.create_task(
        asyncio.sleep(8)
    )
    analyze_done = asyncio.Event()

    async def do_analyze():
        nonlocal result_data
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field("file", image_bytes, filename="photo.jpg", content_type="image/jpeg")
                async with session.post(
                    f"{BACKEND_URL}/analyze",
                    params={"user_id": str(message.from_user.id)},
                    data=data
                ) as resp:
                    result_data = await resp.json()
        except Exception:
            result_data = {"location": "Не удалось определить место"}
        finally:
            analyze_done.set()

    result_data = {}
    await message.answer("Анализирую фото... 🦭")
    analyze_task = asyncio.create_task(do_analyze())

    # Если долго думает — пишем промежуточное сообщение
    done, _ = await asyncio.wait(
        [analyze_task, thinking_task],
        return_when=asyncio.FIRST_COMPLETED
    )

    if thinking_task in done and not analyze_done.is_set():
        await message.answer("думаю немного дольше обычного... 🍵")

    await analyze_done.wait()

    location = result_data.get("location", "Не удалось определить место")
    user_context[message.from_user.id] = {"last_result": location, "photos": [image_bytes.hex()]}
    await message.answer(f"📍 {location}", parse_mode="Markdown")
    await message.answer("Угадал? Если нет — /hint или пришли ещё фото 🗺")


@dp.message(F.text)
async def handle_text(message: Message):
    ctx = user_context.get(message.from_user.id, {})

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BACKEND_URL}/intent",
            json={"text": message.text}
        ) as resp:
            intent_result = await resp.json()

    intent = intent_result.get("intent", "OTHER")

    # Ждём ответ "ещё поискать?"
    if ctx.get("awaiting_new_search"):
        if intent == "POSITIVE":
            user_context[message.from_user.id] = {}
            await message.answer("Пришли новое фото 🥷🏻")
        elif intent == "NEGATIVE":
            user_context[message.from_user.id] = {}
            await message.answer("Хорошо 🎐")
        else:
            await message.answer("Напиши «да» если хочешь найти ещё место, или «нет»")
        return

    if intent == "PHOTO_OFFER":
        await message.answer("Да, пришли 🍋")

    elif intent == "SAME_ANGLE":
        if ctx.get("pending_photo"):
            image_bytes = bytes.fromhex(ctx["pending_photo"])
            await message.answer("Анализирую другой ракурс... 🦭")
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field("file", image_bytes, filename="photo.jpg", content_type="image/jpeg")
                params = {"user_id": str(message.from_user.id)}
                if ctx.get("last_result"):
                    params["previous_guess"] = ctx["last_result"]
                async with session.post(f"{BACKEND_URL}/analyze", params=params, data=data) as resp:
                    result = await resp.json()
            location = result.get("location", "Не удалось определить место")
            user_context[message.from_user.id] = {**ctx, "last_result": location, "pending_photo": None}
            await message.answer(f"📍 {location}", parse_mode="Markdown")
            await message.answer("Угадал теперь? 🫵🏻")
        else:
            user_context[message.from_user.id] = {**ctx, "expecting_angle": True}
            await message.answer("Окей, жду фото с другого ракурса 🦭")

    elif intent == "NEW_PLACE":
        if ctx.get("pending_photo"):
            image_bytes = bytes.fromhex(ctx["pending_photo"])
            await message.answer("Ищу новое место... 🦭")
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field("file", image_bytes, filename="photo.jpg", content_type="image/jpeg")
                async with session.post(
                    f"{BACKEND_URL}/analyze",
                    params={"user_id": str(message.from_user.id)},
                    data=data
                ) as resp:
                    result = await resp.json()
            location = result.get("location", "Не удалось определить место")
            user_context[message.from_user.id] = {"last_result": location}
            await message.answer(f"📍 {location}", parse_mode="Markdown")
            await message.answer("Угадал? Если нет — /hint или пришли ещё фото 🫟")
        else:
            user_context[message.from_user.id] = {}
            await message.answer("Окей 🪷 Пришли новое фото")

    elif intent == "POSITIVE" and ctx.get("last_result"):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BACKEND_URL}/celebrate",
                json={"place": ctx.get("last_result")}
            ) as resp:
                result = await resp.json()
        celebration = filter_response(result.get("text", "Нашли 🎐"))
        user_context[message.from_user.id] = {"awaiting_new_search": True}
        await message.answer(celebration)
        await asyncio.sleep(0.5)
        await message.answer("Хочешь найти ещё одно место? 🎐")

    elif intent == "NEGATIVE" and ctx.get("last_result"):
        await message.answer("Ой, промахнулся 🪼 Напиши /hint или пришли ещё фото")
        user_context[message.from_user.id] = {**ctx, "waiting_hint": True}

    elif intent == "HINT" or ctx.get("waiting_hint"):
        last = ctx.get("last_result", "")
        user_context[message.from_user.id] = {**ctx, "waiting_hint": False}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BACKEND_URL}/refine",
                json={"user_id": str(message.from_user.id), "hint": message.text, "previous": last}
            ) as resp:
                result = await resp.json()
        text = filter_response(result.get("text", result.get("location", "Не удалось уточнить")))
        location = result.get("location", text)
        user_context[message.from_user.id] = {**ctx, "last_result": location, "waiting_hint": False}
        await message.answer(f"📍 {text}", parse_mode="Markdown")
        await message.answer("Нашли место? 🎐")

    else:
        # OTHER — отвечаем через ИИ как обычный чат
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BACKEND_URL}/chat",
                json={"text": message.text, "context": ctx.get("last_result", "")}
            ) as resp:
                result = await resp.json()
        reply = filter_response(result.get("text", "Пришли скриншот 🪩 или напиши /hint"))
        await message.answer(reply)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
