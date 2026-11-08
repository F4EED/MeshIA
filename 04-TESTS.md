# 04 — Procédure de tests (étape 6 : mode frugal, sans LLM)

À dérouler **dans l'ordre**, une étape à la fois. Ne passer à la suivante que si le critère de validation est atteint.

## Préparation

```bash
cd /opt/meshia && source .venv/bin/activate
ls                      # doit montrer : fiches  ingest.py  meshia.py  .venv
ls fiches               # au moins 3 fichiers .md
```

## Test 1 — Indexation

```bash
python ingest.py fiches
```

**Validé si** : la sortie est `N fiches indexées` avec N égal au nombre de `.md` dans `fiches/` (git : 65 ; ThinkCentre souvent 66+).
**Sinon** : vérifier que les fiches sont en UTF-8 et que le dossier est bien `fiches/`.

## Test 2 — Recherche directe dans SQLite (sans le mesh)

```bash
sqlite3 meshia.db "SELECT titre FROM fiches"
sqlite3 meshia.db "SELECT titre FROM fiches WHERE fiches MATCH 'brulure*'"
sqlite3 meshia.db "SELECT titre, substr(contenu,1,60) FROM fiches WHERE fiches MATCH '\"eau\"*' ORDER BY bm25(fiches,5.0,1.0)"
```

**Validé si** : la requête `brulure*` renvoie la fiche « Brûlure » (même sans accent), et la recherche sur `eau` renvoie la fiche « Eau potable ».
**Sinon** : si `sqlite3` est absent, `sudo apt install sqlite3`. Si `no such module: fts5`, signaler l'erreur à l'IA.

## Test 3 — Nœud joignable

Avant de lancer le service, **remettre le nœud dans un état propre** (voir la section « pièges » du fichier 00) :

1. S'assurer qu'aucun script ne tient le port : `fuser -v /dev/ttyACM0` ne doit rien afficher.
2. Débrancher l'USB du nœud, attendre 5 secondes, rebrancher, attendre 5 secondes.
3. Vérifier que le port est revenu : `ls /dev/ttyACM*`.

Ne pas lancer de script de test intermédiaire : lancer directement `meshia.py` à l'étape suivante, pour n'ouvrir le port qu'une seule fois.

## Test 4 — Service lancé

Si `meshia.service` tourne déjà : **ne pas** lancer `python meshia.py` (un seul ACM0). Utiliser `sudo systemctl status meshia` / `journalctl -u meshia -n 30`.

Sinon, port libre, **un** lancement :

```bash
MESHIA_LLM=0 python meshia.py
```

**Validé si** : `MeshIA prête sur /dev/ttyACM0` et pas de boucle « invert dtr » toutes les 10 s.
**Sinon** :
- `create_serial` None après 2 essais : stop, USB 5 s, `start` **une** fois.
- `AttributeError` ou `TypeError` sur une méthode `mc.` : demander à l'IA de vérifier la version de `meshcore` (`pip show meshcore`) et d'adapter l'appel.

## Test 5 — Question depuis un autre nœud

Depuis le téléphone (appli companion reliée à **un autre nœud** que celui du ThinkCentre), envoyer un message **privé** à `FR42-Meshia` :

1. `aide` → réponse « Sujets : … » avec la liste des fiches.
2. `brûlure` → réponse commençant par « Brûlure : Refroidir… ».
3. `comment potabiliser l'eau` → réponse de la fiche « Eau potable ».
4. `zzzz` → réponse « Rien trouvé. Sujets : … ».
5. `blackout` → « Plusieurs : Blackout énergie, Blackout télécom. Lequel transférer ? » puis un 2e MP `Blackout télécom` → cette fiche.

**Validé si** : les réponses arrivent, et le journal affiche `Question de … :` et `Envoyé (1/N) :`.

**Sinon** :
- Le téléphone ne voit pas `FR42-Meshia` : envoyer un « advert » depuis chaque côté pour que les nœuds se découvrent, puis réessayer.
- Rien dans le terminal : le message n'arrive pas. Vérifier que c'est bien un message **privé** (pas sur un canal public), et la portée radio.
- « Contact inconnu » dans le terminal : le téléphone n'est pas dans la liste de contacts du nœud. Faire un advert depuis le téléphone, puis réessayer.

## Test 6 — Temps de réponse bout en bout

Mesurer, avec un chronomètre, le délai entre l'envoi de la question et l'arrivée du **premier** message de réponse, puis du dernier. Faire 3 essais et noter les valeurs.

**Cible indicative** : première partie en quelques secondes. Chaque partie suivante arrive environ `MESHIA_PAUSE` secondes plus tard.

## Test 7 — Troncature et limite de payload

1. Créer une fiche volontairement longue (3 à 4 phrases, plus de 400 caractères).
2. `python ingest.py fiches`, puis relancer `meshia.py` (après un rebranchement USB propre).
3. Poser la question correspondante depuis le téléphone.

**Validé si** : la réponse arrive en 3 messages au plus, aucun message n'est refusé ni coupé au milieu d'un mot ou d'une lettre accentuée, et la dernière partie se termine par « … ».

**Si certains messages ne passent pas** : baisser `MESHIA_MAXLEN` (par exemple 110) :
```bash
MESHIA_MAXLEN=110 MESHIA_LLM=0 python meshia.py
```
Si les parties arrivent dans le désordre ou sont perdues, augmenter `MESHIA_PAUSE` (par exemple 6).

## Fin de l'étape 6

Cocher dans le TODO :

- [x] `python ingest.py fiches` → « N fiches indexées » (git 65 ; ThinkCentre 66+)
- [x] recherche SQLite directe OK
- [x] `meshia.service` répond depuis un autre nœud (ne pas lancer `python meshia.py` si l’unité tourne)
- [x] troncature : `MESHIA_MAXLEN=130` / `MESHIA_MAXPARTS=3` / `MESHIA_PAUSE=4`
- [x] radio plusieurs MATCH → liste de titres puis 2e MP
- [x] adverts local 1 h / flood 2 h si `fr-42`
- [x] série sans boucle DTR (`serial.lock`, 2 essais)

Étapes 7 (Ollama) et 8 (systemd) : faites. Portail `meshia-web.service` : fait.

## Rappels

- Une seule ouverture du port série par essai ; rebrancher l'USB après un blocage.
- Ctrl+C arrête `meshia.py`.
- Toujours coller les fichiers de code via `nano`, jamais via un heredoc indenté.
