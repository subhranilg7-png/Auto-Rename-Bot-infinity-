import os
import re
import time
import shutil
import asyncio
import logging
from datetime import datetime
from PIL import Image
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import InputMediaDocument, Message
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from plugins.antinsfw import check_anti_nsfw
from helper.utils import progress_for_pyrogram, humanbytes   # FIX #9: removed unused `convert`
from helper.database import anixlibrarybots                  # FIX #1: updated import name
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global dictionary to track ongoing operations
renaming_operations = {}

# Enhanced regex patterns for season and episode extraction
SEASON_EPISODE_PATTERNS = [
    (re.compile(r'S(\d+)(?:E|EP)(\d+)'), ('season', 'episode')),
    (re.compile(r'S(\d+)[\s-]*(?:E|EP)(\d+)'), ('season', 'episode')),
    (re.compile(r'Season\s*(\d+)\s*Episode\s*(\d+)', re.IGNORECASE), ('season', 'episode')),
    (re.compile(r'\[S(\d+)\]\[E(\d+)\]'), ('season', 'episode')),
    (re.compile(r'S(\d+)[^\d]*(\d+)'), ('season', 'episode')),
    (re.compile(r'(?:E|EP|Episode)\s*(\d+)', re.IGNORECASE), (None, 'episode')),
    (re.compile(r'\b(\d+)\b'), (None, 'episode'))
]

# Quality detection patterns
QUALITY_PATTERNS = [
    (re.compile(r'\b(\d{3,4}[pi])\b', re.IGNORECASE), lambda m: m.group(1)),
    (re.compile(r'\b(4k|2160p)\b', re.IGNORECASE), lambda m: "4k"),
    (re.compile(r'\b(2k|1440p)\b', re.IGNORECASE), lambda m: "2k"),
    (re.compile(r'\b(HDRip|HDTV)\b', re.IGNORECASE), lambda m: m.group(1)),
    (re.compile(r'\b(4kX264|4kx265)\b', re.IGNORECASE), lambda m: m.group(1)),
    (re.compile(r'\[(\d{3,4}[pi])\]', re.IGNORECASE), lambda m: m.group(1))
]


def extract_season_episode(filename):
    """Extract season and episode numbers from filename."""
    for pattern, (season_group, episode_group) in SEASON_EPISODE_PATTERNS:
        match = pattern.search(filename)
        if match:
            season = match.group(1) if season_group else None
            episode = match.group(2) if episode_group else match.group(1)
            logger.info(f"Extracted season: {season}, episode: {episode} from {filename}")
            return season, episode
    logger.warning(f"No season/episode pattern matched for {filename}")
    return None, None


def extract_quality(filename):
    """Extract quality information from filename."""
    for pattern, extractor in QUALITY_PATTERNS:
        match = pattern.search(filename)
        if match:
            quality = extractor(match)
            logger.info(f"Extracted quality: {quality} from {filename}")
            return quality
    logger.warning(f"No quality pattern matched for {filename}")
    return "Unknown"


async def cleanup_files(*paths):
    """Safely remove files if they exist."""
    for path in paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.error(f"Error removing {path}: {e}")


async def process_thumbnail(thumb_path):
    """Process and resize thumbnail image."""
    if not thumb_path or not os.path.exists(thumb_path):
        return None
    try:
        with Image.open(thumb_path) as img:
            img = img.convert("RGB").resize((320, 320))
            img.save(thumb_path, "JPEG")
        return thumb_path
    except Exception as e:
        logger.error(f"Thumbnail processing failed: {e}")
        await cleanup_files(thumb_path)
        return None


async def add_metadata(input_path, output_path, user_id):
    """Add metadata to media file using ffmpeg."""
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found in PATH")

    metadata = {
        'title':       await anixlibrarybots.get_title(user_id),
        'artist':      await anixlibrarybots.get_artist(user_id),
        'author':      await anixlibrarybots.get_author(user_id),
        'video_title': await anixlibrarybots.get_video(user_id),
        'audio_title': await anixlibrarybots.get_audio(user_id),
        'subtitle':    await anixlibrarybots.get_subtitle(user_id)
    }

    cmd = [
        ffmpeg,
        '-i', input_path,
        '-metadata',     f'title={metadata["title"]}',
        '-metadata',     f'artist={metadata["artist"]}',
        '-metadata',     f'author={metadata["author"]}',
        '-metadata:s:v', f'title={metadata["video_title"]}',
        '-metadata:s:a', f'title={metadata["audio_title"]}',
        '-metadata:s:s', f'title={metadata["subtitle"]}',
        '-map', '0',
        '-c', 'copy',
        '-loglevel', 'error',
        output_path
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {stderr.decode()}")


@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def auto_rename_files(client, message):
    """Main handler for auto-renaming files."""
    user_id = message.from_user.id
    format_template = await anixlibrarybots.get_format_template(user_id)

    if not format_template:
        return await message.reply_text("Please set a rename format using /autorename")

    # Get file information
    if message.document:
        file_id   = message.document.file_id
        file_name = message.document.file_name
        file_size = message.document.file_size
        media_type = "document"
    elif message.video:
        file_id   = message.video.file_id
        file_name = message.video.file_name or "video"
        file_size = message.video.file_size
        media_type = "video"
    elif message.audio:
        file_id   = message.audio.file_id
        file_name = message.audio.file_name or "audio"
        file_size = message.audio.file_size
        media_type = "audio"
    else:
        return await message.reply_text("Unsupported file type")

    # FIX #3: check_anti_nsfw already replies — don't send a second message
    if await check_anti_nsfw(file_name, message):
        return

    # Prevent duplicate processing
    if file_id in renaming_operations:
        if (datetime.now() - renaming_operations[file_id]).seconds < 10:
            return
    renaming_operations[file_id] = datetime.now()

    # FIX #2: initialise all paths to None so finally block never hits NameError
    download_path = None
    metadata_path = None
    thumb_path    = None
    msg           = None

    try:
        # FIX #7: work on a local copy of the template — never mutate the DB value
        working_template = format_template

        season, episode = extract_season_episode(file_name)
        quality = extract_quality(file_name)

        replacements = {
            '{season}':  season or 'XX',
            '{episode}': episode or 'XX',
            '{quality}': quality,
            'Season':    season or 'XX',
            'Episode':   episode or 'XX',
            'QUALITY':   quality
        }
        for placeholder, value in replacements.items():
            working_template = working_template.replace(placeholder, value)

        ext = os.path.splitext(file_name)[1] or ('.mp4' if media_type == 'video' else '.mp3')
        new_filename  = f"{working_template}{ext}"
        download_path = f"downloads/{new_filename}"
        metadata_path = f"metadata/{new_filename}"

        os.makedirs(os.path.dirname(download_path), exist_ok=True)
        os.makedirs(os.path.dirname(metadata_path), exist_ok=True)

        # Download
        msg = await message.reply_text("**Downloading...**")
        try:
            file_path = await client.download_media(
                message,
                file_name=download_path,
                progress=progress_for_pyrogram,
                progress_args=("Downloading...", msg, time.time())
            )
        except Exception as e:
            logger.error(f"Download failed for user {user_id}: {e}")   # FIX #5
            await msg.edit("**Download failed. Please try again.**")
            return

        # FIX #4: only run FFmpeg if user has metadata enabled
        use_metadata = await anixlibrarybots.get_metadata(user_id)
        if use_metadata:
            await msg.edit("**Processing metadata...**")
            try:
                await add_metadata(file_path, metadata_path, user_id)
                file_path = metadata_path
            except Exception as e:
                logger.error(f"Metadata processing failed for user {user_id}: {e}")  # FIX #5
                await msg.edit("**Metadata processing failed. Uploading without metadata...**")
                # fall through and upload the unmodified download

        # Thumbnail
        thumb = await anixlibrarybots.get_thumbnail(user_id)
        if thumb and os.path.exists(thumb):
            thumb_path = thumb
        elif media_type == "video" and message.video.thumbs:
            thumb_path = await client.download_media(message.video.thumbs[0].file_id)
            thumb_path = await process_thumbnail(thumb_path)

        # FIX #8: respect the user's saved media preference for upload type
        saved_preference = await anixlibrarybots.get_media_preference(user_id)
        upload_type = saved_preference if saved_preference in {"document", "video", "audio"} else media_type

        caption = await anixlibrarybots.get_caption(user_id) or f"**{new_filename}**"

        await msg.edit("**Uploading...**")
        try:
            upload_params = {
                'chat_id':       message.chat.id,
                'caption':       caption,
                'thumb':         thumb_path,
                'progress':      progress_for_pyrogram,
                'progress_args': ("Uploading...", msg, time.time())
            }

            if upload_type == "document":
                await client.send_document(document=file_path, **upload_params)
            elif upload_type == "video":
                await client.send_video(video=file_path, **upload_params)
            elif upload_type == "audio":
                await client.send_audio(audio=file_path, **upload_params)

            await msg.delete()
        except Exception as e:
            logger.error(f"Upload failed for user {user_id}: {e}")     # FIX #5
            await msg.edit("**Upload failed. Please try again.**")

    except Exception as e:
        logger.error(f"Unexpected processing error for user {user_id}: {e}")  # FIX #5
        if msg:
            await msg.edit("**Something went wrong. Please try again.**")
        else:
            await message.reply_text("**Something went wrong. Please try again.**")
    finally:
        # FIX #2: safe — all paths initialised to None above
        await cleanup_files(download_path, metadata_path)
        # Only clean up auto-extracted video thumbs, never the user's saved thumbnail
        if thumb_path and thumb_path != thumb:
            await cleanup_files(thumb_path)
        renaming_operations.pop(file_id, None)
