# Document de Design — SAV Claims Analyzer

## Vue d'ensemble

Le système est une application Python en ligne de commande qui orchestre un agent IA (Strands Agents SDK + AWS Bedrock Claude claude-sonnet-4-6) pour classifier automatiquement les réclamations SAV d'Atlantem. Il lit un CSV d'entrée, résout les pièces jointes associées, soumet chaque réclamation à l'agent, puis produit un CSV enrichi avec les quatre champs de classification.

---

## Architecture générale

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI (main.py)                        │
│              python main.py --input claims.csv              │
└────────────────────────┬────────────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │   ConfigLoader      │  YAML + env vars
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │   CSVReader         │  détection encodage, validation
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  AttachmentResolver │  JPG/PDF, taille, chemin
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  BatchProcessor     │  lots de N réclamations
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  ClassificationAgent│  Strands Agents SDK
              │  (AWS Bedrock)      │  retry exponentiel
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  ResponseParser     │  JSON → ClassificationResult
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  CSVWriter          │  UTF-8 BOM, colonnes enrichies
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  Logger             │  fichier horodaté, 90 jours
              └─────────────────────┘
```

---

## Composants

### 1. ConfigLoader (`config.py`)

Charge la configuration depuis `config.yaml` et les variables d'environnement (priorité aux variables d'environnement).

**Paramètres configurables :**
| Paramètre | Env var | Défaut |
|---|---|---|
| `aws_region` | `AWS_REGION` | `eu-west-1` |
| `bedrock_model_id` | `BEDROCK_MODEL_ID` | `us.anthropic.claude-sonnet-4-6` |
| `attachments_dir` | `ATTACHMENTS_DIR` | `./attachments` |
| `output_dir` | `OUTPUT_DIR` | `./output` |
| `log_dir` | `LOG_DIR` | `./logs` |
| `batch_size` | `BATCH_SIZE` | `100` |

**Dataclass :**
```python
@dataclass
class AppConfig:
    aws_region: str
    bedrock_model_id: str
    attachments_dir: Path
    output_dir: Path
    log_dir: Path
    batch_size: int
```

---

### 2. CSVReader (`csv_reader.py`)

Lit et valide le CSV d'entrée.

**Colonnes obligatoires :** `id`, `description`, `product_type`  
**Colonne optionnelle :** `attachments` (chemins séparés par `|`)

**Fonctions clés :**
```python
def detect_encoding(file_path: Path) -> str: ...
def read_claims(file_path: Path) -> list[Claim]: ...
```

**Dataclass Claim :**
```python
@dataclass
class Claim:
    id: str
    description: str
    product_type: str
    attachments: list[str]  # chemins relatifs
    raw_row: dict           # ligne originale complète
```

---

### 3. AttachmentResolver (`attachment_resolver.py`)

Résout et charge les pièces jointes pour chaque réclamation.

**Règles :**
- Formats acceptés : `.jpg`, `.jpeg`, `.pdf`
- Taille max : 10 Mo
- Fichier manquant → log warning, continuer sans
- Format non supporté → log warning, ignorer

**Fonctions clés :**
```python
def resolve(claim: Claim, attachments_dir: Path) -> list[Attachment]: ...
```

**Dataclass Attachment :**
```python
@dataclass
class Attachment:
    path: Path
    mime_type: str          # image/jpeg ou application/pdf
    content: bytes
```

---

### 4. ClassificationAgent (`agent.py`)

Encapsule l'appel à Strands Agents SDK et AWS Bedrock.

**Prompt système :**
Le prompt instruit l'agent de retourner un JSON structuré avec les 4 champs de classification et leurs scores de confiance, en choisissant exclusivement parmi les valeurs autorisées.

**Format de réponse attendu :**
```json
{
  "type_litige": {"value": "Fonctionnement", "confidence": 0.92},
  "responsabilite": {"value": "Fabrication", "confidence": 0.85},
  "solution": {"value": "Refabrication", "confidence": 0.88},
  "precision_produit": {"value": "Crémone/Serrure", "confidence": 0.90}
}
```

**Retry :** 3 tentatives, délai exponentiel de base 2 secondes (`2^n` secondes).

**Fonctions clés :**
```python
def classify(claim: Claim, attachments: list[Attachment]) -> ClassificationResult: ...
```

---

### 5. ResponseParser (`parser.py`)

Parse et valide la réponse JSON de l'agent.

**Valeurs autorisées :**
```python
ALLOWED_VALUES = {
    "type_litige": ["Fonctionnement", "Produit Abimé", "Manque", "Non Conformité",
                    "Esthétique", "Doublon", "Prix"],
    "responsabilite": ["Fournisseur", "Fabrication", "Client", "Transport",
                       "Hors Garantie", "Saisie"],
    "solution": ["Envoi Pieces", "Envoi Vitrage", "Refabrication", "Intervention SAV"],
    "precision_produit": ["Crémone/Serrure", "Vitrage", "Acc Quincaillerie", "Moteur"]
}
CONFIDENCE_THRESHOLD = 0.5
```

**Dataclass ClassificationResult :**
```python
@dataclass
class ClassificationResult:
    type_litige: str
    type_litige_confidence: float
    responsabilite: str
    responsabilite_confidence: float
    solution: str
    solution_confidence: float
    precision_produit: str
    precision_produit_confidence: float
    error: str | None = None
```

Si confiance < 0.5 → valeur = `"Indéterminé"`.

---

### 6. BatchProcessor (`batch_processor.py`)

Orchestre le traitement par lots.

```python
def process(
    claims: list[Claim],
    agent: ClassificationAgent,
    resolver: AttachmentResolver,
    batch_size: int
) -> list[ClassificationResult]: ...
```

Itère sur les lots, appelle l'agent pour chaque réclamation, capture les erreurs par réclamation sans interrompre le lot.

---

### 7. CSVWriter (`csv_writer.py`)

Produit le CSV de sortie.

**Colonnes ajoutées :**
`type_litige`, `type_litige_confidence`, `responsabilite`, `responsabilite_confidence`, `solution`, `solution_confidence`, `precision_produit`, `precision_produit_confidence`, `erreur`

**Nom du fichier :** `output_YYYYMMDD_HHMMSS.csv`  
**Encodage :** UTF-8 avec BOM (`utf-8-sig`)

---

### 8. Logger (`logger.py`)

Journalisation structurée par exécution.

- Fichier : `sav_analyzer_YYYYMMDD_HHMMSS.log`
- Niveau : `INFO` par défaut, `DEBUG` si `LOG_LEVEL=DEBUG`
- Contenu : stats d'exécution, réclamations à faible confiance, erreurs avec traceback

---

## Structure du projet

```
sav-claims-analyzer/
├── main.py                  # point d'entrée CLI
├── config.yaml              # configuration par défaut
├── requirements.txt         # dépendances Python
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── csv_reader.py
│   ├── attachment_resolver.py
│   ├── agent.py
│   ├── parser.py
│   ├── batch_processor.py
│   ├── csv_writer.py
│   └── logger.py
├── tests/
│   ├── __init__.py
│   ├── test_csv_reader.py
│   ├── test_attachment_resolver.py
│   ├── test_parser.py
│   ├── test_batch_processor.py
│   └── test_csv_writer.py
├── attachments/             # pièces jointes (configurable)
├── output/                  # CSV de sortie (configurable)
└── logs/                    # journaux (configurable)
```

---

## Flux de données

```
CSV_Entrée
    │
    ▼
[CSVReader] → list[Claim]
    │
    ▼
[BatchProcessor] ──► [AttachmentResolver] → list[Attachment]
    │                        │
    │                        ▼
    └──────────► [ClassificationAgent] → raw JSON
                             │
                             ▼
                    [ResponseParser] → ClassificationResult
                             │
                             ▼
                    [CSVWriter] → CSV_Sortie
                             │
                             ▼
                    [Logger] → fichier .log
```

---

## Dépendances Python

```
strands-agents>=0.1.0
boto3>=1.34.0
pyyaml>=6.0
chardet>=5.0          # détection encodage
hypothesis>=6.0       # property-based testing
pytest>=8.0
```

---

## Propriétés de correction (Property-Based Testing)

| Propriété | Description |
|---|---|
| **Round-trip** | `parse(serialize(result)) == result` pour tout `ClassificationResult` valide |
| **Valeurs contraintes** | Toute valeur classifiée ∈ ensemble autorisé ∪ `{"Indéterminé"}` |
| **Ordre préservé** | `len(output_rows) == len(input_rows)` et ordre identique |
| **Idempotence** | Même réclamation + même config → même classification |
| **Gestion erreurs** | Toute réclamation en erreur apparaît dans le CSV_Sortie avec colonne `erreur` non vide |
