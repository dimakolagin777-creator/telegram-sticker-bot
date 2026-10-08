import os
import json
import logging
from pathlib import Path

from PIL import Image, ImageOps
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputSticker,
)
from telegram.constants import MessageEntityType
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ============================================================
# SWAGABOT — interactive Telegram sticker service
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATA_FILE = Path("data.json")
WELCOME_IMAGE = Path("welcome.jpg")  # optional: put your SWAGABOT card here

# Paste your Telegram Premium custom emoji IDs here.
# Leave "" until you have them. The bot will still work.
CUSTOM_EMOJIS = {
    "create": "",
    "packs": "",
    "new_pack": "",
    "catalog": "",
    "who": "",
    "help": "",
    "group": "",
    "back": "",
    "settings": "",
}

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("swagabot")


def load_data():
    if not DATA_FILE.exists():
        return {}
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_data(data):
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


DATA = load_data()


def user_state(user_id: int):
    key = str(user_id)
    if key not in DATA:
        DATA[key] = {
            "mode": None,
            "last_photo": None,
            "emoji": "😀",
            "pack": None,
            "packs": [],
        }
        save_data(DATA)
    return DATA[key]


def btn(text, callback, icon_key=None, style=None):
    kwargs = {"text": text, "callback_data": callback}
    icon_id = CUSTOM_EMOJIS.get(icon_key or "", "")
    if icon_id:
        kwargs["icon_custom_emoji_id"] = icon_id
    if style:
        kwargs["style"] = style
    return InlineKeyboardButton(**kwargs)


def main_keyboard():
    return InlineKeyboardMarkup([
        [
            btn("Создать стикер", "create", "create", "primary"),
            btn("Мои паки", "packs", "packs"),
        ],
        [
            btn("Новый пак", "newpack", "new_pack", "success"),
            btn("Каталог", "catalog", "catalog"),
        ],
        [
            btn("Чей стикер?", "who", "who"),
            btn("Помощь", "help", "help"),
        ],
        [
            btn("Добавить в группу", "group", "group"),
            btn("Настройки", "settings", "settings"),
        ],
    ])


def back_keyboard():
    return InlineKeyboardMarkup([
        [btn("◀️ Назад", "home", "back")]
    ])


def create_keyboard():
    return InlineKeyboardMarkup([
        [
            btn("✂️ Обрезать 1:1", "crop"),
            btn("👤 Умное кадрирование", "smart"),
        ],
        [
            btn("⬜ Оставить целиком", "full"),
            btn("🎨 Фон", "background"),
        ],
        [btn("📦 Выбрать пак", "choosepack", "packs")],
        [btn("◀️ Назад", "home", "back")],
    ])


def after_sticker_keyboard():
    return InlineKeyboardMarkup([
        [
            btn("➕ Добавить в пак", "addpack", "packs"),
            btn("📦 Новый пак", "newpack", "new_pack"),
        ],
        [
            btn("🔄 Переделать", "create", "create"),
            btn("📤 Отправить", "share"),
        ],
        [btn("◀️ В меню", "home", "back")],
    ])


async def edit_menu(query, text, keyboard):
    try:
        await query.edit_message_text(text=text, reply_markup=keyboard)
    except Exception:
        await query.message.reply_text(text, reply_markup=keyboard)


async def send_home(update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
    text = (
        "🖤 <b>SWAGABOT</b>\n\n"
        "Создавай стикеры, собирай паки и делись ими.\n\n"
        "Выбери действие ниже:"
    )

    if edit and update.callback_query:
        q = update.callback_query
        if WELCOME_IMAGE.exists():
            # Telegram cannot edit a text message into a photo reliably,
            # so keep the existing message clean and use the menu.
            await edit_menu(q, text, main_keyboard())
        else:
            await edit_menu(q, text, main_keyboard())
    else:
        if WELCOME_IMAGE.exists():
            with WELCOME_IMAGE.open("rb") as photo:
                await update.effective_message.reply_photo(
                    photo=photo,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=main_keyboard(),
                )
        else:
            await update.effective_message.reply_text(
                text, parse_mode="HTML", reply_markup=main_keyboard()
            )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state(update.effective_user.id)["mode"] = None
    save_data(DATA)
    await send_home(update, context)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "❓ <b>Помощь</b>\n\n"
        "• Отправь фото — бот подготовит стикер.\n"
        "• Используй «Мои паки», чтобы управлять наборами.\n"
        "• «Новый пак» создаёт отдельный набор.\n"
        "• /emoji 😀 — выбрать эмодзи для стикера.\n"
        "• /emojiid — узнать ID Premium-эмодзи.\n"
        "• /cancel — отменить текущее действие.\n\n"
        "Дальше добавим умное вырезание, фон, каталог и другие функции."
    )
    await update.effective_message.reply_text(
        text, parse_mode="HTML", reply_markup=back_keyboard()
    )


async def emoji_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = user_state(update.effective_user.id)
    if context.args:
        state["emoji"] = context.args[0][:8]
        save_data(DATA)
        await update.effective_message.reply_text(
            f"Эмодзи для следующего стикера: {state['emoji']}"
        )
    else:
        await update.effective_message.reply_text(
            "Используй так: /emoji 🔥"
        )


async def emoji_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    found = []
    for entity in (msg.entities or []):
        if entity.type == MessageEntityType.CUSTOM_EMOJI:
            found.append(entity.custom_emoji_id)

    if found:
        await msg.reply_text(
            "Custom emoji ID:\n\n" + "\n".join(found)
            + "\n\nВставь этот ID в CUSTOM_EMOJIS в bot.py."
        )
    else:
        await msg.reply_text(
            "Не вижу Premium-эмодзи в этом сообщении.\n"
            "Отправь мне сообщение, в котором есть нужный custom emoji."
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = user_state(update.effective_user.id)
    state["mode"] = None
    state["last_photo"] = None
    save_data(DATA)
    await update.effective_message.reply_text(
        "Действие отменено.", reply_markup=main_keyboard()
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = user_state(update.effective_user.id)
    state["mode"] = "photo_received"

    photo = update.effective_message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    tmp_dir = Path("/tmp/swagabot")
    tmp_dir.mkdir(exist_ok=True)
    src = tmp_dir / f"{update.effective_user.id}_source.jpg"
    await file.download_to_drive(src)

    state["last_photo"] = str(src)
    save_data(DATA)

    await update.effective_message.reply_text(
        "🖼️ Фото получено.\n\nКак обработать изображение?",
        reply_markup=create_keyboard(),
    )


def make_square(src: Path, mode="crop"):
    img = Image.open(src)
    img = ImageOps.exif_transpose(img).convert("RGBA")

    if mode == "crop":
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))

    elif mode == "full":
        w, h = img.size
        side = max(w, h)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.alpha_composite(img, ((side - w) // 2, (side - h) // 2))
        img = canvas

    # "smart" currently uses a safe center crop.
    # A real face/person segmentation module can be added later.
    elif mode == "smart":
        w, h = img.size
        side = min(w, h)
        # Slightly biased toward the upper center to keep faces in frame.
        left = max(0, (w - side) // 2)
        top = max(0, int((h - side) * 0.38))
        top = min(top, max(0, h - side))
        img = img.crop((left, top, left + side, top + side))

    img = img.resize((512, 512), Image.Resampling.LANCZOS)
    out = src.with_name(src.stem + "_sticker.webp")
    img.save(out, "WEBP", quality=92, method=6)
    return out


async def create_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE, mode="crop"):
    uid = update.effective_user.id
    state = user_state(uid)

    if not state.get("last_photo"):
        await update.effective_message.reply_text(
            "Сначала отправь фото.", reply_markup=main_keyboard()
        )
        return

    src = Path(state["last_photo"])
    if not src.exists():
        state["last_photo"] = None
        save_data(DATA)
        await update.effective_message.reply_text(
            "Фото больше недоступно. Отправь его ещё раз."
        )
        return

    out = make_square(src, mode)
    state["mode"] = "sticker_ready"
    state["last_sticker"] = str(out)
    save_data(DATA)

    with out.open("rb") as sticker_file:
        await update.effective_message.reply_sticker(
            sticker=sticker_file,
            emoji=state.get("emoji", "😀"),
        )

    await update.effective_message.reply_text(
        "Готово. Что делаем дальше?",
        reply_markup=after_sticker_keyboard(),
    )


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    action = q.data
    state = user_state(q.from_user.id)

    if action == "home":
        state["mode"] = None
        save_data(DATA)
        await send_home(update, context, edit=True)

    elif action == "create":
        state["mode"] = "waiting_photo"
        save_data(DATA)
        await edit_menu(
            q,
            "🖼️ <b>Создание стикера</b>\n\n"
            "Отправь сюда фотографию или изображение.",
            back_keyboard(),
        )

    elif action == "packs":
        packs = state.get("packs", [])
        if packs:
            lines = "\n".join(f"• {p}" for p in packs)
            text = f"📁 <b>Мои паки</b>\n\n{lines}"
        else:
            text = (
                "📁 <b>Мои паки</b>\n\n"
                "Пока нет созданных паков.\n"
                "Создай первый через «Новый пак»."
            )
        await edit_menu(q, text, InlineKeyboardMarkup([
            [btn("➕ Новый пак", "newpack", "new_pack")],
            [btn("◀️ Назад", "home", "back")],
        ]))

    elif action == "newpack":
        state["mode"] = "new_pack"
        save_data(DATA)
        await edit_menu(
            q,
            "📦 <b>Новый пак</b>\n\n"
            "Отправь название пака одним сообщением.\n\n"
            "Пример: <code>SWAG MEMES</code>",
            back_keyboard(),
        )

    elif action == "catalog":
        await edit_menu(
            q,
            "🌐 <b>Каталог</b>\n\n"
            "Каталог пока в разработке.\n"
            "Здесь появится поиск и подборка публичных паков.",
            back_keyboard(),
        )

    elif action == "who":
        await edit_menu(
            q,
            "🔍 <b>Чей стикер?</b>\n\n"
            "Отправь мне стикер — позже бот определит, из какого он пака.",
            back_keyboard(),
        )

    elif action == "help":
        await edit_menu(
            q,
            "❓ <b>Помощь</b>\n\n"
            "Отправь фото → выбери обработку → получи стикер.\n\n"
            "Команды:\n"
            "/start — главное меню\n"
            "/emoji 🔥 — эмодзи стикера\n"
            "/emojiid — ID Premium-эмодзи\n"
            "/cancel — отмена",
            back_keyboard(),
        )

    elif action == "group":
        await edit_menu(
            q,
            "👥 <b>Добавить SWAGABOT в группу</b>\n\n"
            "Нажми кнопку ниже, чтобы выбрать группу.",
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "➕ Добавить в группу",
                        url="https://t.me/SWAGABOT?startgroup=true",
                    )
                ],
                [btn("◀️ Назад", "home", "back")],
            ]),
        )

    elif action == "settings":
        await edit_menu(
            q,
            "⚙️ <b>Настройки</b>\n\n"
            f"Эмодзи: {state.get('emoji', '😀')}\n"
            "Обрезка: 1:1\n"
            "Размер: 512×512\n\n"
            "Расширенные настройки добавим следующим этапом.",
            InlineKeyboardMarkup([
                [btn("😀 Изменить эмодзи", "setemoji")],
                [btn("◀️ Назад", "home", "back")],
            ]),
        )

    elif action in ("crop", "smart", "full"):
        await create_sticker(update, context, action)

    elif action == "background":
        await edit_menu(
            q,
            "🎨 <b>Изменение фона</b>\n\n"
            "Эта функция будет добавлена следующим этапом.",
            back_keyboard(),
        )

    elif action in ("choosepack", "addpack"):
        packs = state.get("packs", [])
        if not packs:
            await edit_menu(
                q,
                "📦 У тебя пока нет паков.\n\nСоздай новый пак.",
                InlineKeyboardMarkup([
                    [btn("➕ Новый пак", "newpack", "new_pack")],
                    [btn("◀️ Назад", "home", "back")],
                ]),
            )
        else:
            keyboard = [[btn(p, f"usepack:{i}")] for i, p in enumerate(packs)]
            keyboard.append([btn("◀️ Назад", "home", "back")])
            await edit_menu(q, "📦 Выбери пак:", InlineKeyboardMarkup(keyboard))

    elif action.startswith("usepack:"):
        index = int(action.split(":", 1)[1])
        packs = state.get("packs", [])
        if 0 <= index < len(packs):
            state["pack"] = packs[index]
            save_data(DATA)
            await edit_menu(
                q,
                f"✅ Выбран пак: <b>{packs[index]}</b>\n\n"
                "Следующий стикер можно будет добавить сюда.",
                after_sticker_keyboard(),
            )

    elif action == "share":
        await q.message.reply_text(
            "📤 Нажми и удерживай стикер → Переслать.\n"
            "Автоматическую публикацию в канал добавим позже."
        )

    elif action == "setemoji":
        state["mode"] = "set_emoji"
        save_data(DATA)
        await edit_menu(
            q,
            "😀 Отправь обычный emoji одним сообщением.\n"
            "Например: 🔥",
            back_keyboard(),
        )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_message.text:
        return

    state = user_state(update.effective_user.id)
    text = update.effective_message.text.strip()

    if state.get("mode") == "new_pack":
        if len(text) < 1:
            return
        packs = state.setdefault("packs", [])
        if text not in packs:
            packs.append(text[:64])
        state["pack"] = text[:64]
        state["mode"] = None
        save_data(DATA)
        await update.effective_message.reply_text(
            f"📦 Пак <b>{text[:64]}</b> создан.\n\n"
            "Теперь отправь фото, чтобы создать первый стикер.",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )

    elif state.get("mode") == "set_emoji":
        state["emoji"] = text[:8]
        state["mode"] = None
        save_data(DATA)
        await update.effective_message.reply_text(
            f"Готово. Новый emoji: {state['emoji']}",
            reply_markup=main_keyboard(),
        )


async def sticker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "🔍 Стикер получен.\nФункция «Чей стикер?» будет подключена следующим этапом."
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "Не найден BOT_TOKEN. Добавь переменную BOT_TOKEN в Railway → Variables."
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("emoji", emoji_cmd))
    app.add_handler(CommandHandler("emojiid", emoji_id))
    app.add_handler(CommandHandler("cancel", cancel))

    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Sticker.ALL, sticker_handler))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler)
    )

    logger.info("SWAGABOT started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
