import json
import os
from pathlib import Path
from typing import Any

import requests

from evoapi_mcp.client import EvolutionClient
from evoapi_mcp.config import EvolutionConfig
from evoapi_mcp.media import AUDIO_EXTENSIONS, MEDIA_TYPES_AUDIO, download_media

OPENAI_TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"
MISSING_KEY_MESSAGE = (
    "OPENAI_API_KEY não configurada. Defina no bloco \"env\" do ~/.claude/settings.json "
    "(mesmo lugar usado pelo plugin ch-shared) ou no .env do evoapi-mcp e reinicie a sessão."
)


class TranscriptionError(Exception):
    pass


def transcribe_file(
    audio_path: Path,
    api_key: str,
    model: str,
    language: str | None = None,
    timeout: int = 120,
) -> str:
    data: dict[str, str] = {"model": model, "response_format": "json"}
    if language:
        data["language"] = language

    with open(audio_path, "rb") as handle:
        response = requests.post(
            OPENAI_TRANSCRIPTIONS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            data=data,
            files={"file": (Path(audio_path).name, handle)},
            timeout=timeout,
        )

    if response.status_code >= 400:
        raise TranscriptionError(
            f"OpenAI respondeu HTTP {response.status_code} ao transcrever {Path(audio_path).name}: {response.text[:300]}"
        )

    try:
        text = response.json().get("text")
    except ValueError:
        text = None
    if text is None:
        raise TranscriptionError("OpenAI não devolveu o campo text na transcrição")
    return text


def _transcript_path(audio_path: Path) -> Path:
    return audio_path.parent / f"{audio_path.stem}.transcript.txt"


def _transcript_meta_path(audio_path: Path) -> Path:
    return audio_path.parent / f"{audio_path.stem}.transcript.json"


def _write_atomic(path: Path, text: str) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)


def _read_meta(meta_path: Path) -> dict[str, Any] | None:
    if not meta_path.exists():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def transcribe_message(
    client: EvolutionClient,
    config: EvolutionConfig,
    message_id: str,
    language: str | None = None,
) -> dict[str, Any]:
    if not config.openai_api_key:
        raise TranscriptionError(MISSING_KEY_MESSAGE)

    media = download_media(client, config.media_dir, message_id)
    media_type = media.get("mediaType")
    audio_path = Path(media["path"])

    if media_type is not None:
        if media_type not in MEDIA_TYPES_AUDIO:
            raise TranscriptionError(
                f"A mensagem {message_id} é {media_type}, não um áudio. Use download_media pra esse tipo."
            )
    elif audio_path.suffix not in AUDIO_EXTENSIONS:
        kind = audio_path.suffix.lstrip(".") or "desconhecido"
        raise TranscriptionError(
            f"A mensagem {message_id} está em cache como .{kind}, não um áudio. Use download_media pra esse tipo."
        )

    transcript_path = _transcript_path(audio_path)
    meta_path = _transcript_meta_path(audio_path)
    result: dict[str, Any] = {
        "messageId": message_id,
        "model": config.openai_transcribe_model,
        "language": language,
        "audioPath": str(audio_path),
        "transcriptPath": str(transcript_path),
    }

    if transcript_path.exists():
        cached_meta = _read_meta(meta_path)
        if cached_meta is None:
            result["text"] = transcript_path.read_text(encoding="utf-8")
            result["cached"] = True
            result["model"] = None
            result["language"] = None
            return result
        if cached_meta.get("model") == config.openai_transcribe_model and cached_meta.get("language") == language:
            result["text"] = transcript_path.read_text(encoding="utf-8")
            result["cached"] = True
            result["model"] = cached_meta.get("model")
            result["language"] = cached_meta.get("language")
            return result

    text = transcribe_file(audio_path, config.openai_api_key, config.openai_transcribe_model, language)
    _write_atomic(transcript_path, text)
    _write_atomic(
        meta_path,
        json.dumps({"model": config.openai_transcribe_model, "language": language}, ensure_ascii=False),
    )
    result["text"] = text
    result["cached"] = False
    return result


def _audio_seconds(record: dict[str, Any]) -> int | None:
    audio = (record.get("message") or {}).get("audioMessage") or {}
    seconds = audio.get("seconds")
    return int(seconds) if isinstance(seconds, (int, float)) else None


def transcribe_chat_audios(
    client: EvolutionClient,
    config: EvolutionConfig,
    chat: str,
    limit: int = 50,
    page: int = 1,
    language: str | None = None,
    max_audios: int = 10,
    include_own: bool = False,
) -> dict[str, Any]:
    if not config.openai_api_key:
        raise TranscriptionError(MISSING_KEY_MESSAGE)

    found = client.find_messages(chat_id=chat, limit=limit, page=page)
    block = found.get("messages") if isinstance(found, dict) else {}
    records = block.get("records") if isinstance(block, dict) else []
    records = records if isinstance(records, list) else []

    audios: list[dict[str, Any]] = []
    skipped_own = 0
    skipped_over_cap = 0
    for record in records:
        if record.get("messageType") != "audioMessage":
            continue
        key = record.get("key") or {}
        from_me = bool(key.get("fromMe"))
        if from_me and not include_own:
            skipped_own += 1
            continue
        if len(audios) >= max_audios:
            skipped_over_cap += 1
            continue

        item: dict[str, Any] = {
            "messageId": key.get("id"),
            "timestamp": record.get("messageTimestamp"),
            "fromMe": from_me,
            "pushName": record.get("pushName"),
            "seconds": _audio_seconds(record),
        }
        try:
            transcribed = transcribe_message(client, config, key["id"], language)
            item["text"] = transcribed["text"]
            item["cached"] = transcribed["cached"]
        except Exception as error:
            item["error"] = str(error)
        audios.append(item)

    return {
        "chatResolution": block.get("chatResolution") if isinstance(block, dict) else None,
        "scanned": len(records),
        "pages": block.get("pages") if isinstance(block, dict) else None,
        "currentPage": block.get("currentPage") if isinstance(block, dict) else page,
        "audios": audios,
        "skipped_own": skipped_own,
        "skipped_over_cap": skipped_over_cap,
    }
