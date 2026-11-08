# 02 — `meshia.py` : le service qui répond sur le mesh

Le fichier **vivant** est `meshia.py` à la racine du dépôt. Le listing plus bas est l’ébauche étape 6.

## Rôle

Un seul process sur `/dev/ttyACM0` (`meshia.service`). MP MeshCore, FTS5, adverts, pas de second script série.

## Comportement (1.18)

- ACL nœuds (`noeuds.db`, chmod 600, hors git) **avant** toute question : inconnu → MP « Inscription en attente. » ; autorisé → flux ci-dessous ; refusé → « Accès refusé. » une fois, puis silence. Admin : `/meshia/noeuds`.
- `aide` / `?` / `help` / `liste` : liste des sujets. `zzzz` : « Rien trouvé. Sujets : … ».
- Un MATCH : la fiche (Ollama si `MESHIA_LLM=1`, sinon brut), découpée 130 o / 3 parts / pause 4 s.
- Plusieurs MATCH : un MP « Plusieurs : Titre A, Titre B. Lequel transférer ? » ; le 2e MP = le titre exact → cette fiche.
- Adverts (même process) : local `send_advert()` 1 h ; flood `send_advert(flood=True)` 2 h si `get_default_flood_scope()` contient `fr-42`.
- Série : verrou `serial.lock` ; `create_serial` None → pause 20 s, **un** retry, puis exit (pas de boucle DTR 10 s). systemd `RestartSec=30`, `StartLimitBurst=3`. USB 5 s = dernier recours.

## Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `MESHIA_SERIAL` | `/dev/ttyACM0` | port série du nœud |
| `MESHIA_DB` | `/opt/meshia/meshia.db` | base SQLite |
| `MESHIA_LLM` | `0` | `1` reformule la fiche (unité systemd force `1`) |
| `MESHIA_MAXLEN` | `130` | taille max d'un message, en octets |
| `MESHIA_MAXPARTS` | `3` | nombre max de messages par réponse |
| `MESHIA_MATCH_MAX` | `3` | titres listés si plusieurs MATCH |
| `MESHIA_PAUSE` | `4` | secondes entre deux parties |
| `MESHIA_ADVERT_LOCAL` | `3600` | advert local, secondes |
| `MESHIA_ADVERT_FLOOD` | `7200` | advert flood, secondes |
| `MESHIA_FLOOD_REGION` | `fr-42` | tag requis pour le flood |
| `MESHIA_SERIAL_PAUSE` | `20` | pause avant le retry série |
| `MESHIA_SERIAL_ESSAIS` | `2` | ouvertures max par lancement |

## Création du fichier

```bash
cd /opt/meshia && source .venv/bin/activate
nano meshia.py
```

Coller le code ci-dessous, puis Ctrl+O, Entrée, Ctrl+X.

## Code (ébauche étape 6 — historique)

Ne pas coller tel quel : le dépôt a le vrai `meshia.py` (choix de titres, adverts, verrou série, Ollama). Le listing ci-dessous reste LIMIT 1 et sans adverts.

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
