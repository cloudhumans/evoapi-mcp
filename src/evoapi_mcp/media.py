import base64
import mimetypes
import os
import re
from pathlib import Path
from typing import Any

from evoapi_mcp.client import EvolutionAPIError, EvolutionClient

MEDIA_TYPES_AUDIO = {"audioMessage"}

KNOWN_EXTENSIONS = {
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "application/pdf": ".pdf",
}

AUDIO_EXTENSIONS = {ext for mimetype, ext in KNOWN_EXTENSIONS.items() if mimetype.startswith("audio/")}

KNOWN_MEDIA_EXTENSIONS = set(KNOWN_EXTENSIONS.values())

MESSAGE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+")


def _validate_message_id(message_id: str) -> None:
    if not MESSAGE_ID_PATTERN.fullmatch(message_id):
        raise ValueError(
            f"message_id inválido: {message_id!r}. Use apenas letras, números, '_' e '-'."
        )


def extension_for(mimetype: str | None) -> str:
    if not mimetype:
        return ".bin"
    base = mimetype.split(";")[0].strip().lower()
    if base in KNOWN_EXTENSIONS:
        return KNOWN_EXTENSIONS[base]
    return mimetypes.guess_extension(base) or ".bin"


def _result(path: Path, payload: dict[str, Any], cached: bool) -> dict[str, Any]:
    return {
        "path": str(path),
        "mediaType": payload.get("mediaType"),
        "mimetype": payload.get("mimetype"),
        "fileName": payload.get("fileName"),
        "caption": payload.get("caption"),
        "sizeBytes": path.stat().st_size,
        "cached": cached,
    }


def _find_cached(media_dir: Path, message_id: str) -> Path | None:
    if not media_dir.exists():
        return None
    candidates = []
    for candidate in media_dir.glob(f"{message_id}.*"):
        if candidate.suffix == ".tmp":
            continue
        if candidate.suffixes[:1] == [".transcript"]:
            continue
        if candidate.stat().st_size > 0:
            candidates.append(candidate)
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda path: (path.suffix not in KNOWN_MEDIA_EXTENSIONS, path.name),
    )


def save_media(payload: dict[str, Any], media_dir: Path, message_id: str) -> dict[str, Any]:
    _validate_message_id(message_id)
    encoded = payload.get("base64") if isinstance(payload, dict) else None
    if not encoded:
        raise EvolutionAPIError(
            f"A mensagem {message_id} não devolveu mídia (mediaType={payload.get('mediaType') if isinstance(payload, dict) else None})"
        )

    media_dir = Path(media_dir).expanduser()
    cached = _find_cached(media_dir, message_id)
    if cached:
        return _result(cached, payload, cached=True)

    path = media_dir / f"{message_id}{extension_for(payload.get('mimetype'))}"
    media_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_bytes(base64.b64decode(encoded))
    os.replace(tmp_path, path)
    return _result(path, payload, cached=False)


def download_media(client: EvolutionClient, media_dir: Path, message_id: str) -> dict[str, Any]:
    message_id = message_id.strip()
    _validate_message_id(message_id)
    media_dir = Path(media_dir).expanduser()
    cached = _find_cached(media_dir, message_id)
    if cached:
        return _result(cached, {}, cached=True)

    return save_media(client.get_media_base64(message_id), media_dir, message_id)
