"""Fetch http(s) pour proposer une fiche. Pas de file://."""
from __future__ import annotations

import html as htmlmod
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

MAX_OCTETS = 1_000_000
TIMEOUT = 15
MAX_TEXTE = 8000
UA = "MeshIA-LAN/1.7"


class FetchError(Exception):
    pass


class _HtmlTexte(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._zone = None
        self._buf: list[str] = []
        self.title = ""
        self.h1 = ""
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
            return
        if tag in ("title", "h1") and self._skip == 0:
            self._zone = tag
            self._buf = []
        if tag in ("p", "div", "br", "li", "h2", "h3", "tr", "section", "article"):
            self.parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and self._skip == 0:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1
            return
        if tag in ("title", "h1") and self._zone == tag:
            texte = htmlmod.unescape(" ".join("".join(self._buf).split()))
            if tag == "title" and not self.title:
                self.title = texte
            if tag == "h1" and not self.h1:
                self.h1 = texte
            self._zone = None
            self._buf = []
        if tag in ("p", "div", "li", "h2", "h3", "tr", "section", "article"):
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        if self._zone:
            self._buf.append(data)
        else:
            self.parts.append(data)


def _url_ok(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise FetchError("Collez une URL http ou https.")
    if url.lower().startswith("file:"):
        raise FetchError("Les URL file:// sont refusées.")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError("Seules les URL http et https sont acceptées.")
    if not parsed.netloc:
        raise FetchError("URL incomplète.")
    return url


def _lire_reponse(resp) -> tuple[bytes, str, str]:
    final = resp.geturl() or ""
    if final.lower().startswith("file:"):
        raise FetchError("Redirection vers file:// refusée.")
    ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    charset = "utf-8"
    m = re.search(r"charset=([\w-]+)", resp.headers.get("Content-Type") or "", re.I)
    if m:
        charset = m.group(1)
    data = resp.read(MAX_OCTETS + 1)
    if len(data) > MAX_OCTETS:
        raise FetchError("Page trop volumineuse (max 1 Mo).")
    return data, ctype, charset


def extraire_html(raw: str) -> tuple[str, str]:
    p = _HtmlTexte()
    try:
        p.feed(raw)
        p.close()
    except Exception:
        pass
    titre = p.h1 or p.title or ""
    texte = re.sub(r"[ \t]+", " ", "".join(p.parts))
    texte = re.sub(r"\n{3,}", "\n\n", texte).strip()
    return titre.strip(), texte


def fetch_fiche(url: str) -> dict:
    url = _url_ok(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,text/plain,text/markdown,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data, ctype, charset = _lire_reponse(resp)
            final = resp.geturl()
    except FetchError:
        raise
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code} pour {url}") from e
    except urllib.error.URLError as e:
        raise FetchError(f"Récupération impossible : {e.reason}") from e
    except TimeoutError as e:
        raise FetchError(f"Délai dépassé ({TIMEOUT} s).") from e
    except OSError as e:
        raise FetchError(str(e)) from e

    try:
        brut = data.decode(charset, errors="replace")
    except LookupError:
        brut = data.decode("utf-8", errors="replace")

    if ctype in ("text/plain", "text/markdown") or final.lower().endswith((".txt", ".md")):
        titre = urllib.parse.unquote(urllib.parse.urlparse(final).path.rsplit("/", 1)[-1])
        titre = re.sub(r"\.(txt|md)$", "", titre, flags=re.I).replace("-", " ").strip() or "Import URL"
        texte = brut.strip()
    else:
        titre, texte = extraire_html(brut)
        if not titre:
            path = urllib.parse.urlparse(final).path.rsplit("/", 1)[-1]
            titre = urllib.parse.unquote(path).replace("-", " ").strip() or "Import URL"

    if not texte:
        raise FetchError("Aucun texte extractible à cette URL.")
    tronque = False
    if len(texte) > MAX_TEXTE:
        texte = texte[:MAX_TEXTE].rsplit(" ", 1)[0] + "\n[…] (texte tronqué)"
        tronque = True
    return {"source": final or url, "titre": titre[:120], "texte": texte, "tronque": tronque}
