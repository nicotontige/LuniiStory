"""Browsable directory of podcast feeds.

Telmi Sync publishes a list of kid-friendly podcast feeds so a store can be
added without hunting for its address. Each entry becomes an ordinary store:
its RSS feed is a catalog like any other, one episode per story.
"""

import hashlib
import json
from dataclasses import dataclass, field

import requests

from luniistory import config
from luniistory.stores import TIMEOUT, USER_AGENT

DIRECTORY_URL = (
    "https://gist.githubusercontent.com/DantSu/"
    "75dfd354b587e7e353302834967e48bc/raw/rss-feed.json"
)
CACHE_NAME = "feed-directory.json"


@dataclass
class Feed:
    title: str
    url: str
    publisher: str = ""
    description: str = ""
    image: str = ""
    website: str = ""
    has_ads: bool = False

    @property
    def key(self):
        return hashlib.sha1(self.url.encode("utf-8")).hexdigest()


@dataclass
class Directory:
    """The whole list, kept flat.

    The published file groups entries under copyright strings, which makes for
    inconsistent headings and 99 distinct publishers across 174 feeds. A flat
    list with a search box reads better than either grouping.
    """

    feeds: list = field(default_factory=list)

    def search(self, needle):
        if not needle:
            return list(self.feeds)
        needle = needle.casefold()
        return [
            feed for feed in self.feeds
            if needle in f"{feed.title} {feed.publisher} {feed.description}".casefold()
        ]


def parse(payload):
    """Turns the published mapping of publisher → entries into flat feeds."""
    feeds = []
    for publisher, entries in (payload or {}).items():
        for entry in entries or []:
            url = (entry.get("rssFeed") or "").strip()
            if not url:
                continue
            feeds.append(Feed(
                title=entry.get("title") or url,
                url=url,
                publisher=entry.get("category") or publisher,
                description=(entry.get("description") or "").strip(),
                image=entry.get("image") or "",
                website=entry.get("link") or "",
                has_ads=bool(entry.get("ads")),
            ))
    return Directory(sorted(feeds, key=lambda feed: feed.title.casefold()))


def fetch(session=None, use_cache=True):
    """Downloads the directory, falling back to the last copy on failure.

    The list is published by a third party; a network hiccup should not empty
    the window when a perfectly good copy is already on disk.
    """
    config.ensure_dirs()
    cache = config.CACHE_DIR / CACHE_NAME

    try:
        session = session or requests.Session()
        response = session.get(DIRECTORY_URL, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        cache.write_text(json.dumps(payload, ensure_ascii=False), "utf-8")
        return parse(payload)
    except Exception:
        if use_cache and cache.exists():
            try:
                return parse(json.loads(cache.read_text("utf-8")))
            except (ValueError, OSError):
                pass
        raise
