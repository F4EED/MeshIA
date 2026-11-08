#!/usr/bin/env python3
"""Liste d'attente des nœuds MeshCore (fichier hors git, chmod 600)."""
from __future__ import annotations

import os
import sqlite3
import stat
from datetime import datetime
from pathlib import Path

DB = Path(os.environ.get("MESHIA_NOEUDS", "/opt/meshia/noeuds.db"))
STATUTS = ("attente", "autorise", "refuse")
MSG_ATTENTE = "Inscription en attente."
MSG_REFUS = "Accès refusé."
LABELS = {
    "attente": "En attente",
    "autorise": "Autorisé",
    "refuse": "Refusé",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _hex(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).hex().lower()
    s = str(v).strip().lower().replace(":", "")
    if s.startswith("0x"):
        s = s[2:]
    return "".join(c for c in s if c in "0123456789abcdef")


def identite(contact, prefix):
    prefix_h = _hex(prefix)
    pk = ""
    nom = ""
    if isinstance(contact, dict):
        pk = _hex(contact.get("public_key") or contact.get("publicKey") or contact.get("pubkey"))
        nom = str(contact.get("name") or contact.get("adv_name") or contact.get("given_name") or "")
    elif contact is not None:
        pk = _hex(
            getattr(contact, "public_key", None)
            or getattr(contact, "publicKey", None)
            or getattr(contact, "pubkey", None)
        )
        nom = str(
            getattr(contact, "name", None)
            or getattr(contact, "adv_name", None)
            or getattr(contact, "given_name", None)
            or ""
        )
    ident = pk or prefix_h
    nom = (nom or "").strip() or prefix_h or "?"
    return ident, nom, prefix_h


def _chmod(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _con():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    con.execute(
        """CREATE TABLE IF NOT EXISTS noeuds (
            pubkey TEXT PRIMARY KEY,
            prefix TEXT,
            nom TEXT,
            statut TEXT NOT NULL CHECK (statut IN ('attente','autorise','refuse')),
            premier_vu TEXT NOT NULL,
            dernier_vu TEXT,
            refuse_notifie INTEGER NOT NULL DEFAULT 0
        )"""
    )
    con.commit()
    _chmod(DB)
    for extra in (str(DB) + "-wal", str(DB) + "-shm"):
        if os.path.isfile(extra):
            _chmod(Path(extra))
    return con


def _trouver(con, ident, prefix=""):
    ident = _hex(ident)
    prefix = _hex(prefix)
    if ident:
        row = con.execute("SELECT * FROM noeuds WHERE lower(pubkey)=?", (ident,)).fetchone()
        if row:
            return row
    if prefix:
        row = con.execute("SELECT * FROM noeuds WHERE lower(prefix)=?", (prefix,)).fetchone()
        if row:
            return row
        if len(prefix) >= 8:
            return con.execute(
                "SELECT * FROM noeuds WHERE lower(pubkey) LIKE ?",
                (prefix + "%",),
            ).fetchone()
    return None


def voir(ident, nom, prefix=""):
    """Nouveau nœud → attente. Sinon met à jour nom/date et renvoie le statut actuel."""
    ident, prefix = _hex(ident), _hex(prefix)
    nom = (nom or "").strip() or prefix or ident[:12] or "?"
    if not ident:
        return None
    now = _now()
    con = _con()
    try:
        row = _trouver(con, ident, prefix)
        if row is None:
            con.execute(
                "INSERT INTO noeuds (pubkey, prefix, nom, statut, premier_vu, dernier_vu, refuse_notifie) "
                "VALUES (?,?,?,?,?,?,0)",
                (ident, prefix or ident[:12], nom, "attente", now, now),
            )
            con.commit()
            return "attente"
        pk = row["pubkey"]
        if ident and len(ident) > len(pk or ""):
            con.execute("UPDATE noeuds SET pubkey=? WHERE pubkey=?", (ident, pk))
            pk = ident
        con.execute(
            "UPDATE noeuds SET nom=?, prefix=COALESCE(NULLIF(?,''), prefix), dernier_vu=? WHERE pubkey=?",
            (nom, prefix, now, pk),
        )
        con.commit()
        return row["statut"]
    finally:
        con.close()


def set_statut(ident, statut, prefix=""):
    if statut not in STATUTS:
        raise ValueError("Statut inconnu.")
    ident, prefix = _hex(ident), _hex(prefix)
    con = _con()
    try:
        row = _trouver(con, ident, prefix)
        if row is None:
            raise ValueError("Nœud introuvable.")
        notifie = 0
        if statut == "refuse" and row["statut"] == "refuse":
            notifie = row["refuse_notifie"]
        con.execute(
            "UPDATE noeuds SET statut=?, refuse_notifie=?, dernier_vu=? WHERE pubkey=?",
            (statut, notifie, _now(), row["pubkey"]),
        )
        con.commit()
        return row["pubkey"]
    finally:
        con.close()


def marquer_refuse_notifie(ident, prefix=""):
    con = _con()
    try:
        row = _trouver(con, ident, prefix)
        if row is None:
            return
        con.execute(
            "UPDATE noeuds SET refuse_notifie=1, dernier_vu=? WHERE pubkey=?",
            (_now(), row["pubkey"]),
        )
        con.commit()
    finally:
        con.close()


def lister():
    con = _con()
    try:
        rows = con.execute(
            "SELECT pubkey, prefix, nom, statut, premier_vu, dernier_vu, refuse_notifie "
            "FROM noeuds ORDER BY CASE statut WHEN 'attente' THEN 0 WHEN 'autorise' THEN 1 ELSE 2 END, "
            "dernier_vu DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def par_statut():
    data = {"attente": [], "autorise": [], "refuse": []}
    for n in lister():
        data.get(n["statut"], data["refuse"]).append(n)
    return data


def decision_mp(contact, prefix):
    """action : ok | attente | refus | silence. texte_mp éventuellement à envoyer."""
    ident, nom, pref = identite(contact, prefix)
    if not ident:
        return "silence", None, ident, nom, pref
    st = voir(ident, nom, pref)
    if st == "autorise":
        return "ok", None, ident, nom, pref
    if st == "attente" or st is None:
        return "attente", MSG_ATTENTE, ident, nom, pref
    con = _con()
    try:
        row = _trouver(con, ident, pref)
        deja = bool(row["refuse_notifie"]) if row else True
    finally:
        con.close()
    if deja:
        return "silence", None, ident, nom, pref
    return "refus", MSG_REFUS, ident, nom, pref
