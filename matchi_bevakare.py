#!/usr/bin/env python3
"""MATCHi-bevakare: skickar en push-notis (via ntfy) när lediga tider släpps.

Användning:
    python matchi_bevakare.py                 # en körning (används av GitHub Actions)
    python matchi_bevakare.py --loop 300      # kör var 5:e minut (egen dator/Raspberry Pi)
    python matchi_bevakare.py --discover Stockholm   # lista anläggningar att lägga i config.json
    python matchi_bevakare.py --dry-run       # visa vad som skulle notifieras, skicka inget
    python matchi_bevakare.py --debug         # spara rå HTML i debug/ för felsökning

Notiser skickas till ntfy-ämnet i miljövariabeln NTFY_TOPIC (eller "ntfy_topic" i config.json).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE = "https://www.matchi.se"
TZ = ZoneInfo("Europe/Stockholm")
HERE = Path(__file__).resolve().parent
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}
TIME_RANGE = re.compile(r"(\d{1,2})[:.](\d{2})\s*[-–]\s*(\d{1,2})[:.](\d{2})")
NOISE_WORDS = {"ledig", "ledigt", "free", "available", "boka", "book"}

session = requests.Session()
session.headers.update(HEADERS)
DEBUG = False


@dataclass(frozen=True)
class Slot:
    facility_id: str
    facility_name: str
    day: str  # YYYY-MM-DD
    start: str  # HH:MM
    end: str
    court: str

    @property
    def key(self) -> str:
        return f"{self.facility_id}|{self.day}|{self.start}|{self.court}"


# --------------------------------------------------------------------------- HTTP

def fetch(path: str, params: dict | None = None, debug_name: str | None = None) -> str:
    resp = session.get(BASE + path, params=params, timeout=20)
    resp.raise_for_status()
    if DEBUG and debug_name:
        out = HERE / "debug"
        out.mkdir(exist_ok=True)
        (out / f"{debug_name}.html").write_text(resp.text, encoding="utf-8")
    return resp.text


# --------------------------------------------------------------------------- Anläggningar

def resolve_facility(entry: str) -> tuple[str, str, str]:
    """Tar en slug (t.ex. 'padelcenter-stockholm') eller ett numeriskt id.

    Returnerar (facility_id, namn, länk till bokningssidan)."""
    if entry.isdigit():
        return entry, f"Anläggning {entry}", f"{BASE}/book/schedule?facilityId={entry}"
    page = fetch(f"/facilities/{entry}", debug_name=f"facility_{entry}")
    m = re.search(r"facilityId[\"']?\s*[=:]\s*[\"']?(\d+)", page)
    if not m:
        raise RuntimeError(f"Hittade inget facilityId på /facilities/{entry}")
    soup = BeautifulSoup(page, "html.parser")
    name_el = soup.find("h1") or soup.find("title")
    name = name_el.get_text(" ", strip=True) if name_el else entry
    name = re.sub(r"\s*[|–-]\s*MATCHi.*$", "", name, flags=re.I).strip() or entry
    return m.group(1), name, f"{BASE}/facilities/{entry}"


def discover(query: str, sport: int) -> list[tuple[str, str]]:
    page = fetch("/book/findFacilities", {"q": query, "sport": sport}, debug_name="discover")
    soup = BeautifulSoup(page, "html.parser")
    found: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        m = re.match(r"^(?:https?://www\.matchi\.se)?/facilities/([\w-]+)/?(?:\?.*)?$", a["href"])
        if m and m.group(1) not in found:
            text = a.get_text(" ", strip=True)
            found[m.group(1)] = text or m.group(1)
    return sorted(found.items())


# --------------------------------------------------------------------------- Schema

def parse_schedule(page: str, facility_id: str, facility_name: str, day: str) -> list[Slot]:
    """Plockar ut lediga tider ur MATCHi:s schema-HTML.

    Lediga celler har klasserna 'slot free' och ett title-attribut i stil med
    'Ledig<br>Bana 3<br>17:00 - 18:00'."""
    soup = BeautifulSoup(page, "html.parser")
    cells = soup.select(".slot.free") or [
        el for el in soup.find_all(class_=re.compile(r"\bfree\b")) if el.get("title")
    ]
    slots = []
    for cell in cells:
        raw = cell.get("title") or cell.get("data-original-title") or cell.get_text(" ")
        text = html.unescape(raw)
        parts = [BeautifulSoup(p, "html.parser").get_text(" ", strip=True)
                 for p in re.split(r"<br\s*/?>|\n", text)]
        m = TIME_RANGE.search(text)
        if not m:
            continue
        start = f"{int(m.group(1)):02d}:{m.group(2)}"
        end = f"{int(m.group(3)):02d}:{m.group(4)}"
        court = next(
            (p for p in parts if p and not TIME_RANGE.search(p) and p.lower() not in NOISE_WORDS),
            "",
        )
        if not court:  # fallback: radens rubrik (banans namn)
            row = cell.find_parent("tr")
            head = row.find(["th", "td"]) if row else None
            court = head.get_text(" ", strip=True) if head and head is not cell else "Bana ?"
        slots.append(Slot(facility_id, facility_name, day, start, end, court))
    return slots


def to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def in_window(slot: Slot, cfg: dict) -> bool:
    d = date.fromisoformat(slot.day)
    if d.weekday() not in cfg["weekdays"]:
        return False
    s = to_minutes(slot.start)
    if not (to_minutes(cfg["window_start"]) <= s < to_minutes(cfg["window_end"])):
        return False
    if cfg.get("require_end_within_window") and to_minutes(slot.end) > to_minutes(cfg["window_end"]):
        return False
    return True


def days_to_check(cfg: dict) -> list[date]:
    now = datetime.now(TZ)
    today = now.date()
    out = []
    for i in range(cfg["days_ahead"] + 1):
        d = today + timedelta(days=i)
        if d.weekday() in cfg["weekdays"]:
            # Hoppa över dagens datum om fönstret redan passerat
            if i == 0 and now.hour * 60 + now.minute >= to_minutes(cfg["window_end"]):
                continue
            out.append(d)
    return out


# --------------------------------------------------------------------------- Notiser

WEEKDAYS_SV = ["mån", "tis", "ons", "tor", "fre", "lör", "sön"]


def notify(topic: str, server: str, title: str, message: str, click: str, dry_run: bool) -> None:
    if dry_run or not topic:
        print(f"\n[{'DRY-RUN' if dry_run else 'INGET NTFY_TOPIC'}] {title}\n{message}\n→ {click}")
        return
    resp = requests.post(
        server.rstrip("/"),
        json={"topic": topic, "title": title, "message": message, "click": click,
              "tags": ["tennis"], "priority": 4},
        timeout=15,
    )
    resp.raise_for_status()


def format_slots(slots: list[Slot], limit: int = 20) -> str:
    lines = []
    for s in sorted(slots, key=lambda x: (x.day, x.start, x.court)):
        d = date.fromisoformat(s.day)
        lines.append(f"{WEEKDAYS_SV[d.weekday()]} {d.day}/{d.month}  {s.start}–{s.end}  {s.court}")
    if len(lines) > limit:
        lines = lines[:limit] + [f"…och {len(lines) - limit} till"]
    return "\n".join(lines)


# --------------------------------------------------------------------------- Huvudlogik

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def run_once(cfg: dict, state_path: Path, dry_run: bool) -> int:
    state = load_json(state_path, {"free": {}, "facilities": {}})
    previous: dict[str, str] = state.get("free", {})
    fac_cache: dict[str, list] = state.get("facilities", {})
    current: dict[str, str] = {}
    new_by_facility: dict[str, list[Slot]] = {}
    links: dict[str, str] = {}
    errors = 0
    today_iso = datetime.now(TZ).date().isoformat()

    for entry in cfg["facilities"]:
        entry = str(entry).strip()
        try:
            if entry not in fac_cache:
                fac_cache[entry] = list(resolve_facility(entry))
            fid, fname, link = fac_cache[entry]
        except Exception as exc:  # noqa: BLE001
            print(f"FEL: kunde inte slå upp '{entry}': {exc}", file=sys.stderr)
            errors += 1
            continue
        links[fid] = link
        for d in days_to_check(cfg):
            day = d.isoformat()
            try:
                page = fetch(
                    "/book/schedule",
                    {"facilityId": fid, "date": day, "sport": cfg["sport"], "wl": ""},
                    debug_name=f"schedule_{fid}_{day}",
                )
                slots = [s for s in parse_schedule(page, fid, fname, day) if in_window(s, cfg)]
            except Exception as exc:  # noqa: BLE001
                print(f"FEL: {fname} {day}: {exc}", file=sys.stderr)
                errors += 1
                # Behåll gamla tider för den här dagen så vi inte dubbelnotifierar sen
                for k, v in previous.items():
                    if k.startswith(f"{fid}|{day}|"):
                        current[k] = v
                continue
            for s in slots:
                current[s.key] = s.day
                if s.key not in previous:
                    new_by_facility.setdefault(fid, []).append(s)
            time.sleep(cfg.get("request_delay_seconds", 0.7))

    topic = os.environ.get("NTFY_TOPIC") or cfg.get("ntfy_topic", "")
    server = os.environ.get("NTFY_SERVER") or cfg.get("ntfy_server", "https://ntfy.sh")
    for fid, slots in new_by_facility.items():
        title = f"{slots[0].facility_name}: {len(slots)} ny{'a' if len(slots) > 1 else ''} tid{'er' if len(slots) > 1 else ''}"
        try:
            notify(topic, server, title, format_slots(slots), links[fid], dry_run)
        except Exception as exc:  # noqa: BLE001
            print(f"FEL: notis misslyckades: {exc}", file=sys.stderr)
            # Glöm tiderna så vi försöker igen nästa körning
            for s in slots:
                current.pop(s.key, None)
            errors += 1

    total_new = sum(len(v) for v in new_by_facility.values())
    print(f"{datetime.now(TZ):%Y-%m-%d %H:%M} – {len(current)} lediga tider i fönstret, "
          f"{total_new} nya, {errors} fel")

    if not dry_run:
        state = {"free": {k: v for k, v in current.items() if v >= today_iso},
                 "facilities": fac_cache}
        state_path.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    return 1 if errors and not current and not new_by_facility else 0


def main() -> int:
    global DEBUG
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--state", default=str(HERE / "state.json"))
    ap.add_argument("--loop", type=int, metavar="SEK", help="kör om och om igen med N sekunders paus")
    ap.add_argument("--discover", metavar="SÖKORD", help="lista anläggningar (t.ex. 'Stockholm')")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--test-notis", action="store_true", help="skicka en testnotis och avsluta")
    args = ap.parse_args()
    DEBUG = args.debug

    cfg = load_json(Path(args.config), None)
    if cfg is None:
        print(f"Hittar ingen giltig config: {args.config}", file=sys.stderr)
        return 2

    if args.test_notis:
        topic = os.environ.get("NTFY_TOPIC") or cfg.get("ntfy_topic", "")
        notify(topic, cfg.get("ntfy_server", "https://ntfy.sh"), "MATCHi-bevakaren fungerar",
               "Testnotis – du kommer få notiser här när tider släpps.", BASE, dry_run=False)
        return 0

    if args.discover:
        for slug, name in discover(args.discover, cfg["sport"]):
            print(f'  "{slug}",   # {name}')
        return 0

    if not cfg.get("facilities"):
        print("Inga anläggningar i config.json. Kör först:  python matchi_bevakare.py --discover Stockholm",
              file=sys.stderr)
        return 2
    if not args.loop:
        return run_once(cfg, Path(args.state), args.dry_run)
    while True:
        try:
            run_once(cfg, Path(args.state), args.dry_run)
        except Exception as exc:  # noqa: BLE001
            print(f"Oväntat fel: {exc}", file=sys.stderr)
        time.sleep(args.loop)


if __name__ == "__main__":
    sys.exit(main())
