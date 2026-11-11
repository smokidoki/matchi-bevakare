"""Kör: python -m pytest tests/  (eller python tests/test_bevakare.py)"""
import json, sys, tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matchi_bevakare as mb

CFG = {"sport": 5, "facilities": ["testhallen"], "weekdays": [0, 1, 2, 3, 4],
       "window_start": "17:00", "window_end": "19:00", "days_ahead": 7,
       "request_delay_seconds": 0}

def html_for(free_times):
    cells = "".join(
        f'<td class="slot free" title="Ledig&lt;br&gt;Bana {c}&lt;br&gt;{t}"></td>' for c, t in free_times)
    return f'<table><tr><th>Bana</th>{cells}<td class="slot booked" title="Bokad&lt;br&gt;Bana 9&lt;br&gt;17:00 - 18:00"></td></tr></table>'

def test_parse_and_window():
    monday = date(2026, 11, 16)
    page = html_for([(1, "16:00 - 17:00"), (1, "17:00 - 18:00"), (2, "18:30 - 19:30"), (3, "19:00 - 20:00")])
    slots = mb.parse_schedule(page, "42", "Testhallen", monday.isoformat())
    assert [(s.court, s.start) for s in slots] == [("Bana 1", "16:00"), ("Bana 1", "17:00"), ("Bana 2", "18:30"), ("Bana 3", "19:00")]
    ok = [s for s in slots if mb.in_window(s, CFG)]
    assert [(s.court, s.start) for s in ok] == [("Bana 1", "17:00"), ("Bana 2", "18:30")]
    saturday = mb.Slot("42", "T", (monday + timedelta(days=5)).isoformat(), "17:00", "18:00", "Bana 1")
    assert not mb.in_window(saturday, CFG)

def test_only_new_slots_notified(monkeypatch=None):
    sent = []
    pages = {"free": [(1, "17:00 - 18:00")]}
    mb.resolve_facility = lambda e: ("42", "Testhallen", "https://x")
    mb.fetch = lambda path, params=None, debug_name=None: html_for(pages["free"])
    mb.notify = lambda topic, server, title, msg, click, dry: sent.append((title, msg))
    with tempfile.TemporaryDirectory() as d:
        st = Path(d) / "state.json"
        mb.run_once(CFG, st, dry_run=False)
        first = len(sent)
        assert first == 1 and "17:00" in sent[0][1]
        mb.run_once(CFG, st, dry_run=False)          # samma tider -> ingen ny notis
        assert len(sent) == first
        pages["free"] = [(1, "17:00 - 18:00"), (4, "18:00 - 19:00")]
        mb.run_once(CFG, st, dry_run=False)          # ny tid släpps -> notis
        assert len(sent) == first + 1 and "Bana 4" in sent[-1][1] and "Bana 1" not in sent[-1][1]
        pages["free"] = []
        mb.run_once(CFG, st, dry_run=False)          # bokas bort
        pages["free"] = [(4, "18:00 - 19:00")]
        mb.run_once(CFG, st, dry_run=False)          # avbokas igen -> ny notis
        assert len(sent) == first + 2
        assert json.loads(st.read_text())["facilities"]["testhallen"][0] == "42"

if __name__ == "__main__":
    test_parse_and_window(); test_only_new_slots_notified(); print("Alla tester OK")
