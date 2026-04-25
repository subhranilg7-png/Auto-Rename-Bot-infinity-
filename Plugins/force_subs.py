import time
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.errors import UserNotParticipant
from config import Config

logger = logging.getLogger(__name__)

# ── Force sub master switch ──────────────────────────────────────────────────
# Normalise to a clean list — handles None, "", "  ", and already-a-list cases
_raw = Config.FORCE_SUB_CHANNELS
if not _raw:
    FORCE_SUB_CHANNELS = []
elif isinstance(_raw, (list, tuple)):
    FORCE_SUB_CHANNELS = [c for c in _raw if c]    # drop any empty entries
else:
    FORCE_SUB_CHANNELS = [_raw]                     # single value — wrap in list

# If no channels are configured, force-sub is completely disabled.
# The filter always returns False and the handler never fires.
FORCE_SUB_ENABLED = bool(FORCE_SUB_CHANNELS)
if not FORCE_SUB_ENABLED:
    logger.info("Force-sub is DISABLED — no channels configured.")
else:
    logger.info(f"Force-sub is ENABLED for channels: {FORCE_SUB_CHANNELS}")

# ── Per-user prompt cooldown ─────────────────────────────────────────────────
# Prevents the bot from re-prompting the same user within the cooldown window.
# Stores {user_id: last_prompt_timestamp}
_last_prompted: dict[int, float] = {}
PROMPT_COOLDOWN_SECONDS = 30

IMAGE_URL = getattr(Config, "FORCE_SUB_IMAGE", "https://files.catbox.moe/xqr30z.jpg")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _channel_url(channel) -> str:
    """Safely build a t.me URL for both username strings and numeric IDs."""
    if isinstance(channel, int):
        return f"https://t.me/c/{str(channel).replace('-100', '')}"
    return f"https://t.me/{str(channel).lstrip('@')}"


async def _get_unjoined_channels(client, user_id: int) -> list:
    """Return list of channels the user has not joined. Never raises."""
    if not FORCE_SUB_ENABLED:
        return []                                   # master switch — always clean exit
    unjoined = []
    for channel in FORCE_SUB_CHANNELS:
        try:
            member = await client.get_chat_member(channel, user_id)
            if member.status in {"kicked", "left"}:
                unjoined.append(channel)
        except UserNotParticipant:
            unjoined.append(channel)
        except Exception as e:
            # Log the error but do NOT treat it as "unjoined" — API errors
            # should never trigger the force-sub prompt
            logger.error(f"Membership check failed for user {user_id} in {channel}: {e}")
    return unjoined


def _build_join_buttons(unjoined_channels: list) -> list:
    """Build inline keyboard rows for all unjoined channels."""
    buttons = [
        [InlineKeyboardButton(
            text=f"• ᴊᴏɪɴ {str(channel).lstrip('@').capitalize()} •",
            url=_channel_url(channel)
        )]
        for channel in unjoined_channels
    ]
    buttons.append([
        InlineKeyboardButton(text="• ᴊᴏɪɴᴇᴅ •", callback_data="check_subscription")
    ])
    return buttons


def _is_on_cooldown(user_id: int) -> bool:
    """Return True if the user was prompted recently and should be silenced."""
    last = _last_prompted.get(user_id)
    if last and (time.time() - last) < PROMPT_COOLDOWN_SECONDS:
        return True
    return False


def _record_prompt(user_id: int):
    """Record that we just prompted this user."""
    _last_prompted[user_id] = time.time()


# ── Filter ───────────────────────────────────────────────────────────────────

async def not_subscribed(_, client, message):
    """
    Filter: returns True only when ALL of these are true:
      1. Force-sub is enabled (channels are configured)
      2. message.from_user exists
      3. The user has genuinely not joined at least one channel
      4. The user is not on the prompt cooldown
    """
    if not FORCE_SUB_ENABLED:                       # master switch
        return False
    try:
        user_id = message.from_user.id
    except AttributeError:
        return False                                 # no sender (channel post etc.)
    if _is_on_cooldown(user_id):                    # spam protection
        return False
    try:
        unjoined = await _get_unjoined_channels(client, user_id)
    except Exception as e:
        logger.error(f"not_subscribed filter crashed for {user_id}: {e}")
        return False                                 # on any unexpected error — allow through
    return len(unjoined) > 0


# ── Handlers ─────────────────────────────────────────────────────────────────

@Client.on_message(filters.private & filters.create(not_subscribed))
async def forces_sub(client, message):
    """Show force-subscribe prompt listing all unjoined channels."""
    if not FORCE_SUB_ENABLED:                       # double-check master switch
        return
    user_id = message.from_user.id
    unjoined = await _get_unjoined_channels(client, user_id)
    if not unjoined:
        return                                       # passed filter but all joined — do nothing
    _record_prompt(user_id)                         # start cooldown BEFORE sending
    buttons = _build_join_buttons(unjoined)
    await message.reply_photo(
        photo=IMAGE_URL,
        caption=(
            "**ᴀʀᴀ ᴀʀᴀ!!, ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ʟɪᴄᴋᴇᴅ ᴍʏ ꜰᴏᴏᴛ, "
            "ʟɪᴄᴋɪɴɢ ᴍʏ ꜰᴏᴏᴛ ɪꜱ ʀᴇǫᴜɪʀᴇᴅ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ**"
        ),
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@Client.on_callback_query(filters.regex("check_subscription"))
async def check_subscription(client, callback_query: CallbackQuery):
    """Re-check subscription status when user taps the Joined button."""
    if not FORCE_SUB_ENABLED:
        await callback_query.answer("No force-sub channels configured.", show_alert=True)
        return
    user_id = callback_query.from_user.id
    unjoined = await _get_unjoined_channels(client, user_id)
    if not unjoined:
        new_text = (
            "**ʏᴏᴜ ʜᴀᴠᴇ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ʟɪᴄᴋᴇᴅ ᴍʏ ꜰᴏᴏᴛ. "
            "ɢᴏᴏᴅ ʙᴏʏ!  /start ɴᴏᴡ**"
        )
        if callback_query.message.caption != new_text:
            await callback_query.message.edit_caption(
                caption=new_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("• ɴᴏᴡ ᴄʟɪᴄᴋ ʜᴇʀᴇ •", callback_data="help")]
                ])
            )
    else:
        text = (
            "**ᴀʀᴇ ʏᴏᴜ ɴᴏᴛ ɢᴏɪɴɢ ᴛᴏ ʟɪᴄᴋ ᴍʏ ꜰᴏᴏᴛ. "
            "ʟɪᴄᴋ ᴍʏ ꜰᴏᴏᴛ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ**"
        )
        buttons = _build_join_buttons(unjoined)
        if callback_query.message.caption != text:
            await callback_query.message.edit_caption(
                caption=text,
                reply_markup=InlineKeyboardMarkup(buttons)
          )
