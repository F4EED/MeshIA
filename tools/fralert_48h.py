#!/usr/bin/env python3
"""Génère les fiches MeshIA des alertes FR-Alert des 48 dernières heures.

Source officielle (HTML serveur, sans API documentée) :
  https://fr-alert.gouv.fr/les-alertes
Détail d'une alerte :
  https://fr-alert.gouv.fr/les-alertes/<id>

Usage :
  python3 fralert_48h.py
  python3 fralert_48h.py --hours 48 --outdir /workspace/meshia-fiches/fiches/fr-alert

Dépendances : Python 3.10+, urllib, html.parser (stdlib). BeautifulSoup optionnel.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import ssl
import sys
import urllib.request
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
LIST_URL = "https://fr-alert.gouv.fr/les-alertes"
BASE = "https://fr-alert.gouv.fr"
UA = "Mozilla/5.0 (compatible; MeshIA-fralert/1.0; +local)"


def fetch(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    # Repli TLS non vérifié : nécessaire sur certains runners / boîtes
    # sans chaîne Sectigo complète (CERTIFICATE_VERIFY_FAILED sur *.gouv.fr).
    contexts = [ssl.create_default_context(), ssl._create_unverified_context()]
    last_err: Exception | None = None
    for ctx in contexts:
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:  # SSLCertVerificationError souvent encapsulé en URLError
            last_err = e
            continue
    raise RuntimeError(f"fetch failed for {url}: {last_err}")


MONTHS_FR = {
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
}


def parse_date_title(text: str) -> datetime | None:
    # "Jeudi 5 novembre 2026"
    m = re.search(
        r"(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    day = int(m.group(1))
    month = MONTHS_FR.get(m.group(2).lower())
    year = int(m.group(3))
    if not month:
        return None
    return datetime(year, month, day, tzinfo=PARIS)


class ListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_date: datetime | None = None
        self.in_date_title = False
        self.in_alert_title = False
        self.in_li = False
        self.li_depth = 0
        self.capture_li = False
        self.buf: list[str] = []
        self.attrs: dict[str, str] = {}
        self.href = ""
        self.alert_id = ""
        self.alerts: list[dict] = []
        self._title_buf: list[str] = []
        self._date_buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        ad = dict(attrs)
        classes = ad.get("class", "").split()
        if tag == "h3" and "date-title" in classes:
            self.in_date_title = True
            self._date_buf = []
        if tag == "li" and "alert-item" in classes:
            self.in_li = True
            self.capture_li = True
            self.buf = []
            self.attrs = {}
            self.href = ""
            self.alert_id = ad.get("id", "").rsplit("-", 1)[0]
        if self.capture_li:
            if tag == "a" and not self.href:
                self.href = ad.get("href", "")
            if tag == "h3" and "alert-title" in classes:
                self.in_alert_title = True
                self._title_buf = []
                for k in ("data-sender", "data-categorie", "data-statut"):
                    if k in ad:
                        self.attrs[k] = ad[k]

    def handle_endtag(self, tag):
        if tag == "h3" and self.in_date_title:
            self.in_date_title = False
            self.current_date = parse_date_title("".join(self._date_buf))
        if tag == "h3" and self.in_alert_title:
            self.in_alert_title = False
            self.attrs["title"] = " ".join("".join(self._title_buf).split())
        if tag == "li" and self.capture_li:
            self.capture_li = False
            text = " ".join("".join(self.buf).split())
            # heure HH:MM
            hm = re.search(r"\b(\d{1,2})h(\d{2})\b", text)
            hour = minute = 0
            if hm:
                hour, minute = int(hm.group(1)), int(hm.group(2))
            when = None
            if self.current_date:
                when = self.current_date.replace(hour=hour, minute=minute, second=0)
            # zone : ligne après le titre, avant l'heure
            zone = ""
            if self.attrs.get("title") and hm:
                after = text.split(self.attrs["title"], 1)[-1]
                zone = after[: hm.start() - (len(text) - len(after))].strip() if False else ""
                # plus simple : retirer titre + heure + fuseau
                zone = re.sub(r"^" + re.escape(self.attrs.get("title", "")), "", text).strip()
                zone = re.split(r"\b\d{1,2}h\d{2}\b", zone, 1)[0].strip()
            self.alerts.append(
                {
                    "id": self.alert_id or self.href,
                    "href": self.href,
                    "title": self.attrs.get("title", ""),
                    "sender": self.attrs.get("data-sender", ""),
                    "categorie": self.attrs.get("data-categorie", ""),
                    "statut": self.attrs.get("data-statut", ""),
                    "zone": zone,
                    "when": when,
                    "list_text": text,
                }
            )

    def handle_data(self, data):
        if self.in_date_title:
            self._date_buf.append(data)
        if self.in_alert_title:
            self._title_buf.append(data)
        if self.capture_li:
            self.buf.append(data)


def parse_list(html: str) -> list[dict]:
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(html, "html.parser")
        alerts = []
        for section in soup.select("section.date"):
            h3 = section.select_one("h3.date-title")
            day = parse_date_title(h3.get_text(" ", strip=True) if h3 else "")
            for li in section.select("li.alert-item"):
                title_el = li.select_one(".alert-title")
                title = title_el.get_text(" ", strip=True) if title_el else ""
                a = li.select_one("a")
                href = a.get("href", "") if a else ""
                aid = (li.get("id") or "").rsplit("-", 1)[0]
                text = li.get_text(" ", strip=True)
                hm = re.search(r"\b(\d{1,2})h(\d{2})\b", text)
                when = None
                if day and hm:
                    when = day.replace(hour=int(hm.group(1)), minute=int(hm.group(2)))
                zone = ""
                # structure : titre, zone, heure...
                lines = [x.strip() for x in li.get_text("\n", strip=True).split("\n") if x.strip()]
                if len(lines) >= 2:
                    zone = lines[1]
                alerts.append(
                    {
                        "id": aid or href,
                        "href": href,
                        "title": title,
                        "sender": (title_el.get("data-sender") if title_el else "") or "",
                        "categorie": (title_el.get("data-categorie") if title_el else "") or "",
                        "statut": (title_el.get("data-statut") if title_el else "") or "",
                        "zone": zone,
                        "when": when,
                        "list_text": text,
                    }
                )
        return alerts
    except Exception:
        p = ListParser()
        p.feed(html)
        return p.alerts


def parse_detail(html: str) -> dict:
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(html, "html.parser")
        text = (soup.select_one("main") or soup.body).get_text("\n", strip=True)
    except Exception:
        text = re.sub(r"<[^>]+>", "\n", html)
    msg = ""
    m = re.search(
        r"Message[^\n]*:\s*\n(.+?)(?:\nAller à la fin|\nInformations complémentaires|\Z)",
        text,
        re.S | re.I,
    )
    if m:
        msg = " ".join(m.group(1).split())
    else:
        # fallback : bloc après consignes
        m2 = re.search(r"Il vous est demandé\s*:(.+?)(?:Aller à la fin|\Z)", text, re.S | re.I)
        if m2:
            msg = "Il vous est demandé :" + " ".join(m2.group(1).split())
    sev = re.search(r"Sévérité\s*:?\s*([^\n]+)", text, re.I)
    urg = re.search(r"Urgence\s*:?\s*([^\n]+)", text, re.I)
    return {
        "message": msg[:400],
        "severite": (sev.group(1).strip() if sev else ""),
        "urgence": (urg.group(1).strip() if urg else ""),
        "raw": text[:2000],
    }


def slugify(s: str) -> str:
    s = s.lower()
    repl = {
        "à": "a",
        "â": "a",
        "ä": "a",
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "î": "i",
        "ï": "i",
        "ô": "o",
        "ö": "o",
        "ù": "u",
        "û": "u",
        "ü": "u",
        "ç": "c",
        "œ": "oe",
    }
    for a, b in repl.items():
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60] or "alerte"


def fiche_markdown(alert: dict, detail: dict) -> str:
    when = alert["when"]
    when_s = when.strftime("%d/%m/%Y %Hh%M") if when else "?"
    zone = alert.get("zone") or "zone non precisee"
    title_kw = "FR-Alert"
    risque = alert.get("title") or "Alerte"
    # essentiel ~120 premiers caractères
    consignes = detail.get("message") or "Suivre les consignes du message FR-Alert. Rester a l'ecoute des autorites."
    # compresser
    consignes = consignes.replace("Il vous est demandé :", "").strip()
    body_lines = [
        f"# {title_kw}",
        f"{when_s} Europe/Paris. {risque}. Zone: {zone}.",
        consignes[:200],
        "Lire le message entier, appliquer les consignes, ne pas telephoner inutilement.",
        "fr-alert, alerte, notification, telephone, consigne, urgence, population.",
    ]
    return "\n".join(body_lines) + "\n"


def filename_for(alert: dict) -> str:
    when = alert["when"]
    stamp = when.strftime("%Y%m%d-%H%M") if when else "nodate"
    short = slugify(alert.get("title") or "alerte")
    # id hash court pour unicité
    h = hashlib.sha1((alert.get("id") or "").encode()).hexdigest()[:8]
    return f"fr-alert-{stamp}-{short}-{h}.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=48.0)
    ap.add_argument(
        "--outdir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "fiches" / "fr-alert",
    )
    ap.add_argument("--since", default=None, help="ISO local Paris, ex. 2026-11-07T12:15:00")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-detail", action="store_true", help="Ne pas fetcher les pages détail")
    args = ap.parse_args()

    now = datetime.now(PARIS)
    if args.since:
        since = datetime.fromisoformat(args.since)
        if since.tzinfo is None:
            since = since.replace(tzinfo=PARIS)
        else:
            since = since.astimezone(PARIS)
    else:
        since = now - timedelta(hours=args.hours)

    print(f"Lecture {LIST_URL}", file=sys.stderr)
    html = fetch(LIST_URL)
    alerts = parse_list(html)
    print(f"{len(alerts)} alertes listées sur la page", file=sys.stderr)

    recent = [a for a in alerts if a.get("when") and a["when"] >= since]
    recent.sort(key=lambda a: a["when"] or datetime.min.replace(tzinfo=PARIS), reverse=True)
    print(f"{len(recent)} dans la fenêtre depuis {since.isoformat()}", file=sys.stderr)

    outdir: Path = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    keep_names: set[str] = set()
    for a in recent:
        detail = {"message": "", "severite": "", "urgence": ""}
        if not args.no_detail and a.get("href"):
            url = a["href"] if a["href"].startswith("http") else BASE + a["href"].split("#")[0]
            try:
                detail = parse_detail(fetch(url))
            except Exception as e:
                print(f"detail fail {url}: {e}", file=sys.stderr)
        md = fiche_markdown(a, detail)
        name = filename_for(a)
        keep_names.add(name)
        path = outdir / name
        print(f"WRITE {path}", file=sys.stderr)
        if not args.dry_run:
            path.write_text(md, encoding="utf-8")

    # supprimer les fiches hors fenêtre (anciennes)
    removed = 0
    for p in outdir.glob("fr-alert-*.md"):
        if p.name not in keep_names:
            print(f"DELETE {p}", file=sys.stderr)
            if not args.dry_run:
                p.unlink()
            removed += 1

    print(f"OK: {len(keep_names)} fiches, {removed} anciennes supprimées")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
