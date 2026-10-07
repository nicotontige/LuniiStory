"""The published feed directory, and what we make of it."""

from luniistory import directory

PAYLOAD = {
    "Radio France": [
        {
            "title": "Une histoire et Oli",
            "category": "France Inter",
            "link": "https://example.org/oli",
            "rssFeed": "https://example.org/oli.xml",
            "image": "https://example.org/oli.jpg",
            "ads": False,
            "description": "  Des contes pour enfants.\nSecond line.  ",
        },
        # No feed address: nothing to add as a store, so it is dropped.
        {"title": "Broken", "category": "France Inter", "rssFeed": ""},
    ],
    "Autres sources": [
        {
            "title": "Abricot Présente",
            "category": "Abricot",
            "rssFeed": "https://example.org/abricot.xml",
            "ads": True,
        },
    ],
}


def test_entries_become_feeds():
    parsed = directory.parse(PAYLOAD)
    assert len(parsed.feeds) == 2

    oli = next(feed for feed in parsed.feeds if feed.title == "Une histoire et Oli")
    assert oli.url == "https://example.org/oli.xml"
    assert oli.publisher == "France Inter"      # the entry's own label, not the group
    assert oli.website == "https://example.org/oli"
    assert oli.has_ads is False


def test_feeds_are_sorted_by_title():
    assert [feed.title for feed in directory.parse(PAYLOAD).feeds] == [
        "Abricot Présente",
        "Une histoire et Oli",
    ]


def test_advertising_is_carried_through():
    feeds = {feed.title: feed for feed in directory.parse(PAYLOAD).feeds}
    assert feeds["Abricot Présente"].has_ads is True


def test_search_covers_title_publisher_and_description():
    parsed = directory.parse(PAYLOAD)
    assert len(parsed.search("")) == 2
    assert [feed.title for feed in parsed.search("oli")] == ["Une histoire et Oli"]
    assert [feed.title for feed in parsed.search("inter")] == ["Une histoire et Oli"]
    assert [feed.title for feed in parsed.search("contes")] == ["Une histoire et Oli"]
    assert parsed.search("nothing here") == []


def test_keys_are_stable_and_distinct():
    first = directory.parse(PAYLOAD).feeds
    second = directory.parse(PAYLOAD).feeds
    assert [feed.key for feed in first] == [feed.key for feed in second]
    assert len({feed.key for feed in first}) == len(first)


def test_empty_payload_is_not_an_error():
    assert directory.parse({}).feeds == []
    assert directory.parse(None).feeds == []
