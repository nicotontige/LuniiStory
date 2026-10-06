"""Store client.

A store is just a URL serving either a Telmi JSON catalog or a podcast RSS feed.
Both are reduced here to the same list of :class:`StoreStory`.
"""

import hashlib
import json
import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

import requests

from luniistory import config

USER_AGENT = "luniiStory/0.1"
TIMEOUT = 30
RECENT_DELTA = 15 * 24 * 3600  # a story stays "new" for 15 days, as in Telmi Sync

ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


@dataclass
class StoreStory:
    title: str
    download: str
    age: int = 0
    category: str = ""
    description: str = ""
    image: str = ""
    author: str = ""
    publisher: str = ""
    license: str = ""
    awards: list = field(default_factory=list)
    uuid: str = ""
    version: int = 0
    download_count: int = 0
    created_at: str = ""
    updated_at: str = ""
    store_name: str = ""

    @property
    def key(self):
        """Local cache key.

        Catalogs sometimes advertise a made-up UUID ("ffffff-190…") or a shared
        template, and RSS feeds carry none at all. The download URL, on the
        other hand, is always there and changes with every release.
        """
        return hashlib.sha1(self.download.encode("utf-8")).hexdigest()

    @property
    def story_uuid(self):
        """UUID advertised by the catalog, when it really is one.

        Used to spot a story already on the Lunii, bearing in mind that the
        authoritative UUID remains the one in the pack's ``metadata.json``.
        """
        try:
            return str(UUID(str(self.uuid))).upper()
        except (ValueError, AttributeError, TypeError):
            return ""

    @property
    def is_new(self):
        return _is_recent(self.created_at)

    @property
    def is_updated(self):
        return _is_recent(self.updated_at)

    @property
    def is_awarded(self):
        return "PARFAIT" in self.awards


def _is_recent(stamp):
    parsed = _parse_date(stamp)
    if parsed is None:
        return False
    return (datetime.now(timezone.utc) - parsed).total_seconds() < RECENT_DELTA


def _parse_date(stamp):
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime

            parsed = parsedate_to_datetime(str(stamp))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _strip_html(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _thumb(entry):
    thumbs = entry.get("thumbs")
    if isinstance(thumbs, dict):
        return thumbs.get("medium") or thumbs.get("small") or ""
    return entry.get("smallThumbUrl") or entry.get("image") or ""


def fetch(store, session=None):
    """Downloads and normalises a store's catalog."""
    session = session or requests.Session()
    response = session.get(store["url"], headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    response.raise_for_status()

    body = response.content
    try:
        return _parse_json(json.loads(body), store["name"])
    except ValueError:
        return _parse_rss(body, store["name"])


def _parse_json(payload, store_name):
    entries = payload.get("data") if isinstance(payload, dict) else payload
    stories = []
    for entry in entries or []:
        download = entry.get("download") or entry.get("downloadUrl")
        if not download:
            continue
        stories.append(StoreStory(
            title=entry.get("title") or "",
            download=download,
            age=entry.get("age") or 0,
            category=entry.get("category") or "",
            description=entry.get("description") or "",
            image=_thumb(entry),
            author=entry.get("author") or "",
            publisher=entry.get("publisher") or "",
            license=entry.get("license") or "",
            awards=entry.get("awards") or [],
            uuid=entry.get("uuid") or "",
            version=entry.get("version") or 0,
            download_count=entry.get("download_count") or 0,
            created_at=entry.get("created_at") or "",
            updated_at=entry.get("updated_at") or "",
            store_name=store_name,
        ))
    return stories


def _parse_rss(body, store_name):
    """Podcast feed: every episode becomes a single-track story."""
    channel = ElementTree.fromstring(body).find("channel")
    if channel is None:
        raise ValueError("Ni catalogue JSON ni flux RSS exploitable")

    def text(node, tag, default=""):
        found = node.find(tag) if node is not None else None
        return (found.text or default) if found is not None else default

    copyright_ = text(channel, "copyright")
    channel_image = text(channel.find("image"), "url") if channel.find("image") is not None else ""
    if not channel_image:
        itunes_image = channel.find(f"{ITUNES}image")
        channel_image = itunes_image.get("href", "") if itunes_image is not None else ""

    stories = []
    for item in channel.findall("item"):
        if text(item, f"{ITUNES}episodeType") == "trailer":
            continue
        enclosure = next(
            (e for e in item.findall("enclosure") if (e.get("type") or "").startswith("audio/")),
            None,
        )
        if enclosure is None:
            continue
        item_image = item.find(f"{ITUNES}image")
        published = text(item, "pubDate")
        stories.append(StoreStory(
            title=text(item, "title"),
            download=enclosure.get("url"),
            category=text(item, "category"),
            description=_strip_html(text(item, "description")),
            image=(item_image.get("href") if item_image is not None else "") or channel_image,
            author=text(item, f"{ITUNES}author") or copyright_,
            publisher=copyright_,
            license=copyright_,
            created_at=published,
            updated_at=published,
            store_name=store_name,
        ))
    return stories


def fetch_all(stores=None, session=None, on_error=None):
    """Catalog of every store merged, one broken store stopping nothing."""
    session = session or requests.Session()
    stories = []
    for store in stores if stores is not None else config.load_stores():
        try:
            stories.extend(fetch(store, session=session))
        except Exception as error:  # network, broken JSON, invalid XML…
            if on_error:
                on_error(store, error)
    return stories


def cached_thumbnail(story, session=None):
    """Downloads a story's thumbnail and returns its path in the cache."""
    if not story.image:
        return None
    config.ensure_dirs()
    suffix = ".png" if story.image.lower().endswith(".png") else ".jpg"
    target = config.CACHE_DIR / (hashlib.sha1(story.image.encode("utf-8")).hexdigest() + suffix)
    if target.exists():
        return target
    try:
        session = session or requests.Session()
        response = session.get(story.image, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        response.raise_for_status()
        target.write_bytes(response.content)
        return target
    except Exception:
        return None
