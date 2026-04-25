import motor.motor_asyncio
import datetime
import logging
from config import Config
from .utils import send_log


class Database:
    def __init__(self, uri, database_name):
        try:
            self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
            logging.info("MongoDB client initialized (connection verified on first use)")
        except Exception as e:
            logging.error(f"Failed to initialize MongoDB client: {e}")
            raise e
        self.anixlibrarybots = self._client[database_name]
        self.col = self.anixlibrarybots.user

    def new_user(self, id):
        return dict(
            _id=int(id),
            join_date=datetime.date.today().isoformat(),
            file_id=None,
            caption=None,
            metadata=False,                                        # FIX #6: was True (bool), now False (bool) — consistent with get_metadata default
            metadata_code=Config.DEFAULT_METADATA_CODE,            # FIX #7: moved to config
            format_template=None,
            ban_status=dict(
                is_banned=False,
                ban_duration=0,
                banned_on=datetime.date.max.isoformat(),
                ban_reason=''
            )
        )

    async def add_user(self, b, m):
        u = m.from_user
        if not await self.is_user_exist(u.id):
            user = self.new_user(u.id)
            try:
                await self.col.insert_one(user)
                await send_log(b, u)
            except Exception as e:
                logging.error(f"Error adding user {u.id}: {e}")

    async def is_user_exist(self, id):
        try:
            user = await self.col.find_one({"_id": int(id)})
            return bool(user)
        except Exception as e:
            logging.error(f"Error checking if user {id} exists: {e}")
            return False

    async def total_users_count(self):
        try:
            count = await self.col.count_documents({})
            return count
        except Exception as e:
            logging.error(f"Error counting users: {e}")
            return 0

    async def get_all_users(self):
        try:
            return self.col.find({})
        except Exception as e:
            logging.error(f"Error getting all users: {e}")
            return None

    async def delete_user(self, user_id):
        try:
            await self.col.delete_one({"_id": int(user_id)})  # FIX #5: was delete_many
        except Exception as e:
            logging.error(f"Error deleting user {user_id}: {e}")

    # ── Helper: fetch full user document once (FIX #3) ──────────────────────
    async def get_user(self, user_id):
        try:
            return await self.col.find_one({"_id": int(user_id)})
        except Exception as e:
            logging.error(f"Error fetching user {user_id}: {e}")
            return None

    # ── Thumbnail ────────────────────────────────────────────────────────────
    async def set_thumbnail(self, id, file_id):
        try:
            await self.col.update_one({"_id": int(id)}, {"$set": {"file_id": file_id}})
        except Exception as e:
            logging.error(f"Error setting thumbnail for user {id}: {e}")

    async def get_thumbnail(self, id):
        try:
            user = await self.get_user(id)
            return user.get("file_id", None) if user else None
        except Exception as e:
            logging.error(f"Error getting thumbnail for user {id}: {e}")
            return None

    # ── Caption ──────────────────────────────────────────────────────────────
    async def set_caption(self, id, caption):
        try:
            await self.col.update_one({"_id": int(id)}, {"$set": {"caption": caption}})
        except Exception as e:
            logging.error(f"Error setting caption for user {id}: {e}")

    async def get_caption(self, id):
        try:
            user = await self.get_user(id)
            return user.get("caption", None) if user else None
        except Exception as e:
            logging.error(f"Error getting caption for user {id}: {e}")
            return None

    # ── Format Template ──────────────────────────────────────────────────────
    async def set_format_template(self, id, format_template):
        try:
            await self.col.update_one(
                {"_id": int(id)}, {"$set": {"format_template": format_template}}
            )
        except Exception as e:
            logging.error(f"Error setting format template for user {id}: {e}")

    async def get_format_template(self, id):
        try:
            user = await self.get_user(id)
            return user.get("format_template", None) if user else None
        except Exception as e:
            logging.error(f"Error getting format template for user {id}: {e}")
            return None

    # ── Media Preference ─────────────────────────────────────────────────────
    async def set_media_preference(self, id, media_type):
        try:
            await self.col.update_one(
                {"_id": int(id)}, {"$set": {"media_type": media_type}}
            )
        except Exception as e:
            logging.error(f"Error setting media preference for user {id}: {e}")

    async def get_media_preference(self, id):
        try:
            user = await self.get_user(id)
            return user.get("media_type", None) if user else None
        except Exception as e:
            logging.error(f"Error getting media preference for user {id}: {e}")
            return None

    # ── Metadata ─────────────────────────────────────────────────────────────
    async def get_metadata(self, user_id):
        try:                                                        # FIX #2: added try/except + None guard
            user = await self.get_user(user_id)
            return user.get("metadata", False) if user else False  # FIX #6: False (bool) not "Off" (str)
        except Exception as e:
            logging.error(f"Error getting metadata for user {user_id}: {e}")
            return False

    async def set_metadata(self, user_id, metadata):
        try:
            await self.col.update_one({"_id": int(user_id)}, {"$set": {"metadata": metadata}})
        except Exception as e:
            logging.error(f"Error setting metadata for user {user_id}: {e}")

    # ── Title ────────────────────────────────────────────────────────────────
    async def get_title(self, user_id):
        try:                                                        # FIX #2
            user = await self.get_user(user_id)
            return user.get("title", Config.DEFAULT_TITLE) if user else Config.DEFAULT_TITLE  # FIX #7
        except Exception as e:
            logging.error(f"Error getting title for user {user_id}: {e}")
            return Config.DEFAULT_TITLE

    async def set_title(self, user_id, title):
        try:
            await self.col.update_one({"_id": int(user_id)}, {"$set": {"title": title}})
        except Exception as e:
            logging.error(f"Error setting title for user {user_id}: {e}")

    # ── Author ───────────────────────────────────────────────────────────────
    async def get_author(self, user_id):
        try:                                                        # FIX #2
            user = await self.get_user(user_id)
            return user.get("author", Config.DEFAULT_AUTHOR) if user else Config.DEFAULT_AUTHOR  # FIX #7
        except Exception as e:
            logging.error(f"Error getting author for user {user_id}: {e}")
            return Config.DEFAULT_AUTHOR

    async def set_author(self, user_id, author):
        try:
            await self.col.update_one({"_id": int(user_id)}, {"$set": {"author": author}})
        except Exception as e:
            logging.error(f"Error setting author for user {user_id}: {e}")

    # ── Artist ───────────────────────────────────────────────────────────────
    async def get_artist(self, user_id):
        try:                                                        # FIX #2
            user = await self.get_user(user_id)
            return user.get("artist", Config.DEFAULT_ARTIST) if user else Config.DEFAULT_ARTIST  # FIX #7
        except Exception as e:
            logging.error(f"Error getting artist for user {user_id}: {e}")
            return Config.DEFAULT_ARTIST

    async def set_artist(self, user_id, artist):
        try:
            await self.col.update_one({"_id": int(user_id)}, {"$set": {"artist": artist}})
        except Exception as e:
            logging.error(f"Error setting artist for user {user_id}: {e}")

    # ── Audio ────────────────────────────────────────────────────────────────
    async def get_audio(self, user_id):
        try:                                                        # FIX #2
            user = await self.get_user(user_id)
            return user.get("audio", Config.DEFAULT_AUDIO) if user else Config.DEFAULT_AUDIO  # FIX #7
        except Exception as e:
            logging.error(f"Error getting audio for user {user_id}: {e}")
            return Config.DEFAULT_AUDIO

    async def set_audio(self, user_id, audio):
        try:
            await self.col.update_one({"_id": int(user_id)}, {"$set": {"audio": audio}})
        except Exception as e:
            logging.error(f"Error setting audio for user {user_id}: {e}")

    # ── Subtitle ─────────────────────────────────────────────────────────────
    async def get_subtitle(self, user_id):
        try:                                                        # FIX #2
            user = await self.get_user(user_id)
            return user.get("subtitle", Config.DEFAULT_SUBTITLE) if user else Config.DEFAULT_SUBTITLE  # FIX #7
        except Exception as e:
            logging.error(f"Error getting subtitle for user {user_id}: {e}")
            return Config.DEFAULT_SUBTITLE

    async def set_subtitle(self, user_id, subtitle):
        try:
            await self.col.update_one({"_id": int(user_id)}, {"$set": {"subtitle": subtitle}})
        except Exception as e:
            logging.error(f"Error setting subtitle for user {user_id}: {e}")

    # ── Video ────────────────────────────────────────────────────────────────
    async def get_video(self, user_id):
        try:                                                        # FIX #2
            user = await self.get_user(user_id)
            return user.get("video", Config.DEFAULT_VIDEO) if user else Config.DEFAULT_VIDEO  # FIX #7
        except Exception as e:
            logging.error(f"Error getting video for user {user_id}: {e}")
            return Config.DEFAULT_VIDEO

    async def set_video(self, user_id, video):
        try:
            await self.col.update_one({"_id": int(user_id)}, {"$set": {"video": video}})
        except Exception as e:
            logging.error(f"Error setting video for user {user_id}: {e}")


anixlibrarybots = Database(Config.DB_URL, Config.DB_NAME)
