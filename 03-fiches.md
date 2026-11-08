# 03 — Les fiches Markdown

Corpus git : **65** fichiers. ThinkCentre : **66+** (saisies portail). Radio : si plusieurs titres MATCH, MeshIA envoie la liste et attend le titre. Portail : affiche toutes les MATCH.

## Format

Une fiche = un fichier `.md` dans `/opt/meshia/fiches/`, un seul sujet.

```
# Titre court
Phrase essentielle en tête (l'action la plus importante).
Compléments, un par ligne.
```

Règles pour que ça marche bien sur un mesh :

- **Le titre est un mot-clé que l'utilisateur taperait** (« Brûlure », « Eau », « Radio »). Il pèse 5 fois plus que le contenu dans la recherche.
- **L'essentiel dans les ~120 premiers caractères.** La réponse est découpée en 3 messages de ~130 octets au plus, et le reste est coupé.
- Phrases courtes, pas de tableaux, pas de liens, pas d'emojis.
- Mettre dans le contenu les mots que les gens utiliseront aussi (synonymes, variantes) : la recherche est basée sur les mots présents dans la fiche.
- Les accents sont ignorés à la recherche, inutile de s'en préoccuper.

## Création avec nano

```bash
cd /opt/meshia
nano fiches/brulure.md
```

Coller le texte de la fiche, puis Ctrl+O, Entrée, Ctrl+X.

## Fiches d'exemple (à relire et valider avant usage réel)

> Ces textes sont des points de départ. Il faut les relire, les adapter et les valider (idéalement avec une source officielle ou une personne formée) avant de s'en servir pour de vrai.

### `fiches/brulure.md`

```
# Brûlure
Refroidir 10-20 min sous l'eau tiède (pas glacée). Ne pas percer les cloques. Couvrir proprement.
Si étendue, visage, mains ou enfant : appeler le 15.
```

### `fiches/saignement.md`

```
# Saignement
Appuyer fort et en continu avec un linge propre sur la plaie. Ne pas retirer le linge, en ajouter par-dessus.
Si le saignement ne s'arrête pas : appeler le 15 ou le 112.
```

### `fiches/eau.md`

```
# Eau potable
Filtrer l'eau trouble, puis la faire bouillir 1 minute à gros bouillons (3 minutes en altitude).
Laisser refroidir à couvert. Stocker dans un récipient propre fermé.
```

### `fiches/radio.md`

```
# Radio MeshCore
Envoyer un message privé à FR42-Meshia. Taper aide pour voir les sujets.
Une réponse arrive en 1 à 3 messages courts. Patienter quelques secondes entre chaque.
```

### `fiches/urgence.md`

```
# Urgence
En France : 15 (SAMU), 18 (pompiers), 112 (urgence européenne). Donner le lieu exact, le nombre de victimes, l'état.
Ne pas raccrocher avant d'y être invité.
```

## Ajouter d'autres sujets

Un sujet = un fichier. Pour une fiche portant sur un sujet précis du TODO (par exemple « GPW »), appliquer le même format : titre = le mot que les gens taperont, essentiel en tête.

## Après chaque modification

Toujours ré-indexer :

```bash
cd /opt/meshia && source .venv/bin/activate
python ingest.py fiches
```

Puis relancer `meshia.py` pour qu'il relise la base (il ouvre la base à chaque question, donc un redémarrage n'est en réalité pas nécessaire, mais c'est plus sûr pour les tests).
