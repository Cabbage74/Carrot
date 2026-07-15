from carrot import tui


def test_relative_time_buckets():
    now = 1_000_000.0
    assert tui._relative_time(now - 5, now) == "just now"
    assert tui._relative_time(now - 120, now) == "2m ago"
    assert tui._relative_time(now - 3 * 3600, now) == "3h ago"
    assert tui._relative_time(now - 2 * 86400, now) == "2d ago"
    # a clock skew where the session looks "in the future" clamps, never negative
    assert tui._relative_time(now + 100, now) == "just now"


def test_truncate_collapses_newlines_and_caps_width():
    assert tui._truncate("hello") == "hello"
    assert tui._truncate("line1\nline2") == "line1 line2"
    long = "x" * 100
    out = tui._truncate(long, 10)
    assert len(out) == 10 and out.endswith("…")


def test_truncate_handles_wide_characters():
    # CJK text passes through unchanged when under the width cap
    assert tui._truncate("一二三四五六") == "一二三四五六"
