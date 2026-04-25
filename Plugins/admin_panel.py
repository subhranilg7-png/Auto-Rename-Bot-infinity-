from config import Config, Txt
from helper.database import anixlibrarybots          # FIX #3: updated import name
from pyrogram.types import Message
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid
import os, sys, asyncio, logging, datetime, time
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ADMIN_USER_ID = Config.ADMIN

# FIX #4: track bot start time manually since Pyrogram has no .uptime attribute
BOT_START_TIME = time.time()

# Flag to indicate if the bot is restarting
is_restarting = False


@Client.on_message(filters.private & filters.command("restart") & filters.user(ADMIN_USER_ID))
async def restart_bot(b, m):
    global is_restarting
    if not is_restarting:
        is_restarting = True
        try:
            await m.reply_text("**Restarting.....**")
            await asyncio.sleep(2)      # FIX #5: was time.sleep() — blocking in async context
            await b.stop()              # FIX #2: was b.stop() without await
            os.execl(sys.executable, sys.executable, *sys.argv)
        except Exception as e:
            is_restarting = False       # FIX #6: reset flag so restart can be retried
            logger.error(f"Restart failed: {e}")
            await m.reply_text(f"**Restart failed:** `{e}`")


@Client.on_message(filters.private & filters.command("tutorial"))
async def tutorial(bot: Client, message: Message):
    user_id = message.from_user.id
    format_template = await anixlibrarybots.get_format_template(user_id)
    await message.reply_text(
        text=Txt.FILE_NAME_TXT.format(format_template=format_template),
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("• ᴏᴡɴᴇʀ", url=Config.OWNER_URL),       # FIX #7: moved to Config
                InlineKeyboardButton("• ᴛᴜᴛᴏʀɪᴀʟ", url=Config.TUTORIAL_URL)  # FIX #7: moved to Config
            ]
        ])
    )


@Client.on_message(filters.command(["stats", "status"]) & filters.user(Config.ADMIN))
async def get_stats(bot, message):
    total_users = await anixlibrarybots.total_users_count()
    uptime = time.strftime("%Hh%Mm%Ss", time.gmtime(time.time() - BOT_START_TIME))  # FIX #4
    start_t = time.time()
    st = await message.reply('**Accessing The Details.....**')
    end_t = time.time()
    time_taken_s = (end_t - start_t) * 1000
    await st.edit(
        text=f"**--Bot Status--**\n\n"
             f"**⌚️ Bot Uptime :** {uptime}\n"
             f"**🐌 Current Ping :** `{time_taken_s:.3f} ms`\n"
             f"**👭 Total Users :** `{total_users}`"
    )


@Client.on_message(filters.command("broadcast") & filters.user(Config.ADMIN) & filters.reply)
async def broadcast_handler(bot: Client, m: Message):
    await bot.send_message(
        Config.LOG_CHANNEL,
        f"{m.from_user.mention} (`{m.from_user.id}`) started the broadcast."
    )
    all_users = await anixlibrarybots.get_all_users()
    broadcast_msg = m.reply_to_message
    sts_msg = await m.reply_text("Broadcast Started..!")
    done = 0
    failed = 0
    success = 0
    start_time = time.time()
    total_users = await anixlibrarybots.total_users_count()

    async for user in all_users:
        sts = await send_msg(user['_id'], broadcast_msg)
        if sts == 200:
            success += 1
        else:
            failed += 1                         # FIX #8: 500 (unknown errors) now counted as failed too
        if sts == 400:
            await anixlibrarybots.delete_user(user['_id'])
        done += 1
        if not done % 20:
            await sts_msg.edit(
                f"Broadcast In Progress:\n\n"
                f"Total Users: {total_users}\n"
                f"Completed: {done} / {total_users}\n"
                f"Success: {success}\n"
                f"Failed: {failed}"
            )

    completed_in = datetime.timedelta(seconds=int(time.time() - start_time))
    await sts_msg.edit(
        f"Bʀᴏᴀᴅᴄᴀꜱᴛ Cᴏᴍᴩʟᴇᴛᴇᴅ:\n"
        f"Cᴏᴍᴩʟᴇᴛᴇᴅ Iɴ `{completed_in}`.\n\n"
        f"Total Users: {total_users}\n"
        f"Completed: {done} / {total_users}\n"
        f"Success: {success}\n"
        f"Failed: {failed}"
    )


async def send_msg(user_id, message):
    try:
        await message.copy(chat_id=int(user_id))
        return 200
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await send_msg(user_id, message)  # FIX #1: was missing await — returned coroutine object
    except InputUserDeactivated:
        logger.info(f"{user_id} : Deactivated")
        return 400
    except UserIsBlocked:
        logger.info(f"{user_id} : Blocked The Bot")
        return 400
    except PeerIdInvalid:
        logger.info(f"{user_id} : User ID Invalid")
        return 400
    except Exception as e:
        logger.error(f"{user_id} : {e}")
        return 500
