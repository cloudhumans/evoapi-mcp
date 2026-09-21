import base64
import mimetypes
import os
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


def extension_for(mimetype: str | None) -> str:
    if not mimetype:
        return ".bin"
    base = mimetype.split(";")[0].strip().lower()
    if base in KNOWN_EXTENSIONS:
        return KNOWN_EXTENSIONS[base]
    return mimetypes.guess_extension(base) or ".bin"


def _size_bytes(payload: dict[str, Any], fallback: int) -> int:
    size = (payload.get("size") or {}).get("fileLength")
    if isinstance(size, dict):
        size = size.get("low")
    try:
        return int(size) if size is not None else fallback
    except (TypeError, ValueError):
        return fallback


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
    for candidate in media_dir.glob(f"{message_id}.*"):
        if candidate.suffix != ".txt" and candidate.suffix != ".tmp" and candidate.stat().st_size > 0:
            return candidate
    return None


def save_media(payload: dict[str, Any], media_dir: Path, message_id: str) -> dict[str, Any]:
    encoded = payload.get("base64") if isinstance(payload, dict) else None
    if not encoded:
        raise EvolutionAPIError(
            f"A mensagem {message_id} não devolveu mídia (mediaType={payload.get('mediaType') if isinstance(payload, dict) else None})"
        )

    media_dir = Path(media_dir).expanduser()
    path = media_dir / f"{message_id}{extension_for(payload.get('mimetype'))}"
    if path.exists() and path.stat().st_size > 0:
        return _result(path, payload, cached=True)

    media_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_bytes(base64.b64decode(encoded))
    os.replace(tmp_path, path)
    return _result(path, payload, cached=False)


def download_media(client: EvolutionClient, media_dir: Path, message_id: str) -> dict[str, Any]:
    message_id = message_id.strip()
    media_dir = Path(media_dir).expanduser()
    cached = _find_cached(media_dir, message_id)
    if cached:
        return _result(cached, {}, cached=True)

    return save_media(client.get_media_base64(message_id), media_dir, message_id)
