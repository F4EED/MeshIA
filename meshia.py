import asyncio, json, logging, os, re, sqlite3, sys, unicodedata, urllib.error, urllib.request
from meshcore import MeshCore, EventType
from noeuds import decision_mp, marquer_refuse_notifie

PORT = os.environ.get("MESHIA_SERIAL", "/dev/ttyACM0")
DB = os.environ.get("MESHIA_DB", "/opt/meshia/meshia.db")
LLM = os.environ.get("MESHIA_LLM", "0") == "1"
LLM_MODEL = os.environ.get("MESHIA_MODEL", "qwen2.5:0.5b")
LLM_URL = os.environ.get("MESHIA_OLLAMA", "http://127.0.0.1:11434/api/generate")
LLM_TIMEOUT = float(os.environ.get("MESHIA_LLM_TIMEOUT", "45"))
MAX_OCTETS = int(os.environ.get("MESHIA_MAXLEN", "130"))
MAX_PARTS = int(os.environ.get("MESHIA_MAXPARTS", "3"))
PAUSE = float(os.environ.get("MESHIA_PAUSE", "4"))
MATCH_RADIO_MAX = max(1, int(os.environ.get("MESHIA_MATCH_MAX", "3")))
ADVERT_LOCAL_S = float(os.environ.get("MESHIA_ADVERT_LOCAL", "3600"))
ADVERT_FLOOD_S = float(os.environ.get("MESHIA_ADVERT_FLOOD", "7200"))
ADVERT_PREMIER_S = float(os.environ.get("MESHIA_ADVERT_PREMIER", "15"))
REGION_FLOOD = (os.environ.get("MESHIA_FLOOD_REGION", "fr-42") or "fr-42").strip().lower()
SERIAL_PAUSE = float(os.environ.get("MESHIA_SERIAL_PAUSE", "20"))
SERIAL_ESSAIS = max(1, int(os.environ.get("MESHIA_SERIAL_ESSAIS", "2")))
SERIAL_LOCK = os.environ.get("MESHIA_SERIAL_LOCK", "/opt/meshia/serial.lock")
_SERIAL_LOCK_FD = None

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


def _type_ev(ev):
    t = getattr(ev, "type", None)
    return getattr(t, "value", t)


def _texte_ev(ev):
    p = getattr(ev, "payload", None)
    if isinstance(p, dict):
        if p.get("text"):
            return str(p.get("text"))
        return " ".join(str(v) for v in p.values() if v not in (None, ""))
    return "" if p is None else str(p)


def _tag_region_present(texte, tag):
    tag = (tag or "").strip().lower().lstrip("#")
    if not tag:
        return False
    return re.search(r"(?<![a-z0-9])#?" + re.escape(tag) + r"(?![a-z0-9])", (texte or "").lower()) is not None


async def lire_region_noeud(mc):
    """Région du nœud, meshcore 2.3.17 : CLI region, sinon flood_scope Companion."""
    morceaux = []
    for cmd in ("region home", "region"):
        try:
            ev = await mc.commands.run_cli_command(cmd)
        except Exception as e:
            log.warning("CLI %s impossible : %s", cmd, e)
            continue
        kind = _type_ev(ev)
        txt = _texte_ev(ev)
        if kind in ("command_error", "error") or (
            hasattr(EventType, "ERROR") and getattr(ev, "type", None) == EventType.ERROR
        ):
            log.info("CLI %s non supporté sur ce firmware : %s", cmd, txt or kind)
            continue
        if txt:
            morceaux.append(txt)
            log.info("Région (%s) : %s", cmd, " | ".join(txt.splitlines()))
    if hasattr(mc.commands, "get_default_flood_scope"):
        try:
            ev = await mc.commands.get_default_flood_scope()
            kind = _type_ev(ev)
            if kind in ("command_error", "error"):
                log.warning("get_default_flood_scope erreur : %s", ev)
            else:
                p = getattr(ev, "payload", None) or {}
                nom = str((p.get("scope_name") if isinstance(p, dict) else "") or "")
                log.info("Région (flood_scope) : %s", nom or "(aucune)")
                if nom:
                    morceaux.append(nom)
        except Exception as e:
            log.warning("get_default_flood_scope impossible : %s", e)
    if morceaux:
        return "\n".join(morceaux)
    try:
        ev = await mc.commands.get_custom_vars()
    except Exception as e:
        log.warning("get_custom_vars impossible : %s", e)
        return ""
    kind = _type_ev(ev)
    txt = _texte_ev(ev)
    if kind in ("command_error", "error"):
        log.info("get_custom_vars non supporté : %s", txt or kind)
        return ""
    if txt:
        log.info("Région (custom_vars) : %s", txt)
    return txt


async def flood_si_fr42(mc):
    brut = await lire_region_noeud(mc)
    if _tag_region_present(brut, REGION_FLOOD):
        return True
    log.info(
        "Advert flood ignoré : région lue %r, tag %s absent",
        " | ".join((brut or "").splitlines()) or "(vide)",
        REGION_FLOOD,
    )
    return False


def _prendre_verrou_serie():
    """Un seul process sur ACM0 : flock non bloquant, sinon arrêt."""
    global _SERIAL_LOCK_FD
    fd = os.open(SERIAL_LOCK, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except ImportError:
        _SERIAL_LOCK_FD = fd
        return
    except OSError:
        os.close(fd)
        log.error("Port série déjà pris (verrou %s). Un seul process. Arrêt.", SERIAL_LOCK)
        raise SystemExit(1)
    _SERIAL_LOCK_FD = fd


async def ouvrir_noeud():
    """create_serial au plus SERIAL_ESSAIS fois, pause longue entre, pas de boucle DTR."""
    dernier = None
    for i in range(SERIAL_ESSAIS):
        log.info("Ouverture %s essai %d/%d (un process, pas de boucle DTR)", PORT, i + 1, SERIAL_ESSAIS)
        try:
            mc = await MeshCore.create_serial(PORT, auto_reconnect=False)
        except Exception as e:
            log.warning("create_serial exception : %s", e)
            mc = None
        if mc is not None:
            return mc
        dernier = "None"
        log.warning("create_serial None (essai %d/%d).", i + 1, SERIAL_ESSAIS)
        if i + 1 < SERIAL_ESSAIS:
            log.info("Pause %.0fs puis un seul retry.", SERIAL_PAUSE)
            await asyncio.sleep(SERIAL_PAUSE)
    log.error(
        "Nœud muet après %d essai(s) (%s). Arrêt propre. "
        "Dernier recours (pas automatique) : débrancher USB 5 s, rebrancher, "
        "puis sudo systemctl start meshia une fois.",
        SERIAL_ESSAIS,
        dernier,
    )
    raise SystemExit(1)


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.casefold().split())


def fiche_par_titre_exact(q):
    nq = _norm(q)
    if not nq:
        return None
    hits = []
    con = sqlite3.connect(DB)
    try:
        for titre, contenu in con.execute("SELECT titre, contenu FROM fiches"):
            if _norm(titre) == nq:
                hits.append((titre, contenu))
    finally:
        con.close()
    return hits[0] if len(hits) == 1 else None


def liste_choix_titres(titres):
    prefix, suffix = "Plusieurs : ", ". Lequel transférer ?"
    reserve = len(prefix.encode()) + len(suffix.encode())
    choisis = []
    for t in titres:
        essai = ", ".join(choisis + [t])
        if len(essai.encode()) + reserve <= MAX_OCTETS:
            choisis.append(t)
        elif not choisis:
            coupe = t.encode()[: max(8, MAX_OCTETS - reserve - 1)].decode("utf-8", "ignore")
            choisis.append(coupe.rstrip() + "…")
            break
        else:
            break
    return prefix + ", ".join(choisis) + suffix


def parts_pour_question(question):
    """Radio : 1 MATCH → fiche ; plusieurs → liste de titres ; 2e MP = le titre."""
    q = question.strip()
    if q.lower() in ("aide", "?", "help", "liste"):
        titres = lister_titres()
        texte = "Sujets : " + ", ".join(titres) if titres else "Aucune fiche."
        return decouper(texte, MAX_OCTETS, MAX_PARTS)
    exact = fiche_par_titre_exact(q)
    if exact:
        titre, contenu = exact
        return decouper(reformuler(q, titre, contenu), MAX_OCTETS, MAX_PARTS)
    trouves = chercher_tous(q, limite=MATCH_RADIO_MAX)
    if not trouves:
        titres = lister_titres()
        return decouper(
            "Rien trouvé. Sujets : " + ", ".join(titres[:15]),
            MAX_OCTETS,
            MAX_PARTS,
        )
    if len(trouves) == 1:
        titre, contenu = trouves[0]
        return decouper(reformuler(q, titre, contenu), MAX_OCTETS, MAX_PARTS)
    choix = liste_choix_titres([t for t, _ in trouves])
    return decouper(choix, MAX_OCTETS, 1)


def construire_reponse(question):
    return " ".join(parts_pour_question(question))


async def main():
    _prendre_verrou_serie()
    mc = await ouvrir_noeud()

    await mc.ensure_contacts()
    perdu = asyncio.Event()
    radio = asyncio.Lock()

    async def on_msg(event):
        p = event.payload
        question = (p.get("text") or "").strip()
        prefix = p.get("pubkey_prefix")
        if not question:
            return

        contact = mc.get_contact_by_key_prefix(prefix)
        if contact is None:
            try:
                async with radio:
                    await mc.commands.get_contacts()
            except Exception as e:
                log.warning("Rafraîchissement des contacts : %s", e)
            contact = mc.get_contact_by_key_prefix(prefix)

        try:
            action, texte_acl, ident, nom, pref = decision_mp(contact, prefix)
        except Exception as e:
            log.warning("ACL nœuds : %s", e)
            action, texte_acl, ident, nom, pref = "attente", "Inscription en attente.", prefix, prefix, prefix
        log.info("Question de %s (%s) : %s [%s]", nom, (ident or prefix or "")[:16], question, action)

        if action != "ok":
            if action == "silence":
                return
            if contact is None:
                log.warning("ACL %s sans contact, pas de MP (%s)", action, ident)
                return
            async with radio:
                await mc.commands.send_msg(contact, texte_acl)
            log.info("ACL %s envoyé à %s : %s", action, nom, texte_acl)
            if action == "refus":
                marquer_refuse_notifie(ident, pref)
            return

        if contact is None:
            log.warning("Contact introuvable (%s), pas de réponse", prefix)
            return

        parts = parts_pour_question(question)
        for i, part in enumerate(parts):
            async with radio:
                await mc.commands.send_msg(contact, part)
            log.info("Envoyé (%d/%d) : %s", i + 1, len(parts), part)
            if i < len(parts) - 1:
                await asyncio.sleep(PAUSE)

    async def advert_local():
        async with radio:
            ev = await mc.commands.send_advert(flood=False)
        kind = _type_ev(ev)
        if kind in ("command_error", "error"):
            log.warning("Advert local erreur : %s", ev)
        else:
            log.info("Advert local (%s)", kind or ev)

    async def advert_flood():
        async with radio:
            if not await flood_si_fr42(mc):
                return
            ev = await mc.commands.send_advert(flood=True)
        kind = _type_ev(ev)
        if kind in ("command_error", "error"):
            log.warning("Advert flood erreur : %s", ev)
        else:
            log.info("Advert flood (%s)", kind or ev)

    async def boucle_advert(nom, premier, intervalle, fn):
        await asyncio.sleep(max(0.0, premier))
        while not perdu.is_set():
            try:
                await fn()
            except Exception as e:
                log.warning("%s échec : %s", nom, e)
            try:
                await asyncio.wait_for(perdu.wait(), timeout=max(1.0, intervalle))
                return
            except asyncio.TimeoutError:
                continue

    mc.subscribe(EventType.CONTACT_MSG_RECV, on_msg)
    if hasattr(EventType, "DISCONNECTED"):
        mc.subscribe(EventType.DISCONNECTED, lambda e: perdu.set())
    await mc.start_auto_message_fetching()

    log.info("MeshIA prête sur %s (LLM=%s)", PORT, LLM)
    log.info(
        "Timers advert : local %.0fs, flood %.0fs si région %s (premier local %.0fs)",
        ADVERT_LOCAL_S,
        ADVERT_FLOOD_S,
        REGION_FLOOD,
        ADVERT_PREMIER_S,
    )
    t_local = asyncio.create_task(
        boucle_advert("Advert local", ADVERT_PREMIER_S, ADVERT_LOCAL_S, advert_local)
    )
    t_flood = asyncio.create_task(
        boucle_advert("Advert flood", ADVERT_PREMIER_S + 10, ADVERT_FLOOD_S, advert_flood)
    )
    await perdu.wait()
    t_local.cancel()
    t_flood.cancel()
    log.error("Nœud déconnecté, arrêt (systemd relancera le service)")


if __name__ == "__main__":
    asyncio.run(main())
