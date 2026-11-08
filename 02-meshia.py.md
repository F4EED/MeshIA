# 02 — `meshia.py` : le service qui répond sur le mesh

## Rôle

Se connecte au nœud MeshCore (Companion USB) sur le port série, écoute les **messages privés** reçus, cherche la meilleure fiche dans SQLite et répond à l'expéditeur.

## Comportement

- Un message `aide`, `?`, `help` ou `liste` renvoie la liste des sujets disponibles.
- Une question libre : les mots utiles sont extraits (mots de 3 lettres ou plus, sans mots vides), puis cherchés en FTS5 avec préfixes (`"mot"*`, séparés par `OR`). La meilleure fiche est choisie avec `bm25`, le titre pesant 5 fois plus que le contenu.
- Si rien ne correspond : réponse « Rien trouvé. Sujets : … ».
- **Limite de payload** : la réponse est découpée en parties de `MESHIA_MAXLEN` octets (UTF-8, sans couper un caractère, de préférence à un espace), en `MESHIA_MAXPARTS` messages au plus. Si le texte dépasse, la dernière partie se termine par « … ». Pause de `MESHIA_PAUSE` secondes entre les parties.
- Si la connexion au nœud échoue, nouvel essai toutes les 10 secondes. Si le nœud se déconnecte en cours de route, le script s'arrête (systemd le relancera à l'étape 8).
- `MESHIA_LLM` est lue mais **pas encore utilisée** (étape 7).

## Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `MESHIA_SERIAL` | `/dev/ttyACM0` | port série du nœud |
| `MESHIA_DB` | `/opt/meshia/meshia.db` | base SQLite |
| `MESHIA_LLM` | `0` | `1` pour activer le LLM (étape 7, pas encore branché) |
| `MESHIA_MAXLEN` | `130` | taille max d'un message, en octets |
| `MESHIA_MAXPARTS` | `3` | nombre max de messages par réponse |
| `MESHIA_PAUSE` | `4` | secondes entre deux parties |

## Création du fichier

```bash
cd /opt/meshia && source .venv/bin/activate
nano meshia.py
```

Coller le code ci-dessous, puis Ctrl+O, Entrée, Ctrl+X.

## Code

```python
import asyncio, logging, os, re, sqlite3
from meshcore import MeshCore, EventType

PORT = os.environ.get("MESHIA_SERIAL", "/dev/ttyACM0")
DB = os.environ.get("MESHIA_DB", "/opt/meshia/meshia.db")
LLM = os.environ.get("MESHIA_LLM", "0") == "1"          # étape 7, pas encore branché
MAX_OCTETS = int(os.environ.get("MESHIA_MAXLEN", "130"))  # taille max d'un message
MAX_PARTS = int(os.environ.get("MESHIA_MAXPARTS", "3"))   # nb max de messages par réponse
PAUSE = float(os.environ.get("MESHIA_PAUSE", "4"))        # secondes entre deux parties

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("meshia")

MOTS_VIDES = {
    "les", "des", "une", "est", "que", "qui", "quoi", "comment", "pour", "dans",
    "sur", "avec", "pas", "par", "aux", "ces", "ses", "mon", "ton", "son", "mes",
    "tes", "nous", "vous", "ils", "elles", "faire", "fait", "dois", "peut", "puis",
    "the", "and",
}


def chercher(question):
    mots = [m for m in re.findall(r"\w+", question.lower())
            if len(m) >= 3 and m not in MOTS_VIDES]
    if not mots:
        return None
    requete = " OR ".join(f'"{m}"*' for m in mots)
    con = sqlite3.connect(DB)
    try:
        ligne = con.execute(
            "SELECT titre, contenu FROM fiches WHERE fiches MATCH ? "
            "ORDER BY bm25(fiches, 5.0, 1.0) LIMIT 1",
            (requete,),
        ).fetchone()
    finally:
        con.close()
    return ligne


def lister_titres():
    con = sqlite3.connect(DB)
    try:
        return [r[0] for r in con.execute("SELECT titre FROM fiches ORDER BY titre")]
    finally:
        con.close()


def decouper(texte, limite, max_parts):
    limite -= 4  # marge pour le " …"
    parts = []
    while texte and len(parts) < max_parts:
        if len(texte.encode()) <= limite:
            parts.append(texte)
            texte = ""
            break
        coupe = texte.encode()[:limite].decode("utf-8", "ignore")
        i = coupe.rfind(" ")
        if i > limite // 2:
            coupe = coupe[:i]
        parts.append(coupe.rstrip())
        texte = texte[len(coupe):].lstrip()
    if texte and parts:
        parts[-1] += " …"
    return parts


def construire_reponse(question):
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


async def main():
    mc = None
    while mc is None:
        mc = await MeshCore.create_serial(PORT)
        if mc is None:
            log.warning("Connexion au nœud impossible, nouvel essai dans 10 s")
            await asyncio.sleep(10)

    await mc.ensure_contacts()
    perdu = asyncio.Event()

    async def on_msg(event):
        p = event.payload
        question = (p.get("text") or "").strip()
        prefix = p.get("pubkey_prefix")
        if not question:
            return
        log.info("Question de %s : %s", prefix, question)

        contact = mc.get_contact_by_key_prefix(prefix)
        if contact is None:
            try:
                await mc.commands.get_contacts()
            except Exception as e:
                log.warning("Rafraîchissement des contacts : %s", e)
            contact = mc.get_contact_by_key_prefix(prefix)
        if contact is None:
            log.warning("Contact inconnu (%s), pas de réponse", prefix)
            return

        reponse = construire_reponse(question)
        parts = decouper(reponse, MAX_OCTETS, MAX_PARTS)
        for i, part in enumerate(parts):
            await mc.commands.send_msg(contact, part)
            log.info("Envoyé (%d/%d) : %s", i + 1, len(parts), part)
            if i < len(parts) - 1:
                await asyncio.sleep(PAUSE)

    mc.subscribe(EventType.CONTACT_MSG_RECV, on_msg)
    if hasattr(EventType, "DISCONNECTED"):
        mc.subscribe(EventType.DISCONNECTED, lambda e: perdu.set())
    await mc.start_auto_message_fetching()

    log.info("MeshIA prête sur %s (LLM=%s)", PORT, LLM)
    await perdu.wait()
    log.error("Nœud déconnecté, arrêt (systemd relancera le service)")


asyncio.run(main())
```

## Points à vérifier si une erreur apparaît

Le code n'a pas été testé contre toutes les versions de `meshcore`. Les appels les plus susceptibles de varier :

- `MeshCore.create_serial(port)` (renvoie `None` si le nœud ne répond pas)
- `mc.ensure_contacts()`
- `mc.get_contact_by_key_prefix(prefix)`
- `mc.commands.get_contacts()`
- `mc.commands.send_msg(contact, texte)`
- `mc.subscribe(EventType.CONTACT_MSG_RECV, handler)`
- `mc.start_auto_message_fetching()`

Vérifier la version avec `pip show meshcore`, et lister les méthodes avec `python -c "import meshcore; print(dir(meshcore))"`.
