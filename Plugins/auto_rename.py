import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from helper.database import anixlibrarybots          # FIX #1: updated import name

logger = logging.getLogger(__name__)                 # FIX #3 & #6: logger set up

# FIX #4 & #5: explicit allowlist — only these values can ever be saved
VALID_MEDIA_TYPES = {"document", "video", "audio"}


@Client.on_message(filters.private & filters.command("autorename"))
async def auto_rename_command(client, message):
    user_id = message.from_user.id

    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2 or not command_parts[1].strip():
        await message.reply_text(
            "**Please provide a new name after the command /autorename**\n\n"
            "Here's how to use it:\n"
            "**Example format:** `/autorename Overflow [S{season}E{episode}] - [Dual] {quality}`"
        )
        return

    format_template = command_parts[1].strip()
    await anixlibrarybots.set_format_template(user_id, format_template)

    await message.reply_text(
        f"**🌟 Fantastic! You're ready to auto-rename your files.**\n\n"
        "📩 Simply send the file(s) you want to rename.\n\n"
        f"**Your saved template:** `{format_template}`\n\n"
        "Remember, it might take some time, but I'll ensure your files are renamed perfectly! ✨"
    )


@Client.on_message(filters.private & filters.command("setmedia"))
async def set_media_command(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Documents", callback_data="setmedia_document")],
        [InlineKeyboardButton("🎬 Videos",    callback_data="setmedia_video")],
        [InlineKeyboardButton("🎵 Audio",     callback_data="setmedia_audio")],
    ])
    await message.reply_text(
        "✨ **Choose Your Media Vibe** ✨\n"
        "Select the type of media you'd like to set as your preference:",
        reply_markup=keyboard,
        quote=True
    )


@Client.on_callback_query(filters.regex(r"^setmedia_"))
async def handle_media_selection(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    raw_type = callback_query.data.split("_", 1)[1].lower()

    # FIX #5: reject anything not in the allowlist
    if raw_type not in VALID_MEDIA_TYPES:
        logger.warning(f"User {user_id} sent invalid media type: {raw_type!r}")
        await callback_query.answer("Invalid media type selected.", show_alert=True)
        return

    media_type_display = raw_type.capitalize()      # FIX #4: capitalize only after validation

    try:
        await anixlibrarybots.set_media_preference(user_id, raw_type)
        await callback_query.answer(f"Locked in: {media_type_display} 🎉")
        await callback_query.message.edit_text(
            f"🎯 **Media Preference Updated** 🎯\n"
            f"Your vibe is now set to: **{media_type_display}** ✅\n"
            f"Ready to roll with your choice!"
        )
    except Exception as e:
        logger.error(f"Failed to set media preference for user {user_id}: {e}")   # FIX #2 & #3
        await callback_query.answer("Oops, something went wrong! 😅", show_alert=True)
        await callback_query.message.edit_text(
            "⚠️ **Error Setting Preference** ⚠️\n"
            "Couldn't update your preference right now. Please try again later!"
            # FIX #2: removed str(e) from user-facing message
  )
