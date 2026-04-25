import re
import logging
from config import Config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Users who bypass the NSFW filter entirely
# Pulls ADMIN and OWNER_ID from Config — add more IDs to the set if needed
# ---------------------------------------------------------------------------
def _get_privileged_ids() -> set[int]:
    privileged = set()
    if Config.ADMIN:
        # ADMIN may be a single int or a list of ints
        if isinstance(Config.ADMIN, (list, tuple)):
            privileged.update(int(i) for i in Config.ADMIN)
        else:
            privileged.add(int(Config.ADMIN))
    if hasattr(Config, "OWNER_ID") and Config.OWNER_ID:
        privileged.add(int(Config.OWNER_ID))
    return privileged

# ---------------------------------------------------------------------------
# Keyword lists — duplicates removed across categories (FIX #2)
# "adult", "culture", "cultured" removed — too many false positives (FIX #5)
# ---------------------------------------------------------------------------
nsfw_keywords = {
    "general": [
        "porn", "sex", "nude", "naked", "boobs", "tits", "pussy", "dick", "cock",
        "fuck", "blowjob", "cum", "orgasm", "shemale", "erotic", "masturbate", "anal",
        "hardcore", "bdsm", "fetish", "lingerie", "xxx", "milf", "gay", "lesbian",
        "threesome", "squirting", "butt plug", "dildo", "vibrator", "escort", "handjob",
        "striptease", "kinky", "pornstar", "sex tape", "spank", "swinger", "taboo",
        "cumshot", "deepthroat", "domination", "submission", "handcuffs", "orgy",
        "roleplay", "sex toy", "voyeur", "pornhwa", "netorare", "netori", "netorase",
        "eromanga", "incest", "stepmom", "stepdad", "stepsister", "stepbrother",
        "stepson", "stepdaughter", "ntr", "gangbang", "facial", "golden shower",
        "pegging", "rimming", "rough sex", "dirty talk", "sex chat", "nude pic",
        "lewd", "titty", "twerk", "breasts", "penis", "vagina", "clitoris", "genitals",
        "sexual", "kamasutra", "pedo", "rape", "bondage", "cum inside", "creampie",
        "sex slave", "sex doll", "sex machine", "latex", "oral sex", "slut", "whore",
        "tramp", "skank", "cumdumpster", "ecchi", "doujin", "hentai", "smut",
        "futanari", "tentacle"
    ],
    "hentai": [
        "doujinshi", "yaoi", "shota", "loli", "bishoujo", "bishounen", "mecha hentai",
        "hentai manga", "hentai anime", "eroge", "visual novel", "h-manga", "h-anime",
        "adult manga", "18+ anime", "18+ manga", "lewd anime", "lewd manga",
        "animated porn", "animated sex", "hentai game", "hentai art", "hentai drawing",
        "hentai doujin", "yaoi hentai", "hentai comic", "hentai picture", "hentai scene",
        "hentai story", "hentai video", "hentai movie", "hentai episode", "hentai series"
    ],
    "abbreviations": [
        "pr0n", "s3x", "n00d", "fck", "bj", "hj", "p0rn", "h3ntai", "h-ntai",
        "pnwh", "p0rnhwa", "l3wd", "s3xual"
    ]
}

# ---------------------------------------------------------------------------
# Exception keywords — these words make a keyword match ignored
# e.g. "assassination" contains "ass" but should be allowed
# FIX #3: exceptions are now tied to specific triggering keywords, not the
# whole filename — a file must contain BOTH the exception word AND the nsfw
# keyword for the exception to apply. Implemented by checking the exception
# words suppress only the short substrings they are known to contain.
# ---------------------------------------------------------------------------
# Map: exception_word -> the nsfw substring it neutralises
EXCEPTION_MAP = {
    "assassination": {"ass"},
    "classroom":     {"ass"},
    "nxivm":         {"xxx"},
    "geass":         {"ass"},
    "harass":        {"ass"},
    "harassment":    {"ass"},
    "passage":       {"ass"},
    "bass":          {"ass"},
    "mass":          {"ass"},
    "class":         {"ass"},
    "compass":       {"ass"},
}

# ---------------------------------------------------------------------------
# Build a flat deduplicated set and a single compiled regex (FIX #1, #6)
# Sort by length descending so longer phrases match before their substrings
# ---------------------------------------------------------------------------
_flat_keywords: set[str] = set()
for _kws in nsfw_keywords.values():
    _flat_keywords.update(kw.lower() for kw in _kws)

_sorted_keywords = sorted(_flat_keywords, key=len, reverse=True)
_NSFW_PATTERN = re.compile(
    r'(' + '|'.join(re.escape(kw) for kw in _sorted_keywords) + r')',
    re.IGNORECASE
)


def _get_active_exceptions(lower_name: str) -> set[str]:
    """Return the set of nsfw substrings neutralised by exception words present in the filename."""
    neutralised: set[str] = set()
    for exc_word, suppressed in EXCEPTION_MAP.items():
        if exc_word in lower_name:
            neutralised.update(suppressed)
    return neutralised


async def check_anti_nsfw(new_name: str, message) -> bool:
    """
    Returns True (and replies to the message) if the filename contains NSFW content.
    Returns False if the filename is clean, covered by an exception, or sent by admin/owner.
    """
    # Admin and owner bypass the filter entirely
    user_id = message.from_user.id if message.from_user else None
    if user_id and user_id in _get_privileged_ids():
        logger.info(f"NSFW filter bypassed by privileged user {user_id} for filename: {new_name}")
        return False

    lower_name = new_name.lower()
    neutralised = _get_active_exceptions(lower_name)   # FIX #3

    match = _NSFW_PATTERN.search(lower_name)           # FIX #1: single regex pass
    if match:
        matched_keyword = match.group(1)
        if matched_keyword in neutralised:             # FIX #3: exception suppresses this specific hit
            return False
        logger.info(f"NSFW keyword '{matched_keyword}' blocked in filename: {new_name}")  # FIX #4
        await message.reply_text(
            "⚠️ You can't rename files with NSFW content."
        )
        return True

    return False
