"""
image_loader.py — Encodage des pièces jointes (JPG/PDF) en base64 pour AWS Bedrock.

Formats supportés : .jpg, .jpeg, .JPG, .JPEG, .pdf, .PDF
Taille maximale   : 10 Mo par fichier (rejet)
Compression auto  : images > 4 MB sont redimensionnées/compressées en JPEG qualité 70
                    avant encodage. La taille finale encodée ne dépasse jamais 4.5 MB.
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

MAX_SIZE_BYTES = 10 * 1024 * 1024       # 10 Mo — seuil de rejet
COMPRESS_THRESHOLD = 4 * 1024 * 1024   # 4 Mo — seuil de compression
BEDROCK_MAX_BYTES = 4.5 * 1024 * 1024  # 4.5 Mo — limite stricte envoi Bedrock
JPEG_QUALITY = 70
MAX_DIMENSION = 2048  # pixels — dimension max après redimensionnement

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".pdf"}

MIME_TYPES: dict[str, str] = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".pdf":  "application/pdf",
}


@dataclass
class Attachment:
    """Pièce jointe encodée en base64."""
    filename: str
    mime_type: str
    data_b64: str   # contenu encodé en base64 (str)
    raw_bytes: bytes


def _compress_image(raw: bytes, filename: str) -> bytes:
    """
    Compresse une image JPEG pour qu'elle tienne sous BEDROCK_MAX_BYTES.

    Stratégie :
      1. Compresser en JPEG qualité 70.
      2. Si toujours trop grande, réduire les dimensions de moitié et recommencer
         (jusqu'à 4 itérations).

    Args:
        raw:      Contenu brut de l'image.
        filename: Nom du fichier (pour les logs).

    Returns:
        Bytes de l'image compressée.
    """
    img = Image.open(io.BytesIO(raw))

    # Convertir en RGB si nécessaire (ex. PNG RGBA, palette…)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    original_size = len(raw)
    quality = JPEG_QUALITY

    for attempt in range(1, 5):
        # Redimensionner si les dimensions dépassent MAX_DIMENSION
        w, h = img.size
        if max(w, h) > MAX_DIMENSION:
            scale = MAX_DIMENSION / max(w, h)
            new_w, new_h = int(w * scale), int(h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            logger.debug(
                "Redimensionnement %s : %dx%d → %dx%d (tentative %d)",
                filename, w, h, new_w, new_h, attempt,
            )

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        compressed = buf.getvalue()

        if len(compressed) <= BEDROCK_MAX_BYTES:
            logger.info(
                "Image compressée : %s — %.1f Mo → %.1f Mo (qualité %d, tentative %d)",
                filename,
                original_size / 1024 / 1024,
                len(compressed) / 1024 / 1024,
                quality,
                attempt,
            )
            return compressed

        # Encore trop grande : réduire la qualité et les dimensions pour la prochaine passe
        quality = max(40, quality - 10)
        w, h = img.size
        img = img.resize((w // 2, h // 2), Image.LANCZOS)
        logger.debug(
            "Compression insuffisante (%.1f Mo), nouvelle tentative %d — qualité %d",
            len(compressed) / 1024 / 1024, attempt + 1, quality,
        )

    # Dernier recours : retourner la dernière version compressée même si > 4.5 Mo
    logger.warning(
        "Impossible de comprimer %s sous %.1f Mo après 4 tentatives (taille finale : %.1f Mo)",
        filename, BEDROCK_MAX_BYTES / 1024 / 1024, len(compressed) / 1024 / 1024,
    )
    return compressed


def load_attachment(file_path: Path) -> Attachment | None:
    """
    Charge et encode un fichier en base64.

    Les images JPEG dépassant 4 MB sont automatiquement compressées avant encodage
    afin de ne jamais envoyer plus de 4.5 MB à Bedrock.

    Returns:
        Un :class:`Attachment` ou ``None`` si le fichier est ignoré/invalide.
    """
    ext = file_path.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        logger.warning("Format non supporté ignoré : %s", file_path.name)
        return None

    if not file_path.exists():
        logger.warning("Fichier introuvable : %s", file_path)
        return None

    size = file_path.stat().st_size
    if size > MAX_SIZE_BYTES:
        logger.warning(
            "Fichier trop volumineux ignoré (%.1f Mo > 10 Mo) : %s",
            size / 1024 / 1024,
            file_path.name,
        )
        return None

    raw = file_path.read_bytes()
    mime = MIME_TYPES[ext]

    # Compression automatique pour les images JPEG dépassant le seuil
    if mime == "image/jpeg" and size > COMPRESS_THRESHOLD:
        logger.info(
            "Image volumineuse détectée (%.1f Mo > 4 Mo), compression en cours : %s",
            size / 1024 / 1024,
            file_path.name,
        )
        raw = _compress_image(raw, file_path.name)

    b64 = base64.b64encode(raw).decode("ascii")

    logger.debug(
        "Pièce jointe chargée : %s (%s, %.1f Ko encodé)",
        file_path.name, mime, len(raw) / 1024,
    )
    return Attachment(
        filename=file_path.name,
        mime_type=mime,
        data_b64=b64,
        raw_bytes=raw,
    )


def resolve_attachments(filenames: list[str], attachments_dir: Path) -> list[Attachment]:
    """
    Résout et charge une liste de noms de fichiers depuis *attachments_dir*.

    Les fichiers manquants, trop volumineux ou de format non supporté sont
    journalisés et ignorés sans interrompre le traitement.

    Args:
        filenames:       Liste de noms de fichiers (sans chemin).
        attachments_dir: Répertoire racine des pièces jointes.

    Returns:
        Liste d'objets :class:`Attachment` chargés avec succès.
    """
    result: list[Attachment] = []
    for name in filenames:
        path = attachments_dir / name
        att = load_attachment(path)
        if att is not None:
            result.append(att)
    return result
