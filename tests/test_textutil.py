from nf_diagnose_mcp import textutil as t


def test_parse_memory():
    assert t.parse_memory("9.9 MB") == int(9.9 * 1024**2)
    assert t.parse_memory("400 B") == 400
    assert t.parse_memory("19.8 GB") == int(19.8 * 1024**3)
    assert t.parse_memory("4294967296") == 4294967296
    assert t.parse_memory("-") is None and t.parse_memory("") is None and t.parse_memory("n/a") is None


def test_parse_duration():
    assert t.parse_duration("380ms") == 380
    assert t.parse_duration("2.4s") == 2400
    assert t.parse_duration("1m 5s") == 65_000
    assert t.parse_duration("1h 2m 3s") == 3_723_000
    assert t.parse_duration("1d 2h") == 93_600_000
    assert t.parse_duration("3600000") == 3_600_000
    assert t.parse_duration("-") is None and t.parse_duration("soon") is None


def test_format_roundtrip_is_readable():
    assert t.fmt_bytes(4 * 1024**3) == "4.0 GB"
    assert t.fmt_bytes(None) == "-"
    assert t.fmt_ms(3_600_000) == "1h00m"
    assert t.fmt_ms(11_000) == "11.0s"


def test_clip_and_cap_say_what_was_removed():
    assert t.clip_line("x" * 500).endswith("…[+200 chars]")
    clipped = t.clip_lines([str(i) for i in range(100)], head=2, tail=3)
    assert clipped == ["0", "1", "…[95 lines omitted]", "97", "98", "99"]
    capped = t.cap("y" * 1000, 200, "narrow it")
    assert len(capped) <= 200 and "output truncated at 200 chars; narrow it" in capped
    assert t.cap("short", 200) == "short"


def test_strip_ansi():
    assert t.strip_ansi("\x1b[0;35m  nf-core/demo 1.2.0\x1b[0m") == "  nf-core/demo 1.2.0"
