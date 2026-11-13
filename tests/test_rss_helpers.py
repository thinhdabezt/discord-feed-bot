from app.sources.rss import parse_published


def test_parse_published_missing():
    class Entry(dict):
        pass

    assert parse_published(Entry()) is None
