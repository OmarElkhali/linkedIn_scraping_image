# LinkedIn Scraper 🔍

Application Python / Streamlit permettant de **rechercher et analyser des profils LinkedIn** par nom, profession ou reconnaissance faciale.

---

## Fonctionnalités

| Mode | Description |
|------|-------------|
| 👤 **Nom / Prénom** | Recherche un profil par nom complet au sein d'une entreprise ou école. |
| 💼 **Profession** | Recherche des profils par intitulé de poste au sein d'une entreprise ou école. |
| 📷 **Reconnaissance faciale** | Télécharge une photo de référence et parcourt les profils LinkedIn pour identifier la personne. |

---

## Architecture

```
linkedIn_scraping_image/
├── app.py                  # Interface Streamlit (point d'entrée)
├── requirements.txt        # Dépendances Python
└── core/
    ├── __init__.py         # Exports du package
    ├── config.py           # Constantes et variables d'environnement
    ├── scraper.py          # Scraping LinkedIn via Google + Scrapling
    └── face_comparator.py  # Reconnaissance faciale (dlib / face_recognition)
```

---

## Installation

### Prérequis système

- Python 3.11+
- Pour la reconnaissance faciale : `cmake` et les outils de compilation C++

```bash
# Ubuntu / Debian
sudo apt-get install cmake build-essential

# macOS (Homebrew)
brew install cmake
```

### Installation des dépendances Python

```bash
pip install -r requirements.txt
```

> **Note** : `face_recognition` est optionnel. Si la bibliothèque n'est pas installée, les onglets *Nom* et *Profession* restent fonctionnels.

---

## Lancement

```bash
streamlit run app.py
```

L'application s'ouvre automatiquement sur `http://localhost:8501`.

---

## Configuration

Les paramètres peuvent être ajustés via des **variables d'environnement** ou directement dans `core/config.py` :

| Variable | Valeur par défaut | Description |
|----------|-------------------|-------------|
| `OUTPUT_DIR` | `output` | Dossier de sortie principal |
| `FACE_MATCH_TOLERANCE` | `0.55` | Seuil de distance faciale (0 = identique, 1 = différent) |
| `MAX_PROFILES_FOR_FACE_SEARCH` | `20` | Nombre max de profils analysés en mode visage |
| `REQUEST_DELAY` | `1.5` | Délai (s) entre deux requêtes pour éviter le rate-limiting |

Exemple :

```bash
FACE_MATCH_TOLERANCE=0.50 REQUEST_DELAY=2.0 streamlit run app.py
```

---

## Utilisation de l'interface

### Onglet « Recherche par Nom »

1. Saisissez le nom de l'**entreprise ou école**.
2. Saisissez le **nom / prénom** de la personne.
3. Cliquez sur **Rechercher**.
4. Les profils LinkedIn correspondants s'affichent sous forme de cartes cliquables.

### Onglet « Recherche par Profession »

1. Saisissez le nom de l'**entreprise ou école**.
2. Saisissez l'**intitulé de poste** (ex. *Data Scientist*, *Product Manager*).
3. Cliquez sur **Rechercher**.

### Onglet « Recherche par Visage »

1. Saisissez le nom de l'**entreprise ou école**.
2. Téléchargez une **photo de référence** claire (JPEG, PNG, WebP).
3. Cliquez sur **Rechercher et comparer**.
4. L'application scrape les profils, télécharge les photos et les compare à l'image de référence.
5. Les résultats sont triés par **score de confiance** (du plus probable au moins probable).

### Paramètres de la barre latérale

- **Nombre max de résultats** : nombre de profils Google à analyser.
- **Tolérance** : seuil de distance faciale. Diminuez la valeur pour une comparaison plus stricte.

---

## Utilisation programmatique

```python
from core.scraper import search_linkedin_profiles, scrape_linkedin_profile
from core.face_comparator import FaceComparator

# Recherche par nom
profiles = search_linkedin_profiles(
    company_or_school="Google",
    search_type="nom_prenom",
    search_value="John Doe",
    max_results=5,
)

# Scraping détaillé d'un profil
detail = scrape_linkedin_profile(profiles[0]["url"], download_photo=True)
print(detail["nom_complet"], detail["titre_professionnel"])

# Reconnaissance faciale
comparator = FaceComparator("reference.jpg", tolerance=0.50)
result = comparator.compare_with_image("target.jpg")
print(result)
# {'match': True, 'distance': 0.38, 'confidence': 62.0, 'faces_found': 1, 'error': None}
```

---

## Avertissement légal

Ce projet est fourni à des **fins éducatives uniquement**.  
Le scraping de LinkedIn peut violer les [Conditions d'utilisation de LinkedIn](https://www.linkedin.com/legal/user-agreement).  
Utilisez cet outil de manière responsable et en conformité avec les lois applicables.
