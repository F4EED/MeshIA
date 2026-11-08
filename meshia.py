import asyncio, json, logging, os, re, sqlite3, urllib.error, urllib.request
from meshcore import MeshCore, EventType

PORT = os.environ.get("MESHIA_SERIAL", "/dev/ttyACM0")
DB = os.environ.get("MESHIA_DB", "/opt/meshia/meshia.db")
LLM = os.environ.get("MESHIA_LLM", "0") == "1"
LLM_MODEL = os.environ.get("MESHIA_MODEL", "qwen2.5:0.5b")
LLM_URL = os.environ.get("MESHIA_OLLAMA", "http://127.0.0.1:11434/api/generate")
LLM_TIMEOUT = float(os.environ.get("MESHIA_LLM_TIMEOUT", "45"))
MAX_OCTETS = int(os.environ.get("MESHIA_MAXLEN", "130"))
MAX_PARTS = int(os.environ.get("MESHIA_MAXPARTS", "3"))
PAUSE = float(os.environ.get("MESHIA_PAUSE", "4"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("meshia")

MOTS_VIDES = {
    "les", "des", "une", "est", "que", "qui", "quoi", "comment", "pour", "dans",
    "sur", "avec", "pas", "par", "aux", "ces", "ses", "mon", "ton", "son", "mes",
    "tes", "nous", "vous", "ils", "elles", "faire", "fait", "dois", "peut", "puis",
    "the", "and",
}


def _requete_fts(question):
    mots = [m for m in re.findall(r"\w+", question.lower())
            if len(m) >= 3 and m not in MOTS_VIDES]
    if not mots:
        return None
    return " OR ".join(f'"{m}"*' for m in mots)


def chercher(question):
    lignes = chercher_tous(question, limite=1)
    return lignes[0] if lignes else None


def chercher_tous(question, limite=20):
    requete = _requete_fts(question)
    if not requete:
        return []
    lim = max(1, int(limite))
    con = sqlite3.connect(DB)
    try:
        return con.execute(
            "SELECT titre, contenu FROM fiches WHERE fiches MATCH ? "
            "ORDER BY bm25(fiches, 5.0, 1.0) LIMIT ?",
            (requete, lim),
        ).fetchall()
    finally:
        con.close()


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


def reformuler(question, titre, contenu):
    brut = f"{titre} : {contenu}"
    if not LLM:
        return brut
    prompt = (
        "Reformule UNIQUEMENT la fiche pour repondre a la question. "
        "N'ajoute aucun fait absent de la fiche. "
        "Francais, phrases courtes, sans liste ni emoji. "
        "Maximum 350 caracteres.\n"
        f"Question: {question}\n"
        f"Fiche ({titre}): {contenu}\n"
        "Reponse:"
    )
    body = json.dumps(
        {
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 160},
        }
    ).encode()
    req = urllib.request.Request(
        LLM_URL, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        texte = (data.get("response") or "").strip()
        if not texte:
            log.warning("Ollama vide, fallback fiche")
            return brut
        return texte
    except Exception as e:
        log.warning("Ollama indisponible (%s), fallback fiche", e)
        return brut


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
    return reformuler(q, titre, contenu)


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


if __name__ == "__main__":
    asyncio.run(main())
