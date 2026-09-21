# Mark-as-read, download_media e transcrição: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar ao `evoapi-mcp` as tools `mark_as_read`, `download_media`, `transcribe_audio` e `transcribe_chat_audios`, com `list_chats` passando a respeitar um marcador de leitura local.

**Architecture:** `client.py` continua sendo só a camada HTTP e ganha dois métodos (`mark_messages_read`, `get_media_base64`). A orquestração vai pra quatro módulos novos e pequenos: `read_markers.py` (estado JSON por instância), `chat_read.py` (receipts + marcador + anotação do `list_chats`), `media.py` (base64 → arquivo) e `transcription.py` (OpenAI via `requests`, com cache em disco). `server.py` só registra as tools.

**Tech Stack:** Python ≥3.10, `mcp[cli]` (FastMCP 2.11), `requests`, `pydantic-settings` 2.x, `pytest` com HTTP mockado. Sem dependência nova.

**Spec:** `docs/superpowers/specs/2026-09-20-mark-read-media-transcribe-design.md`

## Global Constraints

- **Nenhum comentário, docstring ou TODO em código novo** (regra do harness desta sessão). Descrições de tool vão em `@mcp.tool(description=...)`, não em docstring. Não apagar comentários/docstrings já existentes. Única exceção autorizada pelo Ian: as 3 linhas no docstring de `list_chats` na Task 10.
- Identificadores, nomes de arquivo e mensagens de log em inglês (CLAUDE.md). Mensagens de erro e descrições de tool que o usuário final lê seguem o padrão do repo, em pt-BR.
- Commits no formato `<emoji><type>: <descrição imperativa em minúsculas>`, < 50 chars no assunto, terminando com `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Sem dependência nova no `pyproject.toml`; versão final `1.3.0`.
- Nada de caminho fixo: todo caminho vem de `EvolutionConfig` com default expansível por `~`.
- Base64 de mídia **nunca** aparece em resposta de tool nem em log.
- Trabalhar no worktree `~/dev/evoapi-mcp-wt/mark-read`, branch `feature/mark-read-media-transcribe`. Rodar tudo com `uv run --quiet pytest -q` a partir dele. **Nunca** editar `~/dev/evoapi-mcp` (é o MCP vivo do app).
- Não rodar `git stash`. Não commitar sem os testes verdes.
- Ler `.env.example` com `git show HEAD:.env.example` (o `cat` desse arquivo é bloqueado por regra de permissão).

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `tests/conftest.py` (novo) | `FakeResponse`, `Recorder`, `make_messages`, fixtures `client`/`recorder`, helper `run`, constantes de JID e endpoints. Extraído de `tests/test_message_reading.py`. |
| `src/evoapi_mcp/config.py` (modificar) | Campos `state_dir`, `media_dir`, `openai_api_key`, `openai_transcribe_model`. |
| `src/evoapi_mcp/client.py` (modificar) | `mark_messages_read(keys)`, `get_media_base64(message_id)`. |
| `src/evoapi_mcp/read_markers.py` (novo) | `ReadMarkerStore`: JSON por instância, escrita atômica. |
| `src/evoapi_mcp/chat_read.py` (novo) | `mark_chat_read`, `annotate_chats_with_markers`. |
| `src/evoapi_mcp/media.py` (novo) | `extension_for`, `save_media`, `download_media`. |
| `src/evoapi_mcp/transcription.py` (novo) | `TranscriptionError`, `transcribe_file`, `transcribe_message`, `transcribe_chat_audios`. |
| `src/evoapi_mcp/server.py` (modificar) | 4 tools novas; `list_chats` anota com marcador. |
| `tests/test_config.py`, `tests/test_client_read_media.py`, `tests/test_read_markers.py`, `tests/test_chat_read.py`, `tests/test_media.py`, `tests/test_transcription.py`, `tests/test_server_tools.py` (novos) | Um arquivo de teste por módulo. |
| `README.md`, `.env.example`, `CHANGELOG.md`, `KNOWN_ISSUES.md`, `pyproject.toml` | Docs e versão. |

Formato de dados que atravessa os módulos (vem da Evolution, não muda):

```python
record = {
    "key": {"id": "3A35...", "fromMe": False, "remoteJid": "245814047813821@lid",
            "remoteJidAlt": "5521988007555@s.whatsapp.net", "participant": ""},
    "messageTimestamp": 1789732047,
    "pushName": "Boaz",
    "messageType": "audioMessage",
    "message": {"audioMessage": {"seconds": 105, "mimetype": "audio/ogg; codecs=opus"}},
}
find_messages_result = {"messages": {"total": 7, "pages": 1, "currentPage": 1,
                                     "records": [record, ...],
                                     "chatResolution": {"requested": "...", "jid": "...", "resolved": True}}}
chat = {"remoteJid": "...", "pushName": "...", "unreadCount": 3,
        "lastMessage": {"key": {...}, "messageTimestamp": 1789732047}}
```

---

### Task 1: Extrair fixtures de teste pra `tests/conftest.py`

**Files:**
- Create: `tests/conftest.py`
- Modify: `tests/test_message_reading.py:1-100`

**Interfaces:**
- Produces: `tests/helpers.py` com `FakeResponse`, `Recorder`, `make_messages`, `run` e as constantes `NUMBER`, `PERSONAL_JID`, `LID_JID`, `GROUP_JID`, `FIND_MESSAGES`, `FIND_CHATS`, `FIND_CONTACTS`, `SEND_TEXT`, `MARK_READ`, `GET_BASE64`, `LID_CHAT`, `OTHER_CHAT`; `tests/conftest.py` só com as fixtures `client` e `recorder`. Pytest não importa `conftest` como módulo, por isso os helpers ficam num arquivo próprio.

- [ ] **Step 1: Criar `tests/helpers.py` movendo o código**

Copie de `tests/test_message_reading.py` (linhas 1-78) tudo que não é fixture: o bloco `sys.path`, imports, constantes, `FakeResponse`, `Recorder`, `make_messages`, `LID_CHAT`, `OTHER_CHAT`, e a função `run` (linhas ~97-99). O arquivo fica assim (conteúdo idêntico ao original, só realocado):

```python
import sys
from pathlib import Path
from unittest.mock import patch

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

NUMBER = "5511999999999"
PERSONAL_JID = f"{NUMBER}@s.whatsapp.net"
LID_JID = "100000000000000@lid"
GROUP_JID = "120363000000000000@g.us"

FIND_MESSAGES = "/chat/findMessages/"
FIND_CHATS = "/chat/findChats/"
FIND_CONTACTS = "/chat/findContacts/"
SEND_TEXT = "/message/sendText/"
MARK_READ = "/chat/markMessageAsRead/"
GET_BASE64 = "/chat/getBase64FromMediaMessage/"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class Recorder:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        for fragment, payload in self.routes.items():
            if fragment in kwargs["url"]:
                return FakeResponse(payload)
        raise AssertionError(f"URL inesperada: {kwargs['url']}")

    def bodies(self, fragment):
        return [call["json"] for call in self.calls if fragment in call["url"]]

    def count(self, fragment):
        return len(self.bodies(fragment))


def make_messages(*texts, remote_jid=LID_JID, total=None):
    records = [
        {"key": {"remoteJid": remote_jid, "fromMe": False}, "message": {"conversation": text}}
        for text in texts
    ]
    return {
        "messages": {
            "total": total if total is not None else len(records),
            "pages": 1,
            "currentPage": 1,
            "records": records,
        }
    }


LID_CHAT = {
    "remoteJid": LID_JID,
    "pushName": None,
    "lastMessage": {"key": {"remoteJid": LID_JID, "remoteJidAlt": PERSONAL_JID}},
}
OTHER_CHAT = {"remoteJid": "5500000000000@s.whatsapp.net", "pushName": "Outra Pessoa"}


def run(recorder_obj, call):
    with patch("evoapi_mcp.client.requests.request", side_effect=recorder_obj):
        return call()
```

Confira antes de copiar: se `FakeResponse`/`Recorder` do arquivo original tiverem algo a mais (por exemplo campos usados pelos testes do PR #2), preserve.

- [ ] **Step 2: Criar `tests/conftest.py`**

```python
import pytest

from helpers import Recorder
from evoapi_mcp.client import EvolutionClient
from evoapi_mcp.config import EvolutionConfig


@pytest.fixture
def client():
    config = EvolutionConfig(
        base_url="http://evolution.test",
        api_token="test-token",
        instance_name="test-instance",
    )
    return EvolutionClient(config)


@pytest.fixture
def recorder():
    def build(routes):
        return Recorder(routes)

    return build
```

`from helpers import ...` funciona porque pytest, com `rootdir`/`testpaths = ["tests"]` e sem `__init__.py`, insere `tests/` no `sys.path` (rootdir-based). Se der `ModuleNotFoundError: helpers`, crie `tests/__init__.py` vazio e troque pra `from tests.helpers import ...` em todos os testes.

- [ ] **Step 3: Enxugar `tests/test_message_reading.py`**

Apague das linhas 1-99 tudo que foi movido e deixe no topo só:

```python
from unittest.mock import patch
from datetime import datetime, timedelta

import pytest

from helpers import (
    FIND_CHATS, FIND_CONTACTS, FIND_MESSAGES, SEND_TEXT,
    GROUP_JID, LID_JID, NUMBER, PERSONAL_JID,
    LID_CHAT, OTHER_CHAT, make_messages, run,
)
from evoapi_mcp.client import EvolutionClient, InvalidPhoneNumberError
```

Mantenha só os imports que o arquivo de fato usa (rode o teste; `pyflakes` não está instalado, então confira à mão pelo erro de `NameError`). Os testes em si não mudam.

- [ ] **Step 4: Rodar a suite**

Run: `cd ~/dev/evoapi-mcp-wt/mark-read && uv run --quiet pytest -q`
Expected: `36 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/helpers.py tests/conftest.py tests/test_message_reading.py
git commit -m "$(cat <<'EOF'
🔧maintenance: share test fixtures via conftest

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Config com diretórios e credenciais OpenAI

**Files:**
- Modify: `src/evoapi_mcp/config.py:8-58`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `EvolutionConfig.state_dir: Path`, `EvolutionConfig.media_dir: Path` (já expandidos, absolutos), `EvolutionConfig.openai_api_key: str | None`, `EvolutionConfig.openai_transcribe_model: str`.

- [ ] **Step 1: Escrever os testes**

```python
from pathlib import Path

from evoapi_mcp.config import EvolutionConfig

BASE = dict(base_url="http://evolution.test", api_token="t", instance_name="i")


def test_defaults_expand_home(monkeypatch):
    monkeypatch.delenv("EVOLUTION_STATE_DIR", raising=False)
    monkeypatch.delenv("EVOLUTION_MEDIA_DIR", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_TRANSCRIBE_MODEL", raising=False)

    config = EvolutionConfig(**BASE, _env_file=None)

    assert config.state_dir == Path.home() / ".local" / "state" / "evoapi-mcp"
    assert config.media_dir == Path.home() / "Downloads" / "whatsapp-media"
    assert config.openai_api_key is None
    assert config.openai_transcribe_model == "gpt-4o-mini-transcribe"


def test_directories_come_from_prefixed_env(monkeypatch, tmp_path):
    monkeypatch.setenv("EVOLUTION_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EVOLUTION_MEDIA_DIR", "~/media-x")

    config = EvolutionConfig(**BASE, _env_file=None)

    assert config.state_dir == tmp_path / "state"
    assert config.media_dir == Path.home() / "media-x"


def test_openai_settings_use_unprefixed_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")

    config = EvolutionConfig(**BASE, _env_file=None)

    assert config.openai_api_key == "sk-test"
    assert config.openai_transcribe_model == "whisper-1"


def test_openai_key_can_be_passed_by_field_name(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config = EvolutionConfig(**BASE, openai_api_key="sk-kw", _env_file=None)

    assert config.openai_api_key == "sk-kw"


def test_prefixed_openai_key_is_not_picked_up(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("EVOLUTION_OPENAI_API_KEY", "sk-wrong")

    config = EvolutionConfig(**BASE, _env_file=None)

    assert config.openai_api_key is None
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `uv run --quiet pytest -q tests/test_config.py`
Expected: FAIL (`AttributeError: 'EvolutionConfig' object has no attribute 'state_dir'` ou ValidationError por `extra`).

- [ ] **Step 3: Implementar em `config.py`**

Adicione `from pathlib import Path` e, dentro de `EvolutionConfig`, depois do campo `timeout`:

```python
    state_dir: Path = Field(
        default=Path("~/.local/state/evoapi-mcp"),
        description="Diretório do estado local (marcadores de leitura)"
    )
    media_dir: Path = Field(
        default=Path("~/Downloads/whatsapp-media"),
        description="Diretório onde mídia baixada é salva"
    )
    openai_api_key: str | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
        description="Chave da OpenAI usada só pela transcrição de áudio"
    )
    openai_transcribe_model: str = Field(
        default="gpt-4o-mini-transcribe",
        validation_alias="OPENAI_TRANSCRIBE_MODEL",
        description="Modelo de transcrição da OpenAI"
    )
```

E o validador (junto dos outros `@field_validator`):

```python
    @field_validator("state_dir", "media_dir")
    @classmethod
    def expand_directory(cls, v: Path) -> Path:
        return Path(v).expanduser()
```

E em `model_config`, acrescente `validate_by_name=True, validate_by_alias=True` (pydantic ≥ 2.11; permite construir `EvolutionConfig(openai_api_key=...)` nos testes mesmo com o alias).

Atenção: com `validation_alias`, o pydantic-settings lê a env var exatamente com esse nome, ignorando o `env_prefix`. Como `case_sensitive=False`, `openai_api_key` em minúsculas também casaria; o teste `test_prefixed_openai_key_is_not_picked_up` garante que `EVOLUTION_OPENAI_API_KEY` não entra.

Não altere `load_config()` além de, opcionalmente, incluir `state_dir`/`media_dir` nas linhas de log de configuração (sem logar a chave).

- [ ] **Step 4: Rodar**

Run: `uv run --quiet pytest -q`
Expected: `41 passed`

- [ ] **Step 5: Commit**

```bash
git add src/evoapi_mcp/config.py tests/test_config.py
git commit -m "$(cat <<'EOF'
✨feature: add state, media and openai settings

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Endpoints novos no `EvolutionClient`

**Files:**
- Modify: `src/evoapi_mcp/client.py` (seção `CHAT OPERATIONS`, depois de `get_messages_by_number`)
- Test: `tests/test_client_read_media.py`

**Interfaces:**
- Produces: `EvolutionClient.mark_messages_read(keys: list[dict]) -> dict` e `EvolutionClient.get_media_base64(message_id: str) -> dict`.

- [ ] **Step 1: Testes**

```python
import pytest

from helpers import GET_BASE64, MARK_READ, run
from evoapi_mcp.client import EvolutionAPIError


def test_mark_messages_read_posts_keys_under_readMessages(client, recorder):
    rec = recorder({MARK_READ: {"message": "Read messages", "read": "success"}})
    keys = [{"remoteJid": "5511999999999@s.whatsapp.net", "fromMe": False, "id": "A1"}]

    result = run(rec, lambda: client.mark_messages_read(keys))

    assert rec.bodies(MARK_READ) == [{"readMessages": keys}]
    assert result["read"] == "success"


def test_mark_messages_read_rejects_empty_list(client, recorder):
    rec = recorder({})

    with pytest.raises(ValueError):
        run(rec, lambda: client.mark_messages_read([]))

    assert rec.count(MARK_READ) == 0


def test_get_media_base64_sends_only_the_message_key(client, recorder):
    rec = recorder({GET_BASE64: {"mediaType": "audioMessage", "base64": "QUJD", "mimetype": "audio/ogg"}})

    result = run(rec, lambda: client.get_media_base64("A1"))

    assert rec.bodies(GET_BASE64) == [{"message": {"key": {"id": "A1"}}}]
    assert result["mimetype"] == "audio/ogg"


def test_get_media_base64_rejects_blank_id(client, recorder):
    rec = recorder({})

    with pytest.raises(ValueError):
        run(rec, lambda: client.get_media_base64("  "))
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `uv run --quiet pytest -q tests/test_client_read_media.py`
Expected: FAIL com `AttributeError`.

- [ ] **Step 3: Implementar**

Em `client.py`, logo após `get_messages_by_number`:

```python
    def mark_messages_read(self, keys: list[dict[str, Any]]) -> dict[str, Any]:
        if not keys:
            raise ValueError("keys não pode ser vazio")

        self._log(f"Marking {len(keys)} messages as read")

        return self._make_request(
            "POST",
            "/chat/markMessageAsRead/{instanceId}",
            data={"readMessages": keys}
        )

    def get_media_base64(self, message_id: str) -> dict[str, Any]:
        if not message_id or not message_id.strip():
            raise ValueError("message_id não pode ser vazio")

        self._log(f"Fetching media for message {message_id.strip()}")

        return self._make_request(
            "POST",
            "/chat/getBase64FromMediaMessage/{instanceId}",
            data={"message": {"key": {"id": message_id.strip()}}}
        )
```

- [ ] **Step 4: Rodar**

Run: `uv run --quiet pytest -q`
Expected: `45 passed`

- [ ] **Step 5: Commit**

```bash
git add src/evoapi_mcp/client.py tests/test_client_read_media.py
git commit -m "$(cat <<'EOF'
✨feature: add mark-read and media endpoints to client

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `ReadMarkerStore`

**Files:**
- Create: `src/evoapi_mcp/read_markers.py`
- Test: `tests/test_read_markers.py`

**Interfaces:**
- Produces:
  ```python
  class ReadMarkerStore:
      def __init__(self, state_dir: Path, instance_name: str) -> None
      path: Path
      def get(self, jid: str) -> int | None
      def get_entry(self, jid: str) -> dict | None      # {"lastMessageTimestamp": int, "markedAt": str}
      def set(self, jid: str, last_message_timestamp: int) -> dict   # devolve a entry gravada
      def all(self) -> dict[str, dict]
  ```

- [ ] **Step 1: Testes**

```python
import json
from pathlib import Path

from evoapi_mcp.read_markers import ReadMarkerStore

JID = "245814047813821@lid"


def test_get_on_missing_file_returns_none(tmp_path):
    store = ReadMarkerStore(tmp_path, "inst")

    assert store.get(JID) is None
    assert store.all() == {}
    assert not store.path.exists()


def test_set_then_get_round_trips_and_persists(tmp_path):
    store = ReadMarkerStore(tmp_path, "inst")

    entry = store.set(JID, 1789732047)

    assert entry["lastMessageTimestamp"] == 1789732047
    assert "markedAt" in entry
    assert store.get(JID) == 1789732047
    assert ReadMarkerStore(tmp_path, "inst").get(JID) == 1789732047


def test_file_is_namespaced_by_instance(tmp_path):
    ReadMarkerStore(tmp_path, "a").set(JID, 1)
    ReadMarkerStore(tmp_path, "b").set(JID, 2)

    assert ReadMarkerStore(tmp_path, "a").get(JID) == 1
    assert ReadMarkerStore(tmp_path, "b").get(JID) == 2
    assert (tmp_path / "a.read-markers.json").exists()


def test_corrupted_file_starts_empty(tmp_path):
    (tmp_path / "inst.read-markers.json").write_text("{not json")

    store = ReadMarkerStore(tmp_path, "inst")

    assert store.get(JID) is None
    store.set(JID, 5)
    assert json.loads((tmp_path / "inst.read-markers.json").read_text())["chats"][JID]["lastMessageTimestamp"] == 5


def test_write_is_atomic_and_leaves_no_tmp(tmp_path):
    store = ReadMarkerStore(tmp_path, "inst")
    store.set(JID, 1)
    store.set("x@g.us", 2)

    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []
    data = json.loads(store.path.read_text())
    assert data["version"] == 1
    assert set(data["chats"]) == {JID, "x@g.us"}


def test_creates_state_dir_on_first_write(tmp_path):
    store = ReadMarkerStore(tmp_path / "nested" / "dir", "inst")

    store.set(JID, 1)

    assert store.path.exists()
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `uv run --quiet pytest -q tests/test_read_markers.py`
Expected: FAIL `ModuleNotFoundError: evoapi_mcp.read_markers`.

- [ ] **Step 3: Implementar**

```python
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

STORE_VERSION = 1


class ReadMarkerStore:
    def __init__(self, state_dir: Path, instance_name: str) -> None:
        self.path = Path(state_dir).expanduser() / f"{instance_name}.read-markers.json"
        self._chats: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            chats = data.get("chats", {})
            return chats if isinstance(chats, dict) else {}
        except (ValueError, OSError) as error:
            print(f"[WARNING] Read markers: ignoring unreadable {self.path}: {error}", file=sys.stderr)
            return {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {"version": STORE_VERSION, "chats": self._chats}
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, self.path)

    def get(self, jid: str) -> int | None:
        entry = self._chats.get(jid)
        return entry.get("lastMessageTimestamp") if entry else None

    def get_entry(self, jid: str) -> dict | None:
        entry = self._chats.get(jid)
        return dict(entry) if entry else None

    def set(self, jid: str, last_message_timestamp: int) -> dict:
        entry = {
            "lastMessageTimestamp": int(last_message_timestamp),
            "markedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._chats[jid] = entry
        self._save()
        return dict(entry)

    def all(self) -> dict[str, dict]:
        return {jid: dict(entry) for jid, entry in self._chats.items()}
```

- [ ] **Step 4: Rodar**

Run: `uv run --quiet pytest -q`
Expected: `51 passed`

- [ ] **Step 5: Commit**

```bash
git add src/evoapi_mcp/read_markers.py tests/test_read_markers.py
git commit -m "$(cat <<'EOF'
✨feature: add local read marker store

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `mark_chat_read`

**Files:**
- Create: `src/evoapi_mcp/chat_read.py`
- Test: `tests/test_chat_read.py`

**Interfaces:**
- Consumes: `client.resolve_chat_jid_detail(chat) -> (jid, resolved)`, `client.find_messages(chat_id=..., limit=...) -> dict`, `client.find_chats(enrich_with_names=False) -> list`, `client.mark_messages_read(keys)`, `ReadMarkerStore.get/set`.
- Produces: `mark_chat_read(client, store, chat: str, page_size: int = 100) -> dict` com chaves `requested, jid, resolved, receiptsSent, phoneCleared, reason, markerTimestamp, messagesScanned`. Constantes `REASON_GROUP = "group_receipts_unsupported"`, `REASON_NOT_FOUND = "chat_not_found"`, `REASON_NOTHING_NEW = "nothing_new"`. Helper `receipt_key(key: dict) -> dict`.

- [ ] **Step 1: Testes**

```python
import pytest

from helpers import FIND_CHATS, FIND_MESSAGES, MARK_READ, GROUP_JID, LID_JID, NUMBER, PERSONAL_JID, LID_CHAT, run
from evoapi_mcp.chat_read import REASON_GROUP, REASON_NOT_FOUND, REASON_NOTHING_NEW, mark_chat_read
from evoapi_mcp.read_markers import ReadMarkerStore

OK = {"message": "Read messages", "read": "success"}


def record(msg_id, ts, from_me=False, remote_jid=LID_JID, alt=PERSONAL_JID):
    key = {"id": msg_id, "fromMe": from_me, "remoteJid": remote_jid}
    if alt:
        key["remoteJidAlt"] = alt
    return {"key": key, "messageTimestamp": ts, "message": {"conversation": msg_id}}


def page(*records):
    return {"messages": {"total": len(records), "pages": 1, "currentPage": 1, "records": list(records)}}


@pytest.fixture
def store(tmp_path):
    return ReadMarkerStore(tmp_path, "test-instance")


def test_lid_chat_sends_receipts_with_phone_jid(client, store, recorder):
    rec = recorder({FIND_MESSAGES: page(record("A", 10), record("B", 20)), MARK_READ: OK})

    result = run(rec, lambda: mark_chat_read(client, store, LID_JID))

    sent = rec.bodies(MARK_READ)[0]["readMessages"]
    assert sent == [
        {"remoteJid": PERSONAL_JID, "fromMe": False, "id": "A"},
        {"remoteJid": PERSONAL_JID, "fromMe": False, "id": "B"},
    ]
    assert result["phoneCleared"] is True
    assert result["receiptsSent"] == 2
    assert result["markerTimestamp"] == 20
    assert store.get(LID_JID) == 20


def test_number_is_resolved_to_lid_jid(client, store, recorder):
    rec = recorder({FIND_CHATS: [LID_CHAT], FIND_MESSAGES: page(record("A", 10)), MARK_READ: OK})

    result = run(rec, lambda: mark_chat_read(client, store, NUMBER))

    assert result["jid"] == LID_JID
    assert result["resolved"] is True
    assert rec.bodies(FIND_MESSAGES)[0]["where"] == {"key": {"remoteJid": LID_JID}}


def test_group_records_marker_but_sends_no_receipt(client, store, recorder):
    rec = recorder({FIND_MESSAGES: page(record("A", 10, remote_jid=GROUP_JID, alt=None))})

    result = run(rec, lambda: mark_chat_read(client, store, GROUP_JID))

    assert rec.count(MARK_READ) == 0
    assert result["phoneCleared"] is False
    assert result["reason"] == REASON_GROUP
    assert result["receiptsSent"] == 0
    assert store.get(GROUP_JID) == 10


def test_duplicate_ids_are_sent_once(client, store, recorder):
    rec = recorder({FIND_MESSAGES: page(record("A", 10), record("A", 10), record("B", 11)), MARK_READ: OK})

    result = run(rec, lambda: mark_chat_read(client, store, LID_JID))

    assert [k["id"] for k in rec.bodies(MARK_READ)[0]["readMessages"]] == ["A", "B"]
    assert result["receiptsSent"] == 2


def test_own_messages_and_already_marked_are_skipped(client, store, recorder):
    store.set(LID_JID, 15)
    rec = recorder({FIND_MESSAGES: page(record("old", 10), record("mine", 20, from_me=True), record("new", 30)), MARK_READ: OK})

    result = run(rec, lambda: mark_chat_read(client, store, LID_JID))

    assert [k["id"] for k in rec.bodies(MARK_READ)[0]["readMessages"]] == ["new"]
    assert result["markerTimestamp"] == 30


def test_nothing_new_does_not_call_api_but_advances_marker(client, store, recorder):
    store.set(LID_JID, 10)
    rec = recorder({FIND_MESSAGES: page(record("old", 5), record("mine", 12, from_me=True))})

    result = run(rec, lambda: mark_chat_read(client, store, LID_JID))

    assert rec.count(MARK_READ) == 0
    assert result["receiptsSent"] == 0
    assert result["phoneCleared"] is True
    assert result["reason"] == REASON_NOTHING_NEW
    assert store.get(LID_JID) == 12


def test_personal_jid_without_alt_is_sent_as_is(client, store, recorder):
    rec = recorder({FIND_MESSAGES: page(record("A", 10, remote_jid=PERSONAL_JID, alt=None)), MARK_READ: OK})

    run(rec, lambda: mark_chat_read(client, store, PERSONAL_JID))

    assert rec.bodies(MARK_READ)[0]["readMessages"][0]["remoteJid"] == PERSONAL_JID


def test_unresolved_number_sends_nothing_and_records_no_marker(client, store, recorder):
    rec = recorder({FIND_CHATS: [], FIND_MESSAGES: page()})

    result = run(rec, lambda: mark_chat_read(client, store, "5500000000001"))

    assert result["resolved"] is False
    assert result["reason"] == REASON_NOT_FOUND
    assert result["receiptsSent"] == 0
    assert result["phoneCleared"] is False
    assert rec.count(MARK_READ) == 0
    assert result["markerTimestamp"] is None
    assert store.get(result["jid"]) is None


def test_empty_chat_uses_no_marker(client, store, recorder):
    rec = recorder({FIND_MESSAGES: page()})

    result = run(rec, lambda: mark_chat_read(client, store, LID_JID))

    assert result["markerTimestamp"] is None
    assert store.get(LID_JID) is None
    assert result["messagesScanned"] == 0
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `uv run --quiet pytest -q tests/test_chat_read.py`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implementar `chat_read.py`**

```python
from typing import Any

from evoapi_mcp.client import GROUP_JID_SUFFIX, EvolutionClient
from evoapi_mcp.read_markers import ReadMarkerStore

REASON_GROUP = "group_receipts_unsupported"
REASON_NOT_FOUND = "chat_not_found"
REASON_NOTHING_NEW = "nothing_new"


def receipt_key(key: dict[str, Any]) -> dict[str, Any]:
    return {
        "remoteJid": key.get("remoteJidAlt") or key["remoteJid"],
        "fromMe": bool(key.get("fromMe")),
        "id": key["id"],
    }


def _records(result: Any) -> list[dict[str, Any]]:
    block = result.get("messages") if isinstance(result, dict) else None
    records = block.get("records") if isinstance(block, dict) else None
    return records if isinstance(records, list) else []


def _timestamp(record: dict[str, Any]) -> int:
    value = record.get("messageTimestamp")
    if isinstance(value, dict):
        value = value.get("low")
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _pending_keys(records: list[dict[str, Any]], marker_before: int | None) -> list[dict[str, Any]]:
    seen: set[str] = set()
    pending: list[dict[str, Any]] = []
    for record in records:
        key = record.get("key") or {}
        message_id = key.get("id")
        if not message_id or key.get("fromMe") or message_id in seen:
            continue
        if marker_before is not None and _timestamp(record) <= marker_before:
            continue
        seen.add(message_id)
        pending.append(receipt_key(key))
    return pending


def mark_chat_read(
    client: EvolutionClient,
    store: ReadMarkerStore,
    chat: str,
    page_size: int = 100,
) -> dict[str, Any]:
    jid, resolved = client.resolve_chat_jid_detail(chat)
    result: dict[str, Any] = {
        "requested": chat,
        "jid": jid,
        "resolved": resolved,
        "receiptsSent": 0,
        "phoneCleared": False,
        "reason": None,
        "markerTimestamp": None,
        "messagesScanned": 0,
    }

    records = _records(client.find_messages(chat_id=jid, limit=page_size))
    result["messagesScanned"] = len(records)

    if not resolved:
        result["reason"] = REASON_NOT_FOUND
        return result

    marker_before = store.get(jid)
    pending = _pending_keys(records, marker_before)
    is_group = jid.endswith(GROUP_JID_SUFFIX)

    if is_group:
        result["reason"] = REASON_GROUP
    elif pending:
        client.mark_messages_read(pending)
        result["receiptsSent"] = len(pending)
        result["phoneCleared"] = True
    else:
        result["reason"] = REASON_NOTHING_NEW
        result["phoneCleared"] = True

    newest = max((_timestamp(r) for r in records), default=0)
    if newest:
        store.set(jid, newest)
        result["markerTimestamp"] = newest

    return result
```

Nota sobre `_timestamp`: a Evolution devolve `messageTimestamp` como int no `findMessages`, mas em alguns payloads (ex.: dentro de `audioMessage.mediaKeyTimestamp`) aparece como `{"low", "high", "unsigned"}`. O helper aceita os dois pra não quebrar se o formato mudar.

- [ ] **Step 4: Rodar**

Run: `uv run --quiet pytest -q`
Expected: `60 passed`

- [ ] **Step 5: Commit**

```bash
git add src/evoapi_mcp/chat_read.py tests/test_chat_read.py
git commit -m "$(cat <<'EOF'
✨feature: mark chat read with receipts and local marker

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `annotate_chats_with_markers`

**Files:**
- Modify: `src/evoapi_mcp/chat_read.py`
- Test: `tests/test_chat_read.py` (acrescentar)

**Interfaces:**
- Consumes: `ReadMarkerStore.get_entry(jid)`, `client.find_messages(chat_id, limit)`, `_records`, `_timestamp` da Task 5.
- Produces: `annotate_chats_with_markers(client, store, chats: list[dict], page_size: int = 100) -> list[dict]`. Muta e devolve a mesma lista. Campos adicionados por chat: `unreadSource` (`"evolution"` | `"local_marker"`); quando há marcador: `readMarker` (a entry) e possivelmente `unreadCountIsLowerBound: True`.

- [ ] **Step 1: Testes (acrescentar ao fim de `tests/test_chat_read.py`)**

```python
from evoapi_mcp.chat_read import annotate_chats_with_markers
from evoapi_mcp.client import EvolutionAPIError


def chat(jid, unread, last_ts, last_from_me=False):
    return {
        "remoteJid": jid,
        "unreadCount": unread,
        "lastMessage": {"key": {"remoteJid": jid, "fromMe": last_from_me}, "messageTimestamp": last_ts},
    }


def test_chat_without_marker_keeps_evolution_count(client, store, recorder):
    rec = recorder({})
    chats = [chat(LID_JID, 7, 100)]

    out = run(rec, lambda: annotate_chats_with_markers(client, store, chats))

    assert out[0]["unreadCount"] == 7
    assert out[0]["unreadSource"] == "evolution"
    assert "readMarker" not in out[0]
    assert rec.count(FIND_MESSAGES) == 0


def test_marker_up_to_date_zeroes_count_without_http(client, store, recorder):
    store.set(LID_JID, 100)
    rec = recorder({})

    out = run(rec, lambda: annotate_chats_with_markers(client, store, [chat(LID_JID, 7, 100)]))

    assert out[0]["unreadCount"] == 0
    assert out[0]["unreadSource"] == "local_marker"
    assert out[0]["readMarker"]["lastMessageTimestamp"] == 100
    assert rec.count(FIND_MESSAGES) == 0


def test_newer_messages_are_counted_after_marker(client, store, recorder):
    store.set(LID_JID, 100)
    rec = recorder({FIND_MESSAGES: page(record("a", 90), record("b", 110), record("mine", 120, from_me=True), record("c", 130))})

    out = run(rec, lambda: annotate_chats_with_markers(client, store, [chat(LID_JID, 999, 130)]))

    assert out[0]["unreadCount"] == 2
    assert out[0]["unreadSource"] == "local_marker"
    assert "unreadCountIsLowerBound" not in out[0]
    assert rec.bodies(FIND_MESSAGES)[0]["offset"] == 100


def test_full_page_marks_count_as_lower_bound(client, store, recorder):
    store.set(LID_JID, 0)
    records = [record(str(i), i + 1) for i in range(3)]
    rec = recorder({FIND_MESSAGES: page(*records)})

    out = run(rec, lambda: annotate_chats_with_markers(client, store, [chat(LID_JID, 50, 3)], page_size=3))

    assert out[0]["unreadCount"] == 3
    assert out[0]["unreadCountIsLowerBound"] is True


def test_http_failure_falls_back_to_evolution_count(client, store, recorder, monkeypatch):
    store.set(LID_JID, 100)

    def boom(**kwargs):
        raise EvolutionAPIError("down")

    monkeypatch.setattr(client, "find_messages", lambda **kw: boom())

    out = annotate_chats_with_markers(client, store, [chat(LID_JID, 7, 130)])

    assert out[0]["unreadCount"] == 7
    assert out[0]["unreadSource"] == "evolution"


def test_chat_without_last_message_timestamp_recounts(client, store, recorder):
    store.set(LID_JID, 100)
    rec = recorder({FIND_MESSAGES: page(record("b", 110))})
    chats = [{"remoteJid": LID_JID, "unreadCount": 4}]

    out = run(rec, lambda: annotate_chats_with_markers(client, store, chats))

    assert out[0]["unreadCount"] == 1
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `uv run --quiet pytest -q tests/test_chat_read.py`
Expected: FAIL `ImportError: annotate_chats_with_markers`.

- [ ] **Step 3: Implementar (acrescentar em `chat_read.py`)**

```python
from evoapi_mcp.client import EvolutionAPIError


def _last_message_timestamp(chat: dict[str, Any]) -> int | None:
    last = chat.get("lastMessage") or {}
    value = last.get("messageTimestamp")
    if value is None:
        return None
    return _timestamp({"messageTimestamp": value})


def _count_unread_since(client: EvolutionClient, jid: str, marker: int, page_size: int) -> tuple[int, bool]:
    records = _records(client.find_messages(chat_id=jid, limit=page_size))
    count = sum(
        1 for r in records
        if not (r.get("key") or {}).get("fromMe") and _timestamp(r) > marker
    )
    return count, len(records) >= page_size


def annotate_chats_with_markers(
    client: EvolutionClient,
    store: ReadMarkerStore,
    chats: list[dict[str, Any]],
    page_size: int = 100,
) -> list[dict[str, Any]]:
    for chat in chats:
        jid = chat.get("remoteJid") or ""
        entry = store.get_entry(jid) if jid else None
        if not entry:
            chat["unreadSource"] = "evolution"
            continue

        marker = int(entry["lastMessageTimestamp"])
        chat["readMarker"] = entry
        last_ts = _last_message_timestamp(chat)

        if last_ts is not None and last_ts <= marker:
            chat["unreadCount"] = 0
            chat["unreadSource"] = "local_marker"
            continue

        try:
            count, is_lower_bound = _count_unread_since(client, jid, marker, page_size)
        except EvolutionAPIError as error:
            client._log(f"Unread recount failed for {jid}: {error}", "WARNING")
            chat["unreadSource"] = "evolution"
            continue

        chat["unreadCount"] = count
        chat["unreadSource"] = "local_marker"
        if is_lower_bound:
            chat["unreadCountIsLowerBound"] = True

    return chats
```

Ajuste o import no topo do arquivo pra uma linha só: `from evoapi_mcp.client import GROUP_JID_SUFFIX, EvolutionAPIError, EvolutionClient`.

- [ ] **Step 4: Rodar**

Run: `uv run --quiet pytest -q`
Expected: `66 passed`

- [ ] **Step 5: Commit**

```bash
git add src/evoapi_mcp/chat_read.py tests/test_chat_read.py
git commit -m "$(cat <<'EOF'
✨feature: compute unread count from local read markers

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: `media.py`: base64 → arquivo

**Files:**
- Create: `src/evoapi_mcp/media.py`
- Test: `tests/test_media.py`

**Interfaces:**
- Consumes: `client.get_media_base64(message_id) -> dict` (Task 3), `config.media_dir: Path` (Task 2).
- Produces:
  ```python
  def extension_for(mimetype: str | None) -> str            # ".ogg", ".jpg", ..., ".bin"
  def save_media(payload: dict, media_dir: Path, message_id: str) -> dict
  def download_media(client, media_dir: Path, message_id: str) -> dict
  ```
  Retorno de `save_media`/`download_media`: `{path: str, mediaType, mimetype, fileName, caption, sizeBytes: int, cached: bool}`. Constante `MEDIA_TYPES_AUDIO = {"audioMessage"}`.

- [ ] **Step 1: Testes**

```python
import base64

import pytest

from helpers import GET_BASE64, run
from evoapi_mcp.client import EvolutionAPIError
from evoapi_mcp.media import download_media, extension_for, save_media

AUDIO_BYTES = b"OggS\x00fake-opus-bytes"


def payload(**overrides):
    base = {
        "mediaType": "audioMessage",
        "fileName": "PTT-20260920.ogg",
        "caption": None,
        "size": {"fileLength": {"low": len(AUDIO_BYTES), "high": 0}},
        "mimetype": "audio/ogg; codecs=opus",
        "base64": base64.b64encode(AUDIO_BYTES).decode(),
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("mimetype,ext", [
    ("audio/ogg; codecs=opus", ".ogg"),
    ("audio/ogg", ".ogg"),
    ("image/jpeg", ".jpg"),
    ("image/webp", ".webp"),
    ("video/mp4", ".mp4"),
    ("application/pdf", ".pdf"),
    ("audio/mpeg", ".mp3"),
    ("application/x-unknown-thing", ".bin"),
    (None, ".bin"),
])
def test_extension_for(mimetype, ext):
    assert extension_for(mimetype) == ext


def test_save_media_writes_file_and_omits_base64(tmp_path):
    result = save_media(payload(), tmp_path / "media", "MSG1")

    path = tmp_path / "media" / "MSG1.ogg"
    assert path.read_bytes() == AUDIO_BYTES
    assert result["path"] == str(path)
    assert result["sizeBytes"] == len(AUDIO_BYTES)
    assert result["mimetype"] == "audio/ogg; codecs=opus"
    assert result["mediaType"] == "audioMessage"
    assert result["fileName"] == "PTT-20260920.ogg"
    assert result["cached"] is False
    assert "base64" not in result
    assert not list((tmp_path / "media").glob("*.tmp"))


def test_save_media_reuses_existing_file(tmp_path):
    save_media(payload(), tmp_path, "MSG1")
    (tmp_path / "MSG1.ogg").write_bytes(b"already here")

    result = save_media(payload(), tmp_path, "MSG1")

    assert result["cached"] is True
    assert (tmp_path / "MSG1.ogg").read_bytes() == b"already here"


def test_save_media_without_base64_raises(tmp_path):
    with pytest.raises(EvolutionAPIError):
        save_media({"mediaType": "conversation"}, tmp_path, "MSG1")


def test_download_media_calls_api_and_saves(client, recorder, tmp_path):
    rec = recorder({GET_BASE64: payload()})

    result = run(rec, lambda: download_media(client, tmp_path, "MSG1"))

    assert rec.bodies(GET_BASE64) == [{"message": {"key": {"id": "MSG1"}}}]
    assert (tmp_path / "MSG1.ogg").exists()
    assert result["cached"] is False


def test_download_media_skips_api_when_cached(client, recorder, tmp_path):
    (tmp_path / "MSG1.ogg").write_bytes(AUDIO_BYTES)
    rec = recorder({GET_BASE64: payload()})

    result = run(rec, lambda: download_media(client, tmp_path, "MSG1"))

    assert result["cached"] is True
```

Atenção ao último teste: sem chamar a API não há `mimetype`; a implementação precisa localizar o arquivo existente por prefixo `MSG1.*` (glob) e preencher `mimetype`/`mediaType` como `None` quando vier do cache sem metadados. Ajuste o teste pra `assert result["mimetype"] is None` se preferir deixar isso explícito, e mantenha `rec.count(GET_BASE64) == 0`.

- [ ] **Step 2: Rodar pra ver falhar**

Run: `uv run --quiet pytest -q tests/test_media.py`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implementar**

```python
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
```

- [ ] **Step 4: Rodar**

Run: `uv run --quiet pytest -q`
Expected: todos verdes.

- [ ] **Step 5: Commit**

```bash
git add src/evoapi_mcp/media.py tests/test_media.py
git commit -m "$(cat <<'EOF'
✨feature: download media to disk instead of base64

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: `transcription.py`: OpenAI + cache

**Files:**
- Create: `src/evoapi_mcp/transcription.py`
- Test: `tests/test_transcription.py`

**Interfaces:**
- Consumes: `download_media(client, media_dir, message_id)` (Task 7), `config.openai_api_key`, `config.openai_transcribe_model`, `config.media_dir`.
- Produces:
  ```python
  class TranscriptionError(Exception)
  OPENAI_TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"
  MISSING_KEY_MESSAGE: str
  def transcribe_file(audio_path: Path, api_key: str, model: str, language: str | None = None, timeout: int = 120) -> str
  def transcribe_message(client, config, message_id: str, language: str | None = None) -> dict
      # {text, model, audioPath, transcriptPath, cached, language, messageId}
  ```

- [ ] **Step 1: Testes**

```python
import base64
from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import GET_BASE64, run
from evoapi_mcp.config import EvolutionConfig
from evoapi_mcp.transcription import (
    MISSING_KEY_MESSAGE,
    OPENAI_TRANSCRIPTIONS_URL,
    TranscriptionError,
    transcribe_file,
    transcribe_message,
)

AUDIO = b"OggS\x00fake"


class OpenAIResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(payload)

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def clear_openai_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_TRANSCRIBE_MODEL", raising=False)


def audio_payload():
    return {"mediaType": "audioMessage", "mimetype": "audio/ogg; codecs=opus",
            "base64": base64.b64encode(AUDIO).decode(), "fileName": "a.ogg"}


def make_config(tmp_path, key="sk-test"):
    return EvolutionConfig(base_url="http://evolution.test", api_token="t", instance_name="i",
                           media_dir=tmp_path, openai_api_key=key, _env_file=None)


def test_transcribe_file_posts_multipart_with_model_and_language(tmp_path):
    audio = tmp_path / "a.ogg"
    audio.write_bytes(AUDIO)
    with patch("evoapi_mcp.transcription.requests.post", return_value=OpenAIResponse(200, {"text": "olá"})) as post:
        text = transcribe_file(audio, "sk-test", "whisper-1", language="pt")

    assert text == "olá"
    args, kwargs = post.call_args
    assert args[0] == OPENAI_TRANSCRIPTIONS_URL
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test"
    assert kwargs["data"] == {"model": "whisper-1", "response_format": "json", "language": "pt"}
    assert "file" in kwargs["files"]


def test_transcribe_file_omits_language_when_none(tmp_path):
    audio = tmp_path / "a.ogg"
    audio.write_bytes(AUDIO)
    with patch("evoapi_mcp.transcription.requests.post", return_value=OpenAIResponse(200, {"text": "x"})) as post:
        transcribe_file(audio, "sk", "m")

    assert "language" not in post.call_args.kwargs["data"]


def test_transcribe_file_http_error_becomes_transcription_error(tmp_path):
    audio = tmp_path / "a.ogg"
    audio.write_bytes(AUDIO)
    with patch("evoapi_mcp.transcription.requests.post", return_value=OpenAIResponse(401, {"error": {"message": "bad key"}})):
        with pytest.raises(TranscriptionError) as exc:
            transcribe_file(audio, "sk", "m")

    assert "401" in str(exc.value)


def test_missing_key_fails_before_any_http(client, recorder, tmp_path):
    rec = recorder({GET_BASE64: audio_payload()})
    config = make_config(tmp_path, key=None)

    with pytest.raises(TranscriptionError) as exc:
        run(rec, lambda: transcribe_message(client, config, "MSG1"))

    assert str(exc.value) == MISSING_KEY_MESSAGE
    assert "OPENAI_API_KEY" in MISSING_KEY_MESSAGE
    assert rec.count(GET_BASE64) == 0


def test_non_audio_media_is_rejected_with_its_type(client, recorder, tmp_path):
    rec = recorder({GET_BASE64: {**audio_payload(), "mediaType": "imageMessage", "mimetype": "image/jpeg"}})

    with pytest.raises(TranscriptionError) as exc:
        run(rec, lambda: transcribe_message(client, make_config(tmp_path), "MSG1"))

    assert "imageMessage" in str(exc.value)


def test_transcribe_message_downloads_calls_openai_and_caches(client, recorder, tmp_path):
    rec = recorder({GET_BASE64: audio_payload()})
    config = make_config(tmp_path)

    with patch("evoapi_mcp.transcription.requests.post", return_value=OpenAIResponse(200, {"text": "fechado o deal"})) as post:
        result = run(rec, lambda: transcribe_message(client, config, "MSG1", language="pt"))

    assert result["text"] == "fechado o deal"
    assert result["cached"] is False
    assert result["model"] == "gpt-4o-mini-transcribe"
    assert result["audioPath"] == str(tmp_path / "MSG1.ogg")
    assert Path(result["transcriptPath"]).read_text(encoding="utf-8") == "fechado o deal"
    assert post.call_count == 1


def test_cached_transcript_skips_openai(client, recorder, tmp_path):
    (tmp_path / "MSG1.ogg").write_bytes(AUDIO)
    (tmp_path / "MSG1.txt").write_text("já transcrito", encoding="utf-8")
    rec = recorder({})

    with patch("evoapi_mcp.transcription.requests.post") as post:
        result = run(rec, lambda: transcribe_message(client, make_config(tmp_path), "MSG1"))

    assert result["text"] == "já transcrito"
    assert result["cached"] is True
    post.assert_not_called()
    assert rec.count(GET_BASE64) == 0
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `uv run --quiet pytest -q tests/test_transcription.py`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implementar**

```python
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
```

Sobre `media_type is not None`: quando o áudio veio do cache em disco (Task 7, `_find_cached`), não há metadados; a checagem de tipo é pulada e a extensão do arquivo decide. Não é preciso testar esse ramo além do `test_cached_transcript_skips_openai`.

- [ ] **Step 4: Rodar**

Run: `uv run --quiet pytest -q`
Expected: todos verdes.

- [ ] **Step 5: Commit**

```bash
git add src/evoapi_mcp/transcription.py tests/test_transcription.py
git commit -m "$(cat <<'EOF'
✨feature: transcribe audio messages via openai

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: `transcribe_chat_audios`

**Files:**
- Modify: `src/evoapi_mcp/transcription.py`
- Test: `tests/test_transcription.py` (acrescentar)

**Interfaces:**
- Consumes: `client.find_messages(chat_id, limit, page)`, `transcribe_message` (Task 8).
- Produces: `transcribe_chat_audios(client, config, chat: str, limit: int = 50, page: int = 1, language: str | None = None) -> dict` com `{chatResolution, scanned, pages, currentPage, audios: [{messageId, timestamp, fromMe, pushName, seconds, text | error, cached}]}`.

- [ ] **Step 1: Testes (acrescentar)**

```python
from helpers import FIND_MESSAGES, LID_JID
from evoapi_mcp.transcription import transcribe_chat_audios


def audio_record(msg_id, ts, seconds=5, from_me=False):
    return {
        "key": {"id": msg_id, "fromMe": from_me, "remoteJid": LID_JID},
        "messageTimestamp": ts,
        "pushName": "Boaz",
        "messageType": "audioMessage",
        "message": {"audioMessage": {"seconds": seconds, "mimetype": "audio/ogg; codecs=opus"}},
    }


def text_record(msg_id, ts):
    return {"key": {"id": msg_id, "fromMe": False, "remoteJid": LID_JID}, "messageTimestamp": ts,
            "messageType": "conversation", "message": {"conversation": "oi"}}


def find_result(*records):
    return {"messages": {"total": len(records), "pages": 2, "currentPage": 1, "records": list(records),
                         "chatResolution": {"requested": LID_JID, "jid": LID_JID, "resolved": True}}}


def test_transcribes_only_audio_records_and_isolates_failures(client, recorder, tmp_path):
    rec = recorder({FIND_MESSAGES: find_result(text_record("T1", 1), audio_record("A1", 2), audio_record("A2", 3, seconds=9)),
                    GET_BASE64: audio_payload()})
    config = make_config(tmp_path)
    responses = iter([OpenAIResponse(200, {"text": "primeiro"}), OpenAIResponse(500, {"error": "boom"})])

    with patch("evoapi_mcp.transcription.requests.post", side_effect=lambda *a, **k: next(responses)):
        result = run(rec, lambda: transcribe_chat_audios(client, config, LID_JID, limit=10, page=1, language="pt"))

    assert result["scanned"] == 3
    assert result["pages"] == 2
    assert result["chatResolution"]["resolved"] is True
    assert [a["messageId"] for a in result["audios"]] == ["A1", "A2"]
    assert result["audios"][0]["text"] == "primeiro"
    assert result["audios"][0]["seconds"] == 5
    assert result["audios"][0]["pushName"] == "Boaz"
    assert result["audios"][0]["fromMe"] is False
    assert "500" in result["audios"][1]["error"]
    assert "text" not in result["audios"][1]
    body = rec.bodies(FIND_MESSAGES)[0]
    assert body["offset"] == 10


def test_chat_audios_fails_fast_without_key(client, recorder, tmp_path):
    rec = recorder({FIND_MESSAGES: find_result(audio_record("A1", 2))})

    with pytest.raises(TranscriptionError):
        run(rec, lambda: transcribe_chat_audios(client, make_config(tmp_path, key=None), LID_JID))

    assert rec.count(FIND_MESSAGES) == 0
```

Cuidado: os dois áudios usam o mesmo `GET_BASE64` mock, mas têm ids diferentes, então geram `A1.ogg` e `A2.ogg` distintos e o cache não interfere.

- [ ] **Step 2: Rodar pra ver falhar**

Run: `uv run --quiet pytest -q tests/test_transcription.py`
Expected: FAIL `ImportError`.

- [ ] **Step 3: Implementar (acrescentar em `transcription.py`)**

```python
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
) -> dict[str, Any]:
    if not config.openai_api_key:
        raise TranscriptionError(MISSING_KEY_MESSAGE)

    found = client.find_messages(chat_id=chat, limit=limit, page=page)
    block = found.get("messages") if isinstance(found, dict) else {}
    records = block.get("records") if isinstance(block, dict) else []
    records = records if isinstance(records, list) else []

    audios: list[dict[str, Any]] = []
    for record in records:
        if record.get("messageType") != "audioMessage":
            continue
        key = record.get("key") or {}
        item: dict[str, Any] = {
            "messageId": key.get("id"),
            "timestamp": record.get("messageTimestamp"),
            "fromMe": bool(key.get("fromMe")),
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
    }
```

- [ ] **Step 4: Rodar**

Run: `uv run --quiet pytest -q`
Expected: todos verdes.

- [ ] **Step 5: Commit**

```bash
git add src/evoapi_mcp/transcription.py tests/test_transcription.py
git commit -m "$(cat <<'EOF'
✨feature: transcribe every audio in a chat page

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Tools no `server.py` e `list_chats` com marcador

**Files:**
- Modify: `src/evoapi_mcp/server.py` (imports no topo; `list_chats` em ~237-269; nova seção de tools antes de `# Entry Point`)
- Test: `tests/test_server_tools.py`

**Interfaces:**
- Consumes: tudo das Tasks 2-9.
- Produces: tools MCP `mark_as_read`, `download_media`, `transcribe_audio`, `transcribe_chat_audios`; `list_chats` anotado. Objeto de módulo `read_markers: ReadMarkerStore`.

- [ ] **Step 1: Testes**

Importar `server` carrega a config real do ambiente e faz `sys.exit(1)` se faltar `EVOLUTION_*`. Os testes setam as env vars antes do import e usam `monkeypatch` nas funções de orquestração; não fazem HTTP.

```python
import importlib
import sys

import pytest


@pytest.fixture
def server(monkeypatch, tmp_path):
    monkeypatch.setenv("EVOLUTION_BASE_URL", "http://evolution.test")
    monkeypatch.setenv("EVOLUTION_API_TOKEN", "t")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "test-instance")
    monkeypatch.setenv("EVOLUTION_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EVOLUTION_MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("evoapi_mcp.server", None)
    module = importlib.import_module("evoapi_mcp.server")
    yield module
    sys.modules.pop("evoapi_mcp.server", None)


def test_registers_new_tools(server):
    names = {tool.name for tool in server.mcp._tool_manager.list_tools()}
    assert {"mark_as_read", "download_media", "transcribe_audio", "transcribe_chat_audios"} <= names


def test_mark_as_read_description_forbids_automatic_use(server):
    tool = server.mcp._tool_manager.get_tool("mark_as_read")
    assert "NUNCA" in tool.description
    assert "comando explícito" in tool.description


def test_mark_as_read_accepts_list_and_isolates_failures(server, monkeypatch):
    calls = []

    def fake(client, store, chat, page_size=100):
        calls.append(chat)
        if chat == "bad":
            raise RuntimeError("boom")
        return {"requested": chat, "jid": chat, "phoneCleared": True}

    monkeypatch.setattr(server, "mark_chat_read", fake)

    out = server.mark_as_read(["a", "bad", "c"])

    assert calls == ["a", "bad", "c"]
    assert out[0]["phoneCleared"] is True
    assert out[1]["requested"] == "bad" and "boom" in out[1]["error"]
    assert out[2]["jid"] == "c"


def test_mark_as_read_accepts_single_string(server, monkeypatch):
    monkeypatch.setattr(server, "mark_chat_read", lambda client, store, chat, page_size=100: {"requested": chat})

    assert server.mark_as_read("5511999999999") == [{"requested": "5511999999999"}]


def test_list_chats_is_annotated_before_limit(server, monkeypatch):
    chats = [{"remoteJid": "a@lid", "unreadCount": 3}, {"remoteJid": "b@lid", "unreadCount": 4}]
    monkeypatch.setattr(server.client, "find_chats", lambda **kw: chats)
    seen = {}

    def fake_annotate(client, store, chats, page_size=100):
        seen["count"] = len(chats)
        for c in chats:
            c["unreadSource"] = "evolution"
        return chats

    monkeypatch.setattr(server, "annotate_chats_with_markers", fake_annotate)

    out = server.list_chats(limit=1)

    assert seen["count"] == 2
    assert out == [{"remoteJid": "a@lid", "unreadCount": 3, "unreadSource": "evolution"}]


def test_download_media_uses_configured_dir(server, monkeypatch, tmp_path):
    captured = {}

    def fake(client, media_dir, message_id):
        captured["dir"] = media_dir
        captured["id"] = message_id
        return {"path": "x"}

    monkeypatch.setattr(server, "download_media_to_disk", fake)

    assert server.download_media("MSG1") == {"path": "x"}
    assert captured == {"dir": server.config.media_dir, "id": "MSG1"}


def test_transcribe_tools_delegate(server, monkeypatch):
    monkeypatch.setattr(server, "transcribe_message", lambda client, config, message_id, language=None: {"text": f"{message_id}:{language}"})
    monkeypatch.setattr(server, "transcribe_chat_audios_in_page", lambda client, config, chat, limit=50, page=1, language=None: {"chat": chat, "limit": limit, "page": page})

    assert server.transcribe_audio("M", language="pt") == {"text": "M:pt"}
    assert server.transcribe_chat_audios("c", limit=5, page=2) == {"chat": "c", "limit": 5, "page": 2}
```

Se `server.mcp._tool_manager` não existir nesta versão do FastMCP, use `import asyncio; names = {t.name for t in asyncio.run(server.mcp.list_tools())}` e `tool = next(t for t in asyncio.run(server.mcp.list_tools()) if t.name == "mark_as_read")`.

- [ ] **Step 2: Rodar pra ver falhar**

Run: `uv run --quiet pytest -q tests/test_server_tools.py`
Expected: FAIL (`AttributeError: module has no attribute 'mark_as_read'`).

- [ ] **Step 3: Implementar em `server.py`**

Imports (depois de `from evoapi_mcp.client import EvolutionClient`):

```python
from evoapi_mcp.chat_read import annotate_chats_with_markers, mark_chat_read
from evoapi_mcp.media import download_media as download_media_to_disk
from evoapi_mcp.read_markers import ReadMarkerStore
from evoapi_mcp.transcription import transcribe_chat_audios as transcribe_chat_audios_in_page
from evoapi_mcp.transcription import transcribe_message
```

Logo após `client = EvolutionClient(config)` dentro do `try`:

```python
    read_markers = ReadMarkerStore(config.state_dir, config.instance_name)
```

Em `list_chats`, troque `chats = client.find_chats()` por:

```python
    chats = client.find_chats()
    if isinstance(chats, list):
        chats = annotate_chats_with_markers(client, read_markers, chats)
```

No docstring existente de `list_chats`, dentro da lista de campos do `Returns`, acrescente exatamente estas linhas (o Ian autorizou esta única exceção à regra de comentários; nada além disso):

```
              - unreadSource: "evolution" (contador bruto da Evolution, que nunca decrementa)
                ou "local_marker" (calculado a partir do marcador gravado por mark_as_read)
              - readMarker / unreadCountIsLowerBound: presentes só quando há marcador
```

Nova seção antes de `# Entry Point`:

```python
# ============================================================================
# TOOLS - Leitura, Mídia e Transcrição
# ============================================================================

MARK_AS_READ_DESCRIPTION = """Marca uma ou várias conversas do WhatsApp como lidas.

NUNCA chame esta ferramenta por iniciativa própria, dentro de uma skill automática ou
como efeito colateral de uma triagem. Só sob comando explícito do usuário ("marca X
como lido", "limpa as não lidas de A, B e C"). O "não lido" é a memória de trabalho
das pessoas; zerar sem pedido apaga essa memória.

O que a ferramenta faz por conversa:
- Manda read receipts das mensagens recebidas ainda não marcadas. Em conversa 1:1 isso
  limpa a marca de não lido no celular (contatos @lid usam o telefone em remoteJidAlt,
  porque a Evolution API descarta chaves @lid em silêncio).
- Grava um marcador de leitura local; a partir dele list_chats passa a calcular
  unreadCount (unreadSource = "local_marker").
- Em GRUPO não manda receipt (a Evolution API perde o participant da chave e o WhatsApp
  ignora o receipt). Só o marcador é gravado; phoneCleared vem False com
  reason = "group_receipts_unsupported".

Args:
    chats: Número internacional sem '+' (ex: 5511999999999), JID completo
        (ex: 120363000000000000@g.us, 100000000000000@lid) ou lista misturando os dois.

Returns:
    Uma entrada por chat pedido, na mesma ordem: requested, jid, resolved, receiptsSent,
    phoneCleared, reason, markerTimestamp, messagesScanned. Falha em um chat vira
    "error" nessa entrada e não interrompe os demais.
"""

DOWNLOAD_MEDIA_DESCRIPTION = """Baixa a mídia (imagem, documento, áudio, vídeo, sticker) de uma mensagem e salva em disco.

message_id é o key.id de um registro devolvido por get_chat_messages ou find_messages.
A Evolution API descriptografa a mídia internamente; a ferramenta grava o arquivo em
EVOLUTION_MEDIA_DIR (padrão ~/Downloads/whatsapp-media) como <message_id>.<ext> e devolve
o CAMINHO, nunca o conteúdo em base64 (respostas grandes seriam truncadas). Se o arquivo
já existe, não baixa de novo (cached = True).

Returns:
    path, mediaType, mimetype, fileName, caption, sizeBytes, cached.
"""

TRANSCRIBE_AUDIO_DESCRIPTION = """Transcreve um áudio do WhatsApp usando a API de transcrição da OpenAI.

Baixa o áudio (mesmo caminho de download_media) e envia pra OpenAI com o modelo em
OPENAI_TRANSCRIBE_MODEL (padrão gpt-4o-mini-transcribe). Exige OPENAI_API_KEY no
ambiente; sem ela, falha antes de baixar qualquer coisa. O texto fica em cache ao lado
do áudio (<message_id>.txt), então repetir a chamada não paga de novo.

Args:
    message_id: key.id de uma mensagem do tipo audioMessage.
    language: Código ISO-639-1 (ex: "pt") pra guiar o modelo. Opcional.

Returns:
    text, model, language, audioPath, transcriptPath, cached, messageId.
"""

TRANSCRIBE_CHAT_AUDIOS_DESCRIPTION = """Transcreve todos os áudios de uma página de mensagens de uma conversa.

Use quando o usuário pedir "o que dizem os áudios que fulano mandou" ou quando uma
triagem encontrar audioMessage numa conversa relevante. Busca `limit` mensagens da
página `page` (mesma paginação de find_messages), filtra os áudios e transcreve cada um.
Falha em um áudio vira "error" naquele item; os outros seguem. Exige OPENAI_API_KEY.

Args:
    chat: Número, ou JID completo (grupos e contatos @lid).
    limit: Tamanho da página de mensagens a varrer (padrão 50).
    page: Página, começando em 1.
    language: Código ISO-639-1 opcional.

Returns:
    chatResolution, scanned, pages, currentPage e audios: lista com messageId,
    timestamp, fromMe, pushName, seconds e text (ou error).
"""


@mcp.tool(description=MARK_AS_READ_DESCRIPTION)
def mark_as_read(chats: list[str] | str) -> list[dict]:
    requested = [chats] if isinstance(chats, str) else list(chats)
    results: list[dict] = []
    for chat in requested:
        try:
            results.append(mark_chat_read(client, read_markers, chat))
        except Exception as error:
            results.append({"requested": chat, "error": str(error)})
    return results


@mcp.tool(description=DOWNLOAD_MEDIA_DESCRIPTION)
def download_media(message_id: str) -> dict:
    return download_media_to_disk(client, config.media_dir, message_id)


@mcp.tool(description=TRANSCRIBE_AUDIO_DESCRIPTION)
def transcribe_audio(message_id: str, language: str | None = None) -> dict:
    return transcribe_message(client, config, message_id, language)


@mcp.tool(description=TRANSCRIBE_CHAT_AUDIOS_DESCRIPTION)
def transcribe_chat_audios(
    chat: str,
    limit: int = 50,
    page: int = 1,
    language: str | None = None
) -> dict:
    return transcribe_chat_audios_in_page(client, config, chat, limit=limit, page=page, language=language)
```

As strings `*_DESCRIPTION` são dados (vão pro `description` da tool), não comentários. Não escreva docstring nas funções novas.

- [ ] **Step 4: Rodar**

Run: `uv run --quiet pytest -q`
Expected: todos verdes.

- [ ] **Step 5: Smoke test do servidor subindo**

Run (do worktree, com o `.env` do clone principal, sem tocar no clone):
```bash
cd ~/dev/evoapi-mcp-wt/mark-read && cp ~/dev/evoapi-mcp/.env .env && timeout 5 uv run --quiet evoapi-mcp </dev/null; echo "exit=$?"
```
Expected: log `Configuração carregada` no stderr e saída por timeout (exit 124), sem traceback. O `.env` está no `.gitignore`; não commitar.

- [ ] **Step 6: Commit**

```bash
git add src/evoapi_mcp/server.py tests/test_server_tools.py
git commit -m "$(cat <<'EOF'
✨feature: expose mark-read, media and transcription tools

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Documentação e versão

**Files:**
- Modify: `README.md` (seções "Tools Disponíveis" ~226-282, "Configure as Variáveis de Ambiente" ~101-121, e nova seção antes de "Roadmap" ~358)
- Modify: `.env.example` (reescrever inteiro via heredoc; conteúdo atual em `git show HEAD:.env.example`)
- Modify: `CHANGELOG.md` (inserir `[1.3.0]` acima de `[1.2.1]`)
- Modify: `KNOWN_ISSUES.md` (acrescentar issues #14, #15, #16 no fim, seguindo a numeração e o formato das existentes; leia o arquivo antes)
- Modify: `pyproject.toml:3` (`version = "1.3.0"`)

- [ ] **Step 1: `.env.example`**

```bash
cat > .env.example <<'EOF'
# Configuração do servidor Evolution API
EVOLUTION_BASE_URL=http://localhost:8080
EVOLUTION_API_TOKEN=seu-token-aqui
EVOLUTION_INSTANCE_NAME=minha-instancia

# Opcional: Timeout para requisições (em segundos)
# EVOLUTION_TIMEOUT=30

# Opcional: onde ficam os marcadores de leitura gravados por mark_as_read
# EVOLUTION_STATE_DIR=~/.local/state/evoapi-mcp

# Opcional: onde download_media e transcribe_audio salvam os arquivos
# EVOLUTION_MEDIA_DIR=~/Downloads/whatsapp-media

# Opcional: só pra transcribe_audio / transcribe_chat_audios.
# Se você usa o plugin ch-shared do Claude Code, a mesma OPENAI_API_KEY do bloco "env"
# do ~/.claude/settings.json é herdada pelo processo do MCP; não precisa repetir aqui.
# OPENAI_API_KEY=sk-...
# OPENAI_TRANSCRIBE_MODEL=gpt-4o-mini-transcribe
EOF
```

- [ ] **Step 2: README**

Na seção "Tools Disponíveis", acrescente uma subseção `### Leitura, Mídia e Transcrição` no mesmo formato das existentes (nome da tool em negrito + uma linha), cobrindo `mark_as_read`, `download_media`, `transcribe_audio`, `transcribe_chat_audios`, e uma linha em "Conversas e Mensagens" dizendo que `list_chats` devolve `unreadSource`/`readMarker`. Na seção de variáveis de ambiente, acrescente as quatro novas com uma frase cada, dizendo explicitamente que `OPENAI_API_KEY` é a mesma do `ch-shared` (bloco `env` do `settings.json`) e que o processo do MCP herda o ambiente do Claude Code.

Nova seção `## ⚠️ Limitações da Evolution API (v2.3.7) e próximos passos`, antes do Roadmap, com este conteúdo:

```markdown
## ⚠️ Limitações da Evolution API (v2.3.7) e próximos passos

Verificado no código-fonte da tag 2.3.7 e contra instância real em 2026-09-20:

- **`markMessageAsRead` descarta chaves `@lid` em silêncio** e ainda responde `success`.
  Cerca de 70% das conversas individuais são `@lid`. O MCP contorna mandando a chave com o
  telefone (`remoteJidAlt`), que passa e limpa a marca de não lido no celular.
- **Grupo não pode ser marcado como lido pela API.** A Evolution joga fora o `participant`
  da chave antes de chamar o Baileys, e receipt de grupo sem participant é ignorado pelo
  WhatsApp. `mark_as_read` grava só o marcador local nesses casos (`phoneCleared: false`).
  O que destravaria isso é um endpoint `markChatRead` na Evolution espelhando o
  `markChatUnread` (`chatModify({markRead: true})`, que propaga pro celular). PR upstream
  bem-vindo.
- **O `unreadCount` da Evolution nunca decrementa via API.** Ele conta mensagens recebidas
  com status `DELIVERY_ACK` e só muda por eventos que a nossa leitura não gera. Por isso
  `list_chats` passa a calcular a partir do marcador local quando existe
  (`unreadSource: "local_marker"`).

Próximos passos possíveis, não implementados:

- **Arquivar**: `POST /chat/archiveChat/{instance}` existe (`{"lastMessage": {...},
  "archive": true}`), via `chatModify`, então deve propagar pro celular.
- **Silenciar**: não há endpoint de mute na 2.3.7.
```

- [ ] **Step 3: CHANGELOG**

Inserir acima de `## [1.2.1]`:

```markdown
## [1.3.0] - 2026-09-20

### ✨ Adicionado

- **`mark_as_read(chats)`**: marca uma ou várias conversas como lidas. Manda read
  receipts (1:1 limpa o celular; `@lid` via `remoteJidAlt`) e grava um marcador de
  leitura local em `EVOLUTION_STATE_DIR`. Grupo só recebe marcador, porque a Evolution
  2.3.7 perde o `participant` da chave. Nunca deve ser chamada automaticamente; a
  descrição da tool diz isso em maiúsculas.
- **`list_chats` respeita o marcador**: `unreadCount` passa a ser calculado a partir do
  marcador quando ele existe (`unreadSource: "local_marker"`), porque o contador da
  Evolution só sobe.
- **`download_media(message_id)`**: salva a mídia em `EVOLUTION_MEDIA_DIR` e devolve o
  caminho, nunca o base64.
- **`transcribe_audio(message_id)`** e **`transcribe_chat_audios(chat)`**: transcrição
  via OpenAI (`OPENAI_API_KEY`, mesma variável do plugin ch-shared), com cache do texto em
  `<id>.txt`.

### 🔧 Corrigido

- Nada em comportamento existente; `list_chats` sem marcador é idêntico ao anterior.

### 📝 Verificado

Três limitações da Evolution API 2.3.7 documentadas no README e em `KNOWN_ISSUES.md`
(#14 a #16): `@lid` descartado em `markMessageAsRead`, `participant` perdido em grupo,
`unreadCount` que nunca decrementa.
```

- [ ] **Step 4: KNOWN_ISSUES**

Leia o arquivo (`sed -n 1,60p KNOWN_ISSUES.md` e o fim) pra copiar o formato exato das issues #9-#13 (título, status, sintoma, causa, medição, fix). Acrescente #14 (`@lid` descartado), #15 (`participant` perdido em grupo) e #16 (`unreadCount` só sobe), com os dados do spike: 121 receipts de grupo com `201 success` e badge mantida; `@lid` com `201 success` e nada; `remoteJidAlt` limpando o celular; `unreadCount` = `count(DELIVERY_ACK)` e `chats.update` ignorando o campo.

- [ ] **Step 5: pyproject**

`sed -i '' 's/^version = ".*"/version = "1.3.0"/' pyproject.toml` e confira com `grep -n '^version' pyproject.toml`. Rode `uv lock --quiet` pra o `uv.lock` acompanhar a versão.

- [ ] **Step 6: Rodar tudo e commitar**

Run: `uv run --quiet pytest -q`
Expected: todos verdes.

```bash
git add README.md .env.example CHANGELOG.md KNOWN_ISSUES.md pyproject.toml uv.lock
git commit -m "$(cat <<'EOF'
📙documentation: document read, media and transcription tools

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: Validação ao vivo (sessão principal, não subagent)

Mexe no WhatsApp real do Ian. **Só a sessão principal roda esta task**, nas cobaias combinadas: contato Boaz (`245814047813821@lid` / `5521988007555`) e grupos "GigaWalks⚡" (`120363163376692320@g.us`) e "YC - Like for Like" (`120363298599070505@g.us`). Nenhum outro chat.

**Files:**
- Nenhum de código. Resultados vão pro corpo do PR.

- [ ] **Step 1: Script de validação no scratchpad**

Roda os módulos direto do worktree contra a instância real, sem passar pelo processo MCP do app:

```python
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "dev/evoapi-mcp-wt/mark-read/src"))
os.chdir(Path.home() / "dev/evoapi-mcp-wt/mark-read")
from evoapi_mcp.config import load_config
from evoapi_mcp.client import EvolutionClient
from evoapi_mcp.read_markers import ReadMarkerStore
from evoapi_mcp.chat_read import mark_chat_read, annotate_chats_with_markers

config = load_config()
client = EvolutionClient(config)
store = ReadMarkerStore(config.state_dir, config.instance_name)
for chat in sys.argv[1:]:
    print(json.dumps(mark_chat_read(client, store, chat), ensure_ascii=False))
chats = annotate_chats_with_markers(client, store, client.find_chats(enrich_with_names=False))
for c in chats:
    if c["remoteJid"] in sys.argv[1:] or c["remoteJid"] in [store_jid for store_jid in store.all()]:
        print(c["remoteJid"], c.get("unreadCount"), c.get("unreadSource"), c.get("unreadCountIsLowerBound"))
```

Run: `cd ~/dev/evoapi-mcp-wt/mark-read && uv run --quiet python <scratchpad>/live_mark_read.py 5521988007555 120363163376692320@g.us`
Expected: Boaz → `resolved: true`, `jid` `@lid`, `phoneCleared: true` (ou `reason: nothing_new` se não houver mensagem nova); GigaWalks → `phoneCleared: false`, `reason: group_receipts_unsupported`, `markerTimestamp` preenchido. `list_chats` anotado: ambos `unreadCount 0`, `unreadSource local_marker`. Arquivo `~/.local/state/evoapi-mcp/ian-personal.read-markers.json` criado.

- [ ] **Step 2: Pedir ao Ian pra conferir o celular** (Boaz sem bolinha; GigaWalks ainda com badge, esperado).

- [ ] **Step 3: `download_media` + `transcribe_audio`** num `audioMessage` de grupo de baixo valor: pegar o `key.id` via `client.find_messages(chat_id=<grupo>, limit=100)` filtrando `messageType == "audioMessage"`, rodar `download_media` (conferir arquivo `.ogg` em `~/Downloads/whatsapp-media/` e que abre) e `transcribe_message` (conferir texto plausível e `.txt` criado; segunda chamada `cached: true`).

- [ ] **Step 4: `transcribe_chat_audios`** numa conversa que o Ian indicar na hora; registrar `scanned`, quantidade de áudios, tempo total e custo aproximado (segundos totais × preço do modelo).

- [ ] **Step 5: Confirmar herança da `OPENAI_API_KEY`**: matar todas as instâncias do MCP (`for p in $(pgrep -f evoapi); do kill $p; done`), fazer uma chamada qualquer da tool `whatsapp` na sessão do app (que sobe o processo novo a partir do clone principal, ainda sem as tools novas) e checar `ps eww <pid> | tr ' ' '\n' | grep -c '^OPENAI_API_KEY='` → esperado `1`. Se `0`, o README e a skill do marketplace precisam do `-e OPENAI_API_KEY` no `claude mcp add`; ajustar o README antes do PR.

- [ ] **Step 6: Registrar** os resultados (JSONs resumidos, sem conteúdo de mensagem de terceiros além do necessário) no corpo do PR da Task 13.

---

### Task 13: PR no fork

**Files:** nenhum.

- [ ] **Step 1: Revisão final local**

Run: `cd ~/dev/evoapi-mcp-wt/mark-read && uv run --quiet pytest -q && git log --oneline origin/master..HEAD && git diff origin/master --stat`
Expected: verde; ~12 commits; nenhum arquivo `.env` ou de mídia no diff.

- [ ] **Step 2: Pedir confirmação ao Ian pra push e abertura do PR** (regra CLAUDE.md: push e PR exigem ok explícito). Mostrar o título e o corpo antes.

- [ ] **Step 3: Push e PR**

```bash
git push -u origin feature/mark-read-media-transcribe
gh pr create -R cloudhumans/evoapi-mcp --base master --title "✨feature: mark as read, download media and transcribe audio" --body-file <scratchpad>/pr-body.md
```

Corpo em pt-BR, 1-2 parágrafos focados no problema (triagem não lia áudio; não-lido sem controle), link pra spec no repo, tabela dos resultados da validação ao vivo, as três limitações da Evolution, e no fim `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

- [ ] **Step 4: Anotar follow-ups** (não fazer agora): PR na skill `ch-shared:setup-whatsapp-mcp` do marketplace documentando as tools novas e a `OPENAI_API_KEY`; PR upstream na Evolution com `markChatRead`.
