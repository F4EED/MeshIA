"""Extraction de texte pour l'import de fiches (best-effort pour .doc)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ALLOWED_EXT = {".txt", ".md", ".pdf", ".doc", ".docx"}


class ExtractError(Exception):
    pass


def extraire_texte(path: Path, ext: str | None = None) -> str:
    ext = (ext or path.suffix).lower()
    if ext not in ALLOWED_EXT:
        raise ExtractError(f"Format non pris en charge : {ext or '(sans extension)'}")
    if ext in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if ext == ".pdf":
        return _pdf(path)
    if ext == ".docx":
        return _docx(path)
    return _doc_ancien(path)


def _pdf(path: Path) -> str:
    exe = shutil.which("pdftotext")
    if not exe:
        raise ExtractError("pdftotext absent (paquet Debian poppler-utils)")
    r = subprocess.run(
        [exe, "-layout", "-enc", "UTF-8", str(path), "-"],
        capture_output=True,
        timeout=60,
    )
    if r.returncode != 0:
        err = (r.stderr or b"").decode("utf-8", "replace").strip()
        raise ExtractError(err or "extraction PDF impossible")
    return (r.stdout or b"").decode("utf-8", "replace")


def _docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as e:
        raise ExtractError("python-docx n'est pas installe dans le venv") from e
    doc = Document(str(path))
    parties = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cellules = [c.text.strip() for c in row.cells if c.text.strip()]
            if cellules:
                parties.append(" | ".join(cellules))
    return "\n".join(parties)


def _doc_ancien(path: Path) -> str:
    commandes = []
    if shutil.which("catdoc"):
        commandes.append(["catdoc", "-w", str(path)])
    if shutil.which("antiword"):
        commandes.append(["antiword", str(path)])
    if shutil.which("libreoffice"):
        commandes.append(
            ["libreoffice", "--headless", "--cat", str(path)]
        )
    if not commandes:
        raise ExtractError(
            "Aucun convertisseur .doc (catdoc, antiword ou libreoffice --headless)"
        )
    erreurs = []
    for cmd in commandes:
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=90)
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            erreurs.append(f"{cmd[0]}: {e}")
            continue
        texte = (r.stdout or b"").decode("utf-8", "replace")
        if not texte.strip():
            texte = (r.stdout or b"").decode("latin-1", "replace")
        if r.returncode == 0 and texte.strip():
            return texte
        err = (r.stderr or b"").decode("utf-8", "replace").strip()
        erreurs.append(f"{cmd[0]}: {err or 'sortie vide'}")
    raise ExtractError("extraction .doc impossible (" + " ; ".join(erreurs) + ")")
