"""
classifier.py — Classification des réclamations SAV via AWS Bedrock (Claude claude-sonnet-4-6).

Utilise boto3 directement (invoke_model) pour envoyer description + images en base64
et obtenir les 4 champs de classification en JSON.

Retry exponentiel : 3 tentatives, délai 2^n secondes.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError

from src.data_loader import Claim
from src.image_loader import Attachment

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valeurs autorisées
# ---------------------------------------------------------------------------

ALLOWED_VALUES: dict[str, list[str]] = {
    "type_litige": [
        "Fonctionnement", "Produit Abimé", "Manque",
        "Non Conformité", "Esthétique", "Doublon", "Prix",
    ],
    "responsabilite": [
        "Fournisseur", "Fabrication", "Client",
        "Transport", "Hors Garantie", "Saisie",
    ],
    "solution": [
        "Envoi Pieces", "Envoi Vitrage", "Refabrication", "Intervention SAV",
    ],
    "precision_produit": [
        "Crémone/Serrure", "Vitrage", "Acc Quincaillerie", "Moteur",
    ],
}

CONFIDENCE_THRESHOLD = 0.5
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # secondes


# ---------------------------------------------------------------------------
# Résultat de classification
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    """Résultat de la classification d'une réclamation."""
    claim_id: str
    type_litige: str = "Indéterminé"
    type_litige_confidence: float = 0.0
    responsabilite: str = "Indéterminé"
    responsabilite_confidence: float = 0.0
    solution: str = "Indéterminé"
    solution_confidence: float = 0.0
    precision_produit: str = "Indéterminé"
    precision_produit_confidence: float = 0.0
    error: str | None = None


# ---------------------------------------------------------------------------
# Prompt système
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Tu es un expert SAV en menuiserie industrielle pour Atlantem.
Tu analyses des réclamations clients et tu les classifies selon 4 critères.
Tu réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ni après, sans backticks.

Format de réponse attendu (exactement) :
{
  "type_litige": "...",
  "responsabilite": "...",
  "solution": "...",
  "precision_produit": "..."
}

Valeurs autorisées :
- type_litige      : Fonctionnement | Produit Abimé | Manque | Non Conformité | Esthétique | Doublon | Prix
- responsabilite   : Fournisseur | Fabrication | Client | Transport | Hors Garantie | Saisie
- solution         : Envoi Pieces | Envoi Vitrage | Refabrication | Intervention SAV
- precision_produit: Crémone/Serrure | Vitrage | Acc Quincaillerie | Moteur

Choisis toujours la valeur la plus probable parmi les valeurs autorisées.
"""


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class SAVClassifier:
    """Classifie les réclamations SAV via AWS Bedrock (Claude claude-sonnet-4-6)."""

    def __init__(self, model_id: str, aws_region: str) -> None:
        self.model_id = model_id
        self.client = boto3.client("bedrock-runtime", region_name=aws_region)
        logger.info("SAVClassifier initialisé — modèle : %s, région : %s", model_id, aws_region)

    def classify(self, claim: Claim, attachments: list[Attachment]) -> ClassificationResult:
        """
        Classifie une réclamation avec ses pièces jointes.

        Effectue jusqu'à MAX_RETRIES tentatives avec backoff exponentiel.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                raw_json = self._call_bedrock(claim, attachments)
                return self._parse_response(claim.id, raw_json)
            except (ClientError, Exception) as exc:
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY ** attempt
                    logger.warning(
                        "Tentative %d/%d échouée pour %s (%s). Retry dans %ds.",
                        attempt, MAX_RETRIES, claim.id, exc, delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "Toutes les tentatives épuisées pour %s : %s", claim.id, exc
                    )
                    return ClassificationResult(
                        claim_id=claim.id,
                        error=f"Erreur Bedrock après {MAX_RETRIES} tentatives : {exc}",
                    )

        # Ne devrait jamais être atteint
        return ClassificationResult(claim_id=claim.id, error="Erreur inattendue")

    def _call_bedrock(self, claim: Claim, attachments: list[Attachment]) -> str:
        """Construit le message et appelle l'API Bedrock."""
        content: list[dict] = []

        # Texte de la réclamation
        text_block = (
            f"Type de produit : {claim.type_produit}\n"
            f"Description : {claim.description}\n"
            f"Souhait client : {claim.souhait}\n"
        )
        if claim.reperes:
            text_block += f"Repères concernés : {claim.reperes}\n"

        content.append({"type": "text", "text": text_block})

        # Pièces jointes (images uniquement — Bedrock ne supporte pas les PDF inline)
        for att in attachments:
            if att.mime_type == "image/jpeg":
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": att.mime_type,
                        "data": att.data_b64,
                    },
                })
            elif att.mime_type == "application/pdf":
                # Pour les PDF, on ajoute une note textuelle
                content.append({
                    "type": "text",
                    "text": f"[Document PDF joint : {att.filename}]",
                })

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 512,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": content}],
        }

        response = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )

        response_body = json.loads(response["body"].read())
        return response_body["content"][0]["text"]

    def _parse_response(self, claim_id: str, raw: str) -> ClassificationResult:
        """Parse la réponse JSON de Claude et valide les valeurs.

        Gère les deux formats possibles :
          - Format plat  : {"type_litige": "Fonctionnement", ...}
          - Format objet : {"type_litige": {"value": "Fonctionnement", ...}, ...}

        Supprime également les éventuels blocs ```json ... ``` avant le parsing.
        """
        # 1. Supprimer les backticks markdown (```json ... ``` ou ``` ... ```)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Retirer la première ligne (```json ou ```) et la dernière (```)
            lines = cleaned.splitlines()
            # Supprimer la ligne d'ouverture et la ligne de fermeture si elle est ```
            start = 1
            end = len(lines)
            if lines[-1].strip() == "```":
                end -= 1
            cleaned = "\n".join(lines[start:end]).strip()

        # 2. Parser le JSON
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("JSON invalide pour %s : %s | Réponse : %s", claim_id, exc, raw[:200])
            return ClassificationResult(claim_id=claim_id, error=f"JSON invalide : {exc}")

        result = ClassificationResult(claim_id=claim_id)

        for field_name in ("type_litige", "responsabilite", "solution", "precision_produit"):
            raw_value = data.get(field_name)

            # Accepter les deux formats : valeur directe ou {"value": "..."}
            if isinstance(raw_value, dict):
                value = str(raw_value.get("value", "")).strip()
            elif raw_value is not None:
                value = str(raw_value).strip()
            else:
                logger.warning("Champ '%s' absent de la réponse pour %s", field_name, claim_id)
                continue

            # Validation de la valeur
            allowed = ALLOWED_VALUES.get(field_name, [])
            if value not in allowed:
                logger.warning(
                    "Valeur '%s' non autorisée pour '%s' (réclamation %s). Marqué Indéterminé.",
                    value, field_name, claim_id,
                )
                value = "Indéterminé"

            setattr(result, field_name, value)

        return result
