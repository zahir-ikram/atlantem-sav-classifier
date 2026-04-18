# Plan d'implémentation : SAV Claims Analyzer

## Vue d'ensemble

Implémentation d'un pipeline Python en ligne de commande qui lit un CSV de réclamations SAV, résout les pièces jointes, classifie chaque réclamation via un agent IA (Strands Agents SDK + AWS Bedrock Claude claude-sonnet-4-6) et produit un CSV enrichi avec les quatre champs de classification et leurs scores de confiance.

## Tâches

- [x] 1. Initialiser la structure du projet et les dépendances
  - Créer l'arborescence `sav-claims-analyzer/` avec les dossiers `src/`, `tests/`, `attachments/`, `output/`, `logs/`
  - Créer `src/__init__.py` et `tests/__init__.py`
  - Créer `requirements.txt` avec les dépendances épinglées : `strands-agents>=0.1.0`, `boto3>=1.34.0`, `pyyaml>=6.0`, `chardet>=5.0`, `hypothesis>=6.0`, `pytest>=8.0`
  - Créer `config.yaml` avec les valeurs par défaut documentées dans le design
  - _Exigences : 6.1, 6.2_

- [ ] 2. Implémenter ConfigLoader (`src/config.py`)
  - [ ] 2.1 Implémenter la dataclass `AppConfig` et la fonction de chargement
    - Définir la dataclass `AppConfig` avec les six champs (`aws_region`, `bedrock_model_id`, `attachments_dir`, `output_dir`, `log_dir`, `batch_size`)
    - Implémenter `load_config(config_path: Path) -> AppConfig` : lire `config.yaml`, surcharger avec les variables d'environnement, valider la présence des paramètres obligatoires
    - Lever une erreur explicite listant les paramètres manquants si un champ obligatoire est absent
    - _Exigences : 6.1, 6.2, 6.3, 6.4_

  - [ ] 2.2 Écrire les tests unitaires pour ConfigLoader
    - Tester la priorité des variables d'environnement sur le fichier YAML
    - Tester l'erreur sur paramètre manquant
    - _Exigences : 6.1, 6.3_

- [ ] 3. Implémenter CSVReader (`src/csv_reader.py`)
  - [ ] 3.1 Implémenter la détection d'encodage et la lecture des réclamations
    - Définir la dataclass `Claim` (`id`, `description`, `product_type`, `attachments`, `raw_row`)
    - Implémenter `detect_encoding(file_path: Path) -> str` avec `chardet`
    - Implémenter `read_claims(file_path: Path) -> list[Claim]` : valider les colonnes obligatoires (`id`, `description`, `product_type`), ignorer et journaliser les lignes sans description, parser la colonne `attachments` (séparateur `|`)
    - Lever une erreur descriptive si le fichier est absent ou illisible
    - _Exigences : 1.1, 1.2, 1.3, 1.4_

  - [ ] 3.2 Écrire les tests unitaires pour CSVReader
    - Tester la détection d'encodage UTF-8 et Latin-1
    - Tester le rejet des lignes sans description
    - Tester l'erreur sur fichier absent
    - _Exigences : 1.2, 1.3, 1.4_

- [ ] 4. Implémenter Logger (`src/logger.py`)
  - Implémenter `setup_logger(log_dir: Path) -> logging.Logger` : créer un fichier `sav_analyzer_YYYYMMDD_HHMMSS.log` dans `log_dir`, niveau `INFO` par défaut (`DEBUG` si `LOG_LEVEL=DEBUG`), format avec horodatage
  - Ajouter une fonction `log_execution_stats(logger, stats: dict)` pour consigner le résumé d'exécution (nombre de réclamations traitées/en erreur, durée, version du modèle)
  - _Exigences : 5.1, 5.2, 5.3, 5.4_

- [ ] 5. Implémenter AttachmentResolver (`src/attachment_resolver.py`)
  - [ ] 5.1 Implémenter la résolution et le chargement des pièces jointes
    - Définir la dataclass `Attachment` (`path`, `mime_type`, `content`)
    - Implémenter `resolve(claim: Claim, attachments_dir: Path) -> list[Attachment]` : vérifier l'existence du fichier, valider le format (`.jpg`, `.jpeg`, `.pdf`), vérifier la taille (≤ 10 Mo), charger le contenu en bytes, journaliser les cas d'erreur sans interrompre le traitement
    - _Exigences : 2.1, 2.2, 2.3, 2.4_

  - [ ] 5.2 Écrire les tests unitaires pour AttachmentResolver
    - Tester le rejet des fichiers > 10 Mo
    - Tester l'ignorance des formats non supportés
    - Tester la continuité du traitement sur fichier manquant
    - _Exigences : 2.2, 2.3, 2.4_

- [ ] 6. Implémenter ResponseParser (`src/parser.py`)
  - [ ] 6.1 Implémenter le parsing et la validation de la réponse JSON de l'agent
    - Définir la dataclass `ClassificationResult` avec les huit champs de valeur/confiance et le champ `error`
    - Définir `ALLOWED_VALUES` et `CONFIDENCE_THRESHOLD = 0.5`
    - Implémenter `parse_response(raw_json: str) -> ClassificationResult` : extraire les quatre champs, valider que chaque valeur appartient à `ALLOWED_VALUES`, remplacer par `"Indéterminé"` si confiance < 0.5, retourner une erreur structurée si le schéma JSON est invalide sans lever d'exception non gérée
    - Implémenter `serialize_result(result: ClassificationResult) -> dict` pour la sérialisation
    - _Exigences : 7.1, 7.4, 7.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ] 6.2 Écrire le test de propriété : round-trip (Propriété 1)
    - **Propriété 1 : Round-trip** — `parse_response(serialize(result)) == result` pour tout `ClassificationResult` valide généré par Hypothesis
    - **Valide : Exigence 7.2**

  - [ ] 6.3 Écrire le test de propriété : valeurs contraintes (Propriété 2)
    - **Propriété 2 : Valeurs contraintes** — toute valeur dans `ClassificationResult` ∈ `ALLOWED_VALUES[field]` ∪ `{"Indéterminé"}` pour toute réponse JSON arbitraire
    - **Valide : Exigences 3.2, 3.3, 3.4, 3.5, 7.5**

  - [ ] 6.4 Écrire les tests unitaires pour ResponseParser
    - Tester le remplacement par `"Indéterminé"` quand confiance < 0.5
    - Tester le retour d'erreur structurée sur JSON invalide
    - Tester la validation des valeurs autorisées
    - _Exigences : 7.4, 7.5, 3.6_

- [ ] 7. Point de contrôle — Vérifier que tous les tests passent
  - S'assurer que tous les tests unitaires et de propriété des composants 2 à 6 passent. Interroger l'utilisateur si des questions se posent.

- [ ] 8. Implémenter ClassificationAgent (`src/agent.py`)
  - [ ] 8.1 Implémenter l'appel à Strands Agents SDK avec retry exponentiel
    - Initialiser le client Strands Agents SDK avec le modèle Bedrock configuré (`bedrock_model_id`, `aws_region`)
    - Construire le prompt système demandant un JSON structuré avec les quatre champs et leurs scores de confiance, en contraignant les valeurs aux listes autorisées
    - Implémenter `classify(claim: Claim, attachments: list[Attachment]) -> ClassificationResult` : transmettre la description, le type de produit et les pièces jointes (JPG/PDF) à l'agent, appeler `ResponseParser.parse_response` sur la réponse brute
    - Implémenter le mécanisme de retry : 3 tentatives maximum, délai `2^n` secondes entre chaque tentative, marquer la réclamation en erreur après épuisement des tentatives
    - _Exigences : 3.1, 3.7, 3.8_

  - [ ] 8.2 Écrire les tests unitaires pour ClassificationAgent (avec mock Bedrock)
    - Tester le comportement de retry sur échec Bedrock (mock)
    - Tester la transmission des pièces jointes à l'agent
    - _Exigences : 3.7, 3.8_

- [ ] 9. Implémenter BatchProcessor (`src/batch_processor.py`)
  - [ ] 9.1 Implémenter l'orchestration par lots
    - Implémenter `process(claims, agent, resolver, batch_size) -> list[ClassificationResult]` : découper `claims` en lots de `batch_size`, pour chaque réclamation appeler `resolver.resolve` puis `agent.classify`, capturer les exceptions par réclamation sans interrompre le lot, journaliser les réclamations à faible confiance (< 0.7 sur au moins un champ)
    - _Exigences : 1.5, 5.2, 5.3_

  - [ ] 9.2 Écrire le test de propriété : ordre préservé (Propriété 3)
    - **Propriété 3 : Ordre préservé** — `len(output_results) == len(input_claims)` et l'ordre des résultats correspond à l'ordre des réclamations en entrée, pour toute liste de réclamations arbitraire
    - **Valide : Exigence 4.2**

  - [ ] 9.3 Écrire le test de propriété : gestion des erreurs (Propriété 4)
    - **Propriété 4 : Gestion des erreurs** — toute réclamation dont le traitement lève une exception produit un `ClassificationResult` avec `error` non vide dans la liste de sortie
    - **Valide : Exigences 4.4, 5.3**

  - [ ] 9.4 Écrire les tests unitaires pour BatchProcessor
    - Tester la continuité du lot sur erreur d'une réclamation
    - Tester le découpage correct en lots de `batch_size`
    - _Exigences : 1.5, 5.3_

- [ ] 10. Implémenter CSVWriter (`src/csv_writer.py`)
  - [ ] 10.1 Implémenter l'écriture du CSV de sortie enrichi
    - Implémenter `write_results(claims, results, output_dir: Path) -> Path` : fusionner `raw_row` de chaque `Claim` avec les champs de `ClassificationResult`, ajouter la colonne `erreur`, nommer le fichier `output_YYYYMMDD_HHMMSS.csv`, encoder en UTF-8 avec BOM (`utf-8-sig`), préserver l'ordre des lignes
    - _Exigences : 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ] 10.2 Écrire les tests unitaires pour CSVWriter
    - Tester l'encodage UTF-8 BOM du fichier produit
    - Tester la présence de la colonne `erreur` pour les réclamations en erreur
    - Tester la préservation de l'ordre des lignes
    - _Exigences : 4.2, 4.3, 4.4_

- [ ] 11. Implémenter le point d'entrée CLI (`main.py`)
  - Implémenter `main()` avec `argparse` : argument `--input` (chemin CSV obligatoire), argument `--config` (chemin YAML optionnel, défaut `config.yaml`), argument `--output-dir` (optionnel, surcharge la config)
  - Orchestrer le pipeline complet : `load_config` → `setup_logger` → `read_claims` → `BatchProcessor.process` → `write_results` → `log_execution_stats`
  - Afficher un résumé en console à la fin (nombre de réclamations traitées, nombre d'erreurs, chemin du CSV de sortie)
  - Gérer les erreurs fatales (fichier absent, paramètre manquant) avec un message clair et un code de sortie non nul
  - _Exigences : 1.3, 4.5, 5.1, 6.1, 6.3_

- [ ] 12. Point de contrôle final — Vérifier que tous les tests passent
  - Exécuter `pytest tests/` et s'assurer que tous les tests unitaires et de propriété passent. Interroger l'utilisateur si des questions se posent.

## Notes

- Les tâches marquées `*` sont optionnelles et peuvent être ignorées pour un MVP rapide
- Chaque tâche référence les exigences spécifiques pour la traçabilité
- Les tests de propriété valident les invariants universels définis dans le design (round-trip, valeurs contraintes, ordre préservé, gestion des erreurs)
- Les tests unitaires valident les cas nominaux et les cas limites
- Les points de contrôle garantissent une validation incrémentale avant d'assembler les composants suivants
