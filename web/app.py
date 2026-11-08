#!/usr/bin/env python3
"""Portail web MeshIA (LAN). N'ouvre pas le port serie, n'appelle pas Ollama."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

ROOT = Path(os.environ.get("MESHIA_ROOT", "/opt/meshia"))
WEB = Path(__file__).resolve().parent
for _p in (str(WEB), str(ROOT)):
    while _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(WEB))

from extract import ALLOWED_EXT, ExtractError, extraire_texte  # noqa: E402
from meshia import chercher, lister_titres  # noqa: E402

FICHES = ROOT / "fiches"
INGEST = ROOT / "ingest.py"
PYTHON = ROOT / ".venv" / "bin" / "python"
USERS_FILE = Path(os.environ.get("MESHIA_WEB_USERS", str(WEB / "users.json")))
SECRET_FILE = Path(os.environ.get("MESHIA_WEB_SECRET", str(WEB / "secret.key")))
LOCK_FILE = WEB / "ingest.lock"
BIND = os.environ.get("MESHIA_WEB_BIND", "127.0.0.1")
PORT = int(os.environ.get("MESHIA_WEB_PORT", "8765"))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_PATH"] = "/meshia"
app.config["SESSION_COOKIE_SECURE"] = False
app.config["PERMANENT_SESSION_LIFETIME"] = 8 * 3600


def _lire_secret() -> str:
    if SECRET_FILE.is_file():
        cle = SECRET_FILE.read_text(encoding="utf-8").strip()
        if cle:
            return cle
    return "meshia-dev-insecure"


app.secret_key = _lire_secret()


def _users() -> dict:
    if not USERS_FILE.is_file():
        return {}
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            nxt = request.path if request.path.startswith("/meshia") else "/meshia/"
            return redirect(url_for("login", next=nxt))
        return view(*args, **kwargs)

    return wrapped


def titre_safe(titre: str) -> str:
    s = unicodedata.normalize("NFKD", titre)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return (s[:80] or "fiche")


def ecrire_fiche(titre: str, texte: str) -> Path:
    titre = (titre or "").strip()
    texte = (texte or "").strip()
    if not titre:
        raise ValueError("Le titre est obligatoire.")
    if not texte:
        raise ValueError("Le texte de la fiche est obligatoire.")
    FICHES.mkdir(parents=True, exist_ok=True)
    dest = FICHES / f"{titre_safe(titre)}.md"
    corps = texte if texte.endswith("\n") else texte + "\n"
    dest.write_text(f"# {titre}\n{corps}", encoding="utf-8")
    return dest


def indexer() -> str:
    python = PYTHON if PYTHON.is_file() else Path(sys.executable)
    WEB.mkdir(parents=True, exist_ok=True)
    with open(LOCK_FILE, "a", encoding="utf-8") as lock:
        try:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        r = subprocess.run(
            [str(python), str(INGEST), str(FICHES)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "MESHIA_DB": os.environ.get("MESHIA_DB", str(ROOT / "meshia.db"))},
        )
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "ingest.py a echoue").strip()
        raise RuntimeError(err)
    return (r.stdout or "").strip() or "indexation terminee"


def reponse_radio(question: str) -> str:
    """Meme logique que meshia.construire_reponse, sans Ollama (fiche brute)."""
    q = question.strip()
    if q.lower() in ("aide", "?", "help", "liste"):
        titres = lister_titres()
        return "Sujets : " + ", ".join(titres) if titres else "Aucune fiche."
    trouve = chercher(q)
    if trouve is None:
        titres = lister_titres()
        return "Rien trouvé. Sujets : " + ", ".join(titres[:15])
    titre, contenu = trouve
    return f"{titre} : {contenu}"


@app.route("/meshia/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("recherche"))
    erreur = None
    if request.method == "POST":
        nom = (request.form.get("username") or "").strip()
        mot = request.form.get("password") or ""
        hashed = _users().get(nom)
        if hashed and check_password_hash(hashed, mot):
            session.clear()
            session["user"] = nom
            session.permanent = True
            nxt = request.form.get("next") or request.args.get("next") or ""
            if not (nxt.startswith("/meshia") and not nxt.startswith("//")):
                nxt = url_for("recherche")
            return redirect(nxt)
        erreur = "Identifiant ou mot de passe incorrect."
    return render_template("login.html", erreur=erreur, next=request.args.get("next") or "")


@app.route("/meshia/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/meshia")
@app.route("/meshia/")
@login_required
def accueil():
    return redirect(url_for("recherche"))


@app.route("/meshia/saisir", methods=["GET", "POST"])
@login_required
def saisir():
    if request.method == "POST":
        titre = request.form.get("titre") or ""
        texte = request.form.get("texte") or ""
        try:
            dest = ecrire_fiche(titre, texte)
            msg = indexer()
            flash(f"Fiche enregistrée : {dest.name}. {msg}", "ok")
            return redirect(url_for("saisir"))
        except (ValueError, RuntimeError, OSError) as e:
            flash(str(e), "err")
    return render_template("saisir.html")


@app.route("/meshia/importer", methods=["GET", "POST"])
@login_required
def importer():
    if request.method == "POST":
        f = request.files.get("fichier")
        titre = (request.form.get("titre") or "").strip()
        if f is None or not f.filename:
            flash("Choisissez un fichier à importer.", "err")
            return render_template("importer.html")
        nom = secure_filename(f.filename) or "import"
        ext = Path(nom).suffix.lower()
        if ext not in ALLOWED_EXT:
            flash("Formats acceptés : txt, md, pdf, doc, docx.", "err")
            return render_template("importer.html")
        if not titre:
            titre = Path(nom).stem.replace("_", " ").replace("-", " ").strip() or "Import"
        tmp = None
        try:
            fd, tmp_name = tempfile.mkstemp(suffix=ext, prefix="meshia-import-")
            os.close(fd)
            tmp = Path(tmp_name)
            f.save(str(tmp))
            texte = extraire_texte(tmp, ext).strip()
            if not texte:
                raise ExtractError("Aucun texte extractible dans ce fichier.")
            dest = ecrire_fiche(titre, texte)
            msg = indexer()
            flash(f"Importé dans {dest.name}. {msg}", "ok")
            return redirect(url_for("importer"))
        except (ExtractError, ValueError, RuntimeError, OSError) as e:
            flash(str(e), "err")
        finally:
            if tmp is not None:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
    return render_template("importer.html")


@app.route("/meshia/recherche", methods=["GET", "POST"])
@login_required
def recherche():
    question = ""
    resultat = None
    if request.method == "POST":
        question = (request.form.get("q") or "").strip()
        if not question:
            flash("Saisissez une question ou un mot-clé.", "err")
        else:
            resultat = reponse_radio(question)
    return render_template("recherche.html", question=question, resultat=resultat)


if __name__ == "__main__":
    if not USERS_FILE.is_file():
        sys.stderr.write(f"Fichier utilisateurs manquant : {USERS_FILE}\n")
        sys.exit(1)
    try:
        from waitress import serve

        serve(app, host=BIND, port=PORT, threads=4)
    except ImportError:
        app.run(host=BIND, port=PORT, threaded=True)
