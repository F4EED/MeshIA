#!/usr/bin/env python3
"""Portail web MeshIA (LAN). N'ouvre pas le port serie, n'appelle pas Ollama."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import stat
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
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

ROOT = Path(os.environ.get("MESHIA_ROOT", "/opt/meshia"))
WEB = Path(__file__).resolve().parent
for _p in (str(WEB), str(ROOT)):
    while _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(WEB))

from extract import ALLOWED_EXT, ExtractError, extraire_texte  # noqa: E402
from fetch_url import FetchError, fetch_fiche  # noqa: E402
from meshia import chercher, lister_titres  # noqa: E402

FICHES = ROOT / "fiches"
INGEST = ROOT / "ingest.py"
PYTHON = ROOT / ".venv" / "bin" / "python"
USERS_FILE = Path(os.environ.get("MESHIA_WEB_USERS", str(WEB / "users.json")))
SECRET_FILE = Path(os.environ.get("MESHIA_WEB_SECRET", str(WEB / "secret.key")))
LOCK_FILE = WEB / "ingest.lock"
BIND = os.environ.get("MESHIA_WEB_BIND", "127.0.0.1")
PORT = int(os.environ.get("MESHIA_WEB_PORT", "8765"))
ADMINS = {"meshia"}
USER_RE = re.compile(r"^[A-Za-z0-9._-]{2,32}$")

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


def _sauver_users(data: dict) -> None:
    WEB.mkdir(parents=True, exist_ok=True)
    tmp = USERS_FILE.with_name(USERS_FILE.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    tmp.replace(USERS_FILE)
    os.chmod(USERS_FILE, stat.S_IRUSR | stat.S_IWUSR)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            nxt = request.path if request.path.startswith("/meshia") else "/meshia/"
            return redirect(url_for("login", next=nxt))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login", next=request.path))
        if session.get("user") not in ADMINS:
            flash("Cette page est réservée au compte meshia.", "err")
            return redirect(url_for("recherche"))
        return view(*args, **kwargs)

    return wrapped


@app.context_processor
def _nav():
    return {"est_admin": session.get("user") in ADMINS}


def titre_safe(titre: str) -> str:
    s = unicodedata.normalize("NFKD", titre)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s[:80] or "fiche"


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


def rechercher_fiche(question: str) -> dict:
    """Meme logique FTS5 que meshia.py, sans Ollama. Toujours un texte a afficher."""
    q = question.strip()
    if q.lower() in ("aide", "?", "help", "liste"):
        titres = lister_titres()
        contenu = "Sujets : " + ", ".join(titres) if titres else "Aucune fiche."
        return {"vide": False, "aide": True, "titre": "Aide", "contenu": contenu}
    try:
        trouve = chercher(q)
    except sqlite3.Error as e:
        return {"vide": True, "aide": False, "titre": None, "contenu": f"Erreur de recherche : {e}"}
    if trouve is None:
        titres = lister_titres()
        sujets = ", ".join(titres[:15]) if titres else "(aucune fiche indexée)"
        return {
            "vide": True,
            "aide": False,
            "titre": None,
            "contenu": f"Rien trouvé. Sujets : {sujets}",
        }
    titre, contenu = trouve
    return {"vide": False, "aide": False, "titre": titre, "contenu": contenu or ""}


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


@app.route("/meshia/url", methods=["GET", "POST"])
@login_required
def depuis_url():
    brouillon = session.get("brouillon_url") if isinstance(session.get("brouillon_url"), dict) else None
    if request.method == "POST":
        action = (request.form.get("action") or "apercu").strip()
        if action == "annuler":
            session.pop("brouillon_url", None)
            flash("Brouillon annulé. Rien n’a été enregistré.", "ok")
            return redirect(url_for("depuis_url"))
        if action == "creer":
            if not session.get("brouillon_url"):
                flash("Aucun aperçu en cours. Récupérez d’abord l’URL.", "err")
                return redirect(url_for("depuis_url"))
            titre = request.form.get("titre") or ""
            texte = request.form.get("texte") or ""
            try:
                dest = ecrire_fiche(titre, texte)
                msg = indexer()
                session.pop("brouillon_url", None)
                flash(f"Fiche créée : {dest.name}. {msg}", "ok")
                return redirect(url_for("depuis_url"))
            except (ValueError, RuntimeError, OSError) as e:
                flash(str(e), "err")
                brouillon = {
                    "source": (session.get("brouillon_url") or {}).get("source", ""),
                    "titre": titre,
                    "texte": texte,
                }
                return render_template("url.html", brouillon=brouillon)
        try:
            fiche = fetch_fiche(request.form.get("url") or "")
        except FetchError as e:
            flash(str(e), "err")
            return render_template("url.html", brouillon=None, url=request.form.get("url") or "")
        session["brouillon_url"] = {
            "source": fiche["source"],
            "titre": fiche["titre"],
            "texte": fiche["texte"],
            "tronque": fiche.get("tronque", False),
        }
        return render_template("url.html", brouillon=fiche)
    return render_template("url.html", brouillon=brouillon if brouillon and brouillon.get("titre") else None)


@app.route("/meshia/recherche", methods=["GET", "POST"])
@login_required
def recherche():
    if request.method == "POST":
        question = (request.form.get("q") or "").strip()
    else:
        question = (request.args.get("q") or "").strip()
    resultat = None
    if question:
        resultat = rechercher_fiche(question)
    elif request.method == "POST":
        flash("Saisissez une question ou un mot-clé.", "err")
    return render_template("recherche.html", question=question, resultat=resultat)


@app.route("/meshia/utilisateurs", methods=["GET", "POST"])
@admin_required
def utilisateurs():
    users = _users()
    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        nom = (request.form.get("username") or "").strip()
        mot = request.form.get("password") or ""
        try:
            if action == "creer":
                if not USER_RE.match(nom):
                    raise ValueError("Identifiant : 2 à 32 caractères (lettres, chiffres, . _ -).")
                if nom in users:
                    raise ValueError(f"Le compte {nom} existe déjà.")
                if len(mot) < 8:
                    raise ValueError("Mot de passe : 8 caractères minimum.")
                users[nom] = generate_password_hash(mot, method="scrypt")
                _sauver_users(users)
                flash(f"Compte {nom} créé.", "ok")
            elif action == "mdp":
                if nom not in users:
                    raise ValueError("Compte introuvable.")
                if len(mot) < 8:
                    raise ValueError("Mot de passe : 8 caractères minimum.")
                users[nom] = generate_password_hash(mot, method="scrypt")
                _sauver_users(users)
                flash(f"Mot de passe de {nom} mis à jour.", "ok")
            elif action == "supprimer":
                if nom == "meshia":
                    raise ValueError("Le compte meshia ne peut pas être supprimé.")
                if nom == session.get("user"):
                    raise ValueError("Vous ne pouvez pas supprimer le compte connecté.")
                if nom not in users:
                    raise ValueError("Compte introuvable.")
                del users[nom]
                _sauver_users(users)
                flash(f"Compte {nom} supprimé.", "ok")
            else:
                raise ValueError("Action inconnue.")
            return redirect(url_for("utilisateurs"))
        except (ValueError, OSError) as e:
            flash(str(e), "err")
    noms = sorted(users.keys())
    return render_template("utilisateurs.html", noms=noms)


if __name__ == "__main__":
    if not USERS_FILE.is_file():
        sys.stderr.write(f"Fichier utilisateurs manquant : {USERS_FILE}\n")
        sys.exit(1)
    try:
        from waitress import serve

        serve(app, host=BIND, port=PORT, threads=4)
    except ImportError:
        app.run(host=BIND, port=PORT, threaded=True)
