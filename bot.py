import json
import logging
import os
import re
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps
from telegram import InputFile, InputSticker, Update
from telegram.constants import StickerFormat
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")
STATE_FILE = Path("data.json")
STICKER_SIZE = 512
DEFAULT_EMOJI = "😀"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("sticker-bot")


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(STATE_FILE)


def user_key(update: Update) -> str:
    return str(update.effective_user.id)


def process_image(raw: bytes) -> bytes:
    """Center-crop to 1:1 and output a 512x512 WEBP sticker."""
    with Image.open(BytesIO(raw)) as img:
        img = ImageOps.exif_transpose(img).convert("RGBA")

        width, height = img.size
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2

        img = img.crop((left, top, left + side, top + side))
        img = img.resize((STICKER_SIZE, STICKER_SIZE), Image.Resampling.LANCZOS)

        out = BytesIO()
        img.save(out, format="WEBP", quality=90, method=6)
        return out.getvalue()


def safe_pack_name(title: str, username: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_]", "_", title.lower()).strip("_")
    base = re.sub(r"_+", "_", base)[:35] or "stickers"
    bot_name = re.sub(r"[^a-zA-Z0-9_]", "_", username.lower()).strip("_")
    bot_name = bot_name or "bot"
    return f"{base}_by_{bot_name}"[:64]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Отправь мне картинку — я сделаю из неё квадратный стикер 1:1.\n\n"
        "Команды:\n"
        "/newpack — начать свой стикерпак\n"
        "/emoji 😀 — выбрать эмодзи для следующего стикера\n"
        "/done — закончить стикерпак\n"
        "/cancel — отменить создание пака\n\n"
        "Обычная отправка фото работает без создания пака."
    )


async def newpack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = load_state()
    key = user_key(update)
    state[key] = {
        "mode": "waiting_first",
        "title": f"Stickers by {update.effective_user.first_name or 'User'}",
        "emoji": DEFAULT_EMOJI,
        "pack_name": None,
    }
    save_state(state)

    await update.message.reply_text(
        "Создаём новый стикерпак 🎨\n\n"
        "Теперь пришли первую картинку.\n"
        "Я спрошу название пака и создам его после обработки."
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = load_state()
    state.pop(user_key(update), None)
    save_state(state)
    await update.message.reply_text("Создание стикерпака отменено.")


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = load_state()
    item = state.get(user_key(update))

    if not item or not item.get("pack_name"):
        await update.message.reply_text("У тебя сейчас нет активного стикерпака.")
        return

    pack_name = item["pack_name"]
    state.pop(user_key(update), None)
    save_state(state)

    await update.message.reply_text(
        f"Готово! 🎉\n\n"
        f"Открыть стикерпак:\n"
        f"https://t.me/addstickers/{pack_name}"
    )


async def emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Пример: /emoji 🔥")
        return

    value = context.args[0]
    if len(value) > 8:
        await update.message.reply_text("Укажи один эмодзи, например 😀 или 🔥.")
        return

    state = load_state()
    key = user_key(update)
    item = state.setdefault(key, {"mode": "single", "emoji": DEFAULT_EMOJI})
    item["emoji"] = value
    save_state(state)

    await update.message.reply_text(f"Эмодзи установлено: {value}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    state = load_state()
    key = user_key(update)
    item = state.get(key, {"mode": "single", "emoji": DEFAULT_EMOJI})

    try:
        # Telegram can send the same image either as a photo or as an image document.
        if update.message.photo:
            tg_file = await update.message.photo[-1].get_file()
        elif update.message.document and update.message.document.mime_type:
            tg_file = await update.message.document.get_file()
        else:
            await update.message.reply_text("Пришли изображение в формате JPG, PNG или WEBP.")
            return

        raw = await tg_file.download_as_bytearray()
        sticker_bytes = process_image(bytes(raw))

        await update.message.reply_sticker(
            sticker=InputFile(sticker_bytes, filename="sticker.webp"),
            emoji=item.get("emoji", DEFAULT_EMOJI),
        )

        if item.get("mode") in ("waiting_first", "pack"):
            if not item.get("pack_name"):
                # Ask for a title only after we have successfully processed the first image.
                context.user_data["pending_first_sticker"] = sticker_bytes
                await update.message.reply_text(
                    "Стикер готов ✅\n\n"
                    "Теперь отправь название стикерпака одним сообщением.\n"
                    "Например: Мои мемы"
                )
                item["mode"] = "waiting_title"
                save_state(state)
                return

            input_sticker = InputSticker(
                sticker=sticker_bytes,
                emoji_list=[item.get("emoji", DEFAULT_EMOJI)],
                format=StickerFormat.STATIC,
            )
            await context.bot.add_sticker_to_set(
                user_id=update.effective_user.id,
                name=item["pack_name"],
                sticker=input_sticker,
            )
            await update.message.reply_text("Добавил в стикерпак ✅\nОтправляй следующую картинку.")

    except Exception:
        logger.exception("Error processing image")
        await update.message.reply_text(
            "Не получилось обработать изображение 😕\n"
            "Попробуй JPG/PNG/WEBP или картинку меньшего размера."
        )


async def handle_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    state = load_state()
    key = user_key(update)
    item = state.get(key)

    if not item or item.get("mode") != "waiting_title":
        return

    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("Название не должно быть пустым.")
        return

    pending = context.user_data.get("pending_first_sticker")
    if not pending:
        await update.message.reply_text("Первая картинка потерялась. Нажми /newpack и начни заново.")
        state.pop(key, None)
        save_state(state)
        return

    me = await context.bot.get_me()
    pack_name = safe_pack_name(title, me.username or "bot")

    # If the generated name is occupied, Telegram will return an error.
    # The user can simply choose another title.
    try:
        input_sticker = InputSticker(
            sticker=pending,
            emoji_list=[item.get("emoji", DEFAULT_EMOJI)],
            format=StickerFormat.STATIC,
        )

        await context.bot.create_new_sticker_set(
            user_id=update.effective_user.id,
            name=pack_name,
            title=title[:64],
            stickers=[input_sticker],
        )

        item["mode"] = "pack"
        item["pack_name"] = pack_name
        item["title"] = title[:64]
        state[key] = item
        save_state(state)
        context.user_data.pop("pending_first_sticker", None)

        await update.message.reply_text(
            "Стикерпак создан! 🎉\n\n"
            f"https://t.me/addstickers/{pack_name}\n\n"
            "Теперь просто отправляй следующие картинки — я буду добавлять их в этот пак.\n"
            "Когда закончишь, нажми /done."
        )
    except Exception as exc:
        logger.exception("Could not create sticker set")
        await update.message.reply_text(
            "Не удалось создать стикерпак.\n\n"
            "Возможно, такое имя уже занято. Попробуй другое название.\n\n"
            f"Техническая ошибка: {exc}"
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled exception", exc_info=context.error)


def main() -> None:
    if not TOKEN:
        raise RuntimeError(
            "Не найден BOT_TOKEN. Создай файл .env или задай переменную окружения BOT_TOKEN."
        )

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newpack", newpack))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CommandHandler("emoji", emoji))

    app.add_handler(
        MessageHandler(
            filters.PHOTO | filters.Document.IMAGE,
            handle_photo,
        )
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_title))
    app.add_error_handler(error_handler)

    print("Sticker bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
