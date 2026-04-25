import logging
from helper.database import anixlibrarybots as db   # FIX #1: updated import name
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from config import Txt

logger = logging.getLogger(__name__)


# ── Shared helper ────────────────────────────────────────────────────────────
# FIX #3 & #4: single function builds text + keyboard — no duplication,
# and fetches the full user document once instead of 7 separate DB calls.

async def _build_metadata_ui(user_id: int):
    """Fetch all metadata fields in one DB call and return (text, keyboard)."""
    try:
        user = await db.get_user(user_id)           # FIX #4: single document fetch
    except Exception as e:
        logger.error(f"Failed to fetch user {user_id} for metadata UI: {e}")
        user = {}

    def _val(key, fallback):
        return (user.get(key) or fallback) if user else fallback

    # FIX #2: metadata is stored as bool True/False, display as On/Off
    current_bool = _val('metadata', False)
    current_label = "On" if current_bool else "Off"

    text = f"""
**㊋ Yᴏᴜʀ Mᴇᴛᴀᴅᴀᴛᴀ ɪꜱ ᴄᴜʀʀᴇɴᴛʟʏ: {current_label}**

**◈ Tɪᴛʟᴇ ▹** `{_val('title', 'Nᴏᴛ ꜰᴏᴜɴᴅ')}`  
**◈ Aᴜᴛʜᴏʀ ▹** `{_val('author', 'Nᴏᴛ ꜰᴏᴜɴᴅ')}`  
**◈ Aʀᴛɪꜱᴛ ▹** `{_val('artist', 'Nᴏᴛ ꜰᴏᴜɴᴅ')}`  
**◈ Aᴜᴅɪᴏ ▹** `{_val('audio', 'Nᴏᴛ ꜰᴏᴜɴᴅ')}`  
**◈ Sᴜʙᴛɪᴛʟᴇ ▹** `{_val('subtitle', 'Nᴏᴛ ꜰᴏᴜɴᴅ')}`  
**◈ Vɪᴅᴇᴏ ▹** `{_val('video', 'Nᴏᴛ ꜰᴏᴜɴᴅ')}`  
    """

    # FIX #2: checkmark now correctly compares against bool
    buttons = [
        [
            InlineKeyboardButton(
                f"On{' ✅' if current_bool else ''}",
                callback_data='on_metadata'
            ),
            InlineKeyboardButton(
                f"Off{' ✅' if not current_bool else ''}",
                callback_data='off_metadata'
            )
        ],
        [InlineKeyboardButton("How to Set Metadata", callback_data="metainfo")]
    ]
    return text, InlineKeyboardMarkup(buttons)


# ── Handlers ─────────────────────────────────────────────────────────────────

@Client.on_message(filters.private & filters.command("metadata"))  # FIX #7: added filters.private
async def metadata(client, message):
    user_id = message.from_user.id
    text, keyboard = await _build_metadata_ui(user_id)
    await message.reply_text(text=text, reply_markup=keyboard, disable_web_page_preview=True)


@Client.on_callback_query(filters.regex(r"on_metadata|off_metadata|metainfo"))
async def metadata_callback(client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data

    if data == "metainfo":
        await query.message.edit_text(
            text=Txt.META_TXT,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Hᴏᴍᴇ", callback_data="home"),
                    InlineKeyboardButton("Cʟᴏꜱᴇ", callback_data="close")
                ]
            ])
        )
        return

    # FIX #2: store True/False bool, not "On"/"Off" string
    if data == "on_metadata":
        await db.set_metadata(user_id, True)
    elif data == "off_metadata":
        await db.set_metadata(user_id, False)

    # FIX #3: reuse shared helper — no duplicated code
    text, keyboard = await _build_metadata_ui(user_id)
    await query.message.edit_text(
        text=text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )


# ── Set commands ─────────────────────────────────────────────────────────────

@Client.on_message(filters.private & filters.command('settitle'))
async def set_title(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            "**Gɪᴠᴇ Tʜᴇ Tɪᴛʟᴇ\n\nExᴀᴍᴩʟᴇ:- /settitle Encoded By @Ongoing_english_dub**"  # FIX #6
        )
    value = message.text.split(" ", 1)[1]
    await db.set_title(message.from_user.id, title=value)
    await message.reply_text("**✅ Tɪᴛʟᴇ Sᴀᴠᴇᴅ**")


@Client.on_message(filters.private & filters.command('setauthor'))
async def set_author(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            "**Gɪᴠᴇ Tʜᴇ Aᴜᴛʜᴏʀ\n\nExᴀᴍᴩʟᴇ:- /setauthor @Ongoing_english_dub**"  # FIX #6
        )
    value = message.text.split(" ", 1)[1]
    await db.set_author(message.from_user.id, author=value)
    await message.reply_text("**✅ Aᴜᴛʜᴏʀ Sᴀᴠᴇᴅ**")


@Client.on_message(filters.private & filters.command('setartist'))
async def set_artist(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            "**Gɪᴠᴇ Tʜᴇ Aʀᴛɪꜱᴛ\n\nExᴀᴍᴩʟᴇ:- /setartist @Ongoing_english_dub**"  # FIX #6
        )
    value = message.text.split(" ", 1)[1]
    await db.set_artist(message.from_user.id, artist=value)
    await message.reply_text("**✅ Aʀᴛɪꜱᴛ Sᴀᴠᴇᴅ**")


@Client.on_message(filters.private & filters.command('setaudio'))
async def set_audio(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            "**Gɪᴠᴇ Tʜᴇ Aᴜᴅɪᴏ Tɪᴛʟᴇ\n\nExᴀᴍᴩʟᴇ:- /setaudio @Ongoing_english_dub**"  # FIX #6
        )
    value = message.text.split(" ", 1)[1]
    await db.set_audio(message.from_user.id, audio=value)
    await message.reply_text("**✅ Aᴜᴅɪᴏ Sᴀᴠᴇᴅ**")


@Client.on_message(filters.private & filters.command('setsubtitle'))
async def set_subtitle(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            "**Gɪᴠᴇ Tʜᴇ Sᴜʙᴛɪᴛʟᴇ Tɪᴛʟᴇ\n\nExᴀᴍᴩʟᴇ:- /setsubtitle @Ongoing_english_dub**"  # FIX #6
        )
    value = message.text.split(" ", 1)[1]
    await db.set_subtitle(message.from_user.id, subtitle=value)
    await message.reply_text("**✅ Sᴜʙᴛɪᴛʟᴇ Sᴀᴠᴇᴅ**")


@Client.on_message(filters.private & filters.command('setvideo'))
async def set_video(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            "**Gɪᴠᴇ Tʜᴇ Vɪᴅᴇᴏ Tɪᴛʟᴇ\n\nExᴀᴍᴩʟᴇ:- /setvideo Encoded by @Ongoing_english_dub**"  # FIX #6
        )
    value = message.text.split(" ", 1)[1]
    await db.set_video(message.from_user.id, video=value)
    await message.reply_text("**✅ Vɪᴅᴇᴏ Sᴀᴠᴇᴅ**")
