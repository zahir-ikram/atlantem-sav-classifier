"""
ConfigLoader — Chargement de la configuration depuis config.yaml et variables d'environnement.

Les variables d'environnement ont priorité sur le fichier YAML.
Si un paramètre obligatoire est absent des deux sources, une ValueError est levée
en listant tous les paramètres manquants.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class AppConfig:
    """Configuration de l'application SAV Claims Analyzer."""

    aws_region: str
    bedrock_model_id: str
    attachments_dir: Path
    output_dir: Path
    log_dir: Path
    batch_size: int


# Mapping : nom du champ → (clé YAML, variable d'environnement, valeur par défaut)
_FIELD_MAPPING: dict[str, tuple[str, str, object]] = {
    "aws_region":        ("aws_region",        "AWS_REGION",        "eu-west-1"),
    "bedrock_model_id":  ("bedrock_model_id",   "BEDROCK_MODEL_ID",  "us.anthropic.claude-sonnet-4-6"),
    "attachments_dir":   ("attachments_dir",    "ATTACHMENTS_DIR",   "./attachments"),
    "output_dir":        ("output_dir",         "OUTPUT_DIR",        "./output"),
    "log_dir":           ("log_dir",            "LOG_DIR",           "./logs"),
    "batch_size":        ("batch_size",         "BATCH_SIZE",        100),
}

# Champs dont la valeur doit être convertie en Path
_PATH_FIELDS = {"attachments_dir", "output_dir", "log_dir"}


def load_config(config_path: Path) -> AppConfig:
    """Charge la configuration depuis *config_path* (YAML) et les variables d'environnement.

    Les variables d'environnement ont priorité sur le fichier YAML.
    Les valeurs par défaut sont appliquées en dernier recours.

    Args:
        config_path: Chemin vers le fichier ``config.yaml``.

    Returns:
        Une instance :class:`AppConfig` entièrement renseignée.

    Raises:
        ValueError: Si un ou plusieurs paramètres obligatoires sont absents
            de la configuration (fichier YAML et variables d'environnement).
    """
    # 1. Lire le fichier YAML (optionnel : s'il est absent on continue avec les env vars)
    yaml_data: dict = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
            if isinstance(loaded, dict):
                yaml_data = loaded

    # 2. Résoudre chaque paramètre : env var > YAML > défaut
    resolved: dict[str, object] = {}
    missing: list[str] = []

    for field, (yaml_key, env_var, default) in _FIELD_MAPPING.items():
        env_value = os.environ.get(env_var)
        if env_value is not None:
            # Variable d'environnement présente → priorité absolue
            raw = env_value
        elif yaml_key in yaml_data and yaml_data[yaml_key] is not None:
            raw = yaml_data[yaml_key]
        elif default is not None:
            raw = default
        else:
            # Aucune source disponible pour ce champ obligatoire
            missing.append(f"{field} (env: {env_var})")
            continue

        # 3. Conversion de type
        if field in _PATH_FIELDS:
            resolved[field] = Path(str(raw))
        elif field == "batch_size":
            try:
                resolved[field] = int(raw)
            except (ValueError, TypeError):
                raise ValueError(
                    f"La valeur de 'batch_size' ('{raw}') n'est pas un entier valide."
                )
        else:
            resolved[field] = str(raw)

    # 4. Lever une erreur si des paramètres obligatoires sont manquants
    if missing:
        raise ValueError(
            "Paramètres de configuration obligatoires manquants : "
            + ", ".join(missing)
        )

    return AppConfig(
        aws_region=resolved["aws_region"],          # type: ignore[arg-type]
        bedrock_model_id=resolved["bedrock_model_id"],  # type: ignore[arg-type]
        attachments_dir=resolved["attachments_dir"],    # type: ignore[arg-type]
        output_dir=resolved["output_dir"],              # type: ignore[arg-type]
        log_dir=resolved["log_dir"],                    # type: ignore[arg-type]
        batch_size=resolved["batch_size"],              # type: ignore[arg-type]
    )
