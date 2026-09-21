import os
from pathlib import Path
from typing import Any

import requests

from evoapi_mcp.client import EvolutionClient
from evoapi_mcp.config import EvolutionConfig
from evoapi_mcp.media import MEDIA_TYPES_AUDIO, download_media

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
    return audio_path.with_suffix(".txt")


def _write_atomic(path: Path, text: str) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)


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
    if media_type is not None and media_type not in MEDIA_TYPES_AUDIO:
        raise TranscriptionError(
            f"A mensagem {message_id} é {media_type}, não um áudio. Use download_media pra esse tipo."
        )

    audio_path = Path(media["path"])
    transcript_path = _transcript_path(audio_path)
    result: dict[str, Any] = {
        "messageId": message_id,
        "model": config.openai_transcribe_model,
        "language": language,
        "audioPath": str(audio_path),
        "transcriptPath": str(transcript_path),
    }

    if transcript_path.exists():
        result["text"] = transcript_path.read_text(encoding="utf-8")
        result["cached"] = True
        return result

    text = transcribe_file(audio_path, config.openai_api_key, config.openai_transcribe_model, language)
    _write_atomic(transcript_path, text)
    result["text"] = text
    result["cached"] = False
    return result
