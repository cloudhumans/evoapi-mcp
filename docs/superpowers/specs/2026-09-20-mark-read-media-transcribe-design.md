# Marcar como lido, baixar mídia e transcrever áudio

Data: 2026-09-20. Alvo: `cloudhumans/evoapi-mcp` (fork), Evolution API v2.3.7.

## Objetivo

Estender o MCP com três capacidades que hoje não existem: marcar conversas como lidas
(uma ou dezenas de uma vez), baixar mídia de uma mensagem e transcrever áudio. Tem que
servir pra qualquer pessoa da Cloud Humans: nada de caminho fixo, nada de credencial no
código, README explicando do zero, mesmas variáveis de ambiente que o marketplace já
configura.

Caso de uso que motivou: contexto de deal mandado em três áudios; a triagem viu que havia
áudio, não conseguiu ler, e o item chegou sem a informação que decidia a questão.

## Fora de escopo

Silenciar e arquivar. `POST /chat/archiveChat/{instance}` existe na 2.3.7 (via
`chatModify({archive})`) e entra no README como próximo passo. Mute não está exposto na
2.3.7. Atualização da skill `ch-shared:setup-whatsapp-mcp` no marketplace é PR separado.

## O que foi verificado antes de desenhar

Tudo abaixo foi conferido no código-fonte da tag `2.3.7` da Evolution API
(`src/api/integrations/channel/whatsapp/whatsapp.baileys.service.ts`) e confirmado dentro
do container em execução, mais um spike contra a instância `ian-personal` em 2026-09-20.

### `POST /chat/markMessageAsRead/{instance}`

- Payload: `{"readMessages": [{"remoteJid": str, "fromMe": bool, "id": str}]}`. Por
  mensagem, não por chat. O schema rejeita itens duplicados (`400 readMessages contains
  duplicate item`); a instância tem mensagens duplicadas no banco, então é preciso
  deduplicar por `id` antes de enviar.
- A implementação filtra as chaves com `isJidGroup(remoteJid) || isPnUser(remoteJid)`.
  **Chave `@lid` é descartada em silêncio** e a API ainda responde `201 success`. Cerca de
  70% das conversas individuais são `@lid`. Toda key de mensagem `@lid` traz
  `remoteJidAlt` com o JID de telefone (`<numero>@s.whatsapp.net`); enviando a key com o
  `remoteJidAlt` no lugar do `remoteJid`, o receipt passa e **o celular limpa a marca de
  não lido** (testado no contato cobaia).
- A Evolution só repassa `remoteJid`, `fromMe` e `id` pro Baileys; o `participant` da key
  se perde. Receipt de grupo sem `participant` é ignorado: 121 receipts no grupo cobaia
  devolveram `201 success` e a badge no celular continuou. **Grupo não tem como ser
  marcado como lido pela API da 2.3.7.**
- `chatModify` (usado por `markChatUnread` e `archiveChat`) propaga pro celular
  (testado: `markChatUnread` marcou a conversa cobaia como não lida no aparelho). Mas a
  Evolution só expõe `markRead: false`; não há `markRead: true`. Resolver de verdade pra
  grupo exige PR na Evolution (um `markChatRead` espelhando o `markChatUnread`), fora
  deste escopo.

### `unreadCount` do `findChats`

É `Chat.unreadMessages` no Postgres, recalculado como `count(mensagens recebidas com
status DELIVERY_ACK)`. Só vira READ por evento `messages.update` de leitura, que a nossa
própria chamada de read não gera; o handler de `chats.update` ignora `unreadCount`. Na
prática **o contador só sobe** (há grupo com 3084). Não serve como fonte de "o que eu
ainda não tratei", e não existe endpoint que o zere.

### `POST /chat/getBase64FromMediaMessage/{instance}`

- Payload mínimo: `{"message": {"key": {"id": "<key.id>"}}}`. Quando `message.message`
  não vem, a Evolution busca a mensagem no banco por `key.id`.
- Descriptografa internamente via Baileys `downloadMediaMessage` usando a `mediaKey`
  salva; o `.enc` do `mmg.whatsapp.net` é resolvido lá, com fallback
  `downloadContentFromMessage` após 5s. Não é preciso descriptografar no MCP.
- Tipos aceitos: `imageMessage`, `documentMessage`, `audioMessage`, `videoMessage`,
  `stickerMessage`, `ptvMessage`.
- Resposta: `{mediaType, fileName, caption, size: {fileLength, height, width}, mimetype,
  base64}`. `convertToMp4` opcional pra áudio; não vamos usar.
- Áudio do WhatsApp vem como `audio/ogg; codecs=opus`.

### OpenAI

`POST https://api.openai.com/v1/audio/transcriptions`, multipart `file` + `model`,
`language` (ISO-639-1) opcional, `response_format=json` devolve `{text}`. Aceita `ogg`.
Modelos: `whisper-1`, `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`. `OPENAI_API_KEY` já é
variável do `.env.example` do `ch-shared` e mora no bloco `env` do
`~/.claude/settings.json`.

## Decisão central: marcar como lido = receipt + marcador local

Como a Evolution não zera `unreadCount` nem limpa grupo, a tool faz as duas coisas que
funcionam e é honesta sobre o que não funciona:

1. **Manda read receipts** pras mensagens recebidas da conversa (1:1 limpa o celular;
   `@lid` usa `remoteJidAlt`; grupo não manda porque não surte efeito).
2. **Grava um marcador de leitura local** por conversa, e o `list_chats` passa a calcular
   `unreadCount` a partir dele quando existe.

Alternativas descartadas: só receipts (não resolve grupo nem a triagem) e só marcador
(desperdiça a limpeza real de 1:1).

Estado local por máquina é aceitável porque a instância do WhatsApp já é por pessoa e por
máquina; nada é compartilhado.

## Arquitetura

`client.py` continua sendo só a camada HTTP. Orquestração vai pra módulos novos, cada um
com uma responsabilidade e testável com a camada HTTP mockada.

```
src/evoapi_mcp/
  config.py         + state_dir, media_dir, openai_api_key, openai_transcribe_model
  client.py         + mark_messages_read(keys), get_media_base64(message_id)
  read_markers.py   ReadMarkerStore (JSON por instância, escrita atômica)
  chat_read.py      mark_chat_read(...) e annotate_chats_with_markers(...)
  media.py          save_media(...) : base64 -> arquivo em disco
  transcription.py  transcribe_file(...) via OpenAI, com cache em disco
  server.py         + 4 tools; list_chats passa pelo marcador
```

### `config.py`

Campos novos em `EvolutionConfig` (prefixo `EVOLUTION_` continua):

| Campo | Env | Default |
|---|---|---|
| `state_dir` | `EVOLUTION_STATE_DIR` | `~/.local/state/evoapi-mcp` |
| `media_dir` | `EVOLUTION_MEDIA_DIR` | `~/Downloads/whatsapp-media` |
| `openai_api_key` | `OPENAI_API_KEY` (alias, sem prefixo) | `None` |
| `openai_transcribe_model` | `OPENAI_TRANSCRIBE_MODEL` (alias, sem prefixo) | `gpt-4o-mini-transcribe` |

`~` é expandido. Diretórios são criados sob demanda, não no boot. `openai_api_key`
ausente não impede o servidor de subir; só `transcribe_*` reclama.

### `client.py`

- `mark_messages_read(keys: list[dict]) -> dict`: `POST /chat/markMessageAsRead` com
  `{"readMessages": keys}`. Não decide nada; recebe as keys já preparadas.
- `get_media_base64(message_id: str) -> dict`: `POST /chat/getBase64FromMediaMessage` com
  `{"message": {"key": {"id": message_id}}}`. Devolve a resposta bruta.

### `read_markers.py`

```python
class ReadMarkerStore:
    def __init__(self, state_dir: Path, instance_name: str): ...
    def get(self, jid: str) -> int | None          # lastMessageTimestamp
    def set(self, jid: str, last_message_timestamp: int) -> None
    def all(self) -> dict[str, dict]
```

Arquivo: `<state_dir>/<instance_name>.read-markers.json`, formato
`{"version": 1, "chats": {"<jid>": {"lastMessageTimestamp": int, "markedAt": iso8601}}}`.
Leitura tolera arquivo ausente ou corrompido (log WARNING, começa vazio). Escrita é
atômica: grava em `<arquivo>.tmp` e faz `os.replace`. Chave é sempre o JID resolvido.

### `chat_read.py`

`mark_chat_read(client, store, chat: str, page_size: int = 100) -> dict`:

1. `jid, resolved = client.resolve_chat_jid_detail(chat)`.
2. `client.find_messages(chat_id=jid, limit=page_size)`; pega `records`.
3. `marker_before = store.get(jid)`.
4. Candidatas a receipt: `fromMe == False`, `messageTimestamp > marker_before` (ou todas
   se não há marcador), deduplicadas por `key.id`.
5. Se `jid` termina em `@g.us`: não envia receipt; `phoneCleared = False`,
   `reason = "group_receipts_unsupported"`.
   Senão, monta cada key como `{"remoteJid": key.remoteJidAlt or key.remoteJid,
   "fromMe": key.fromMe, "id": key.id}` e chama `client.mark_messages_read`.
   Lista vazia: não chama a API.
6. `marker_after = max(messageTimestamp de todos os records)`; se não há records, usa
   `lastMessage.messageTimestamp` do chat quando disponível, senão não grava.
7. `store.set(jid, marker_after)`.

Retorno por chat:

```json
{"requested": "5521988007555", "jid": "245814047813821@lid", "resolved": true,
 "receiptsSent": 7, "phoneCleared": true, "reason": null,
 "markerTimestamp": 1789732047, "messagesScanned": 7}
```

`resolved: false` (número sem conversa) grava marcador mesmo assim e devolve
`receiptsSent: 0`, `phoneCleared: false`, `reason: "chat_not_found"`.

`annotate_chats_with_markers(client, store, chats: list[dict], page_size: int = 100) ->
list[dict]`: pra cada chat da lista do `findChats`:

- sem marcador: `unreadSource = "evolution"`, `unreadCount` intacto.
- com marcador e `lastMessage.messageTimestamp <= marcador`: `unreadCount = 0`,
  `unreadSource = "local_marker"`.
- com marcador e mensagem mais nova: `find_messages(chat_id=jid, limit=page_size)`,
  conta `fromMe == False` com `messageTimestamp > marcador`; `unreadCount = count`; se a
  página veio cheia, `unreadCountIsLowerBound = true`. `unreadSource = "local_marker"`.
- todo chat com marcador ganha `readMarker: {lastMessageTimestamp, markedAt}`.

Falha HTTP na contagem de um chat não derruba o `list_chats`: mantém o valor da Evolution
e registra `unreadSource = "evolution"` com log WARNING.

### `media.py`

`save_media(payload: dict, media_dir: Path, message_id: str) -> dict`:

- Extensão: mapa explícito primeiro (`audio/ogg` e variantes com `codecs=opus` → `.ogg`,
  `image/jpeg` → `.jpg`, `image/webp` → `.webp`, `video/mp4` → `.mp4`,
  `application/pdf` → `.pdf`), depois `mimetypes.guess_extension` sobre o mimetype sem
  parâmetros, fallback `.bin`.
- Caminho: `<media_dir>/<message_id><ext>`. Se já existe com tamanho > 0, não regrava e
  devolve `cached: true`.
- Escreve via arquivo temporário + `os.replace`.
- Retorno: `{path, mediaType, mimetype, fileName, caption, sizeBytes, cached}`. **Nunca
  inclui o base64.**

`download_media(client, config, message_id)` em `media.py` compõe
`client.get_media_base64` + `save_media`. Resposta sem `base64` (ex.: mensagem que não é
mídia, `400` da Evolution) vira `EvolutionAPIError` com a mensagem da API.

### `transcription.py`

`transcribe_file(audio_path: Path, api_key: str, model: str, language: str | None) -> str`:
`requests.post` multipart com `file`, `model`, `response_format=json` e `language` quando
informado; timeout 120s; devolve `text`. Erros HTTP da OpenAI viram
`TranscriptionError` com status e corpo resumido.

`transcribe_message(client, config, message_id, language)`:

1. Sem `config.openai_api_key`: `TranscriptionError("OPENAI_API_KEY não configurada.
   Defina no bloco env do ~/.claude/settings.json (mesmo lugar do ch-shared) ou no .env do
   evoapi-mcp.")`. Essa checagem vem **antes** de baixar o áudio.
2. `download_media`; se `mediaType != "audioMessage"` (ou `ptvMessage`, que é vídeo),
   erro dizendo o tipo real.
3. Cache: `<media_dir>/<message_id>.txt`; se existe, devolve `cached: true` sem chamar a
   OpenAI.
4. Chama `transcribe_file`, grava o `.txt` (atômico), devolve
   `{text, model, audioPath, transcriptPath, cached, language}`.

`transcribe_chat_audios(client, config, chat, limit, page, language)` também mora aqui:
chama `client.find_messages(chat_id=chat, limit=limit, page=page)`, filtra
`messageType == "audioMessage"` e aplica `transcribe_message` a cada um, capturando a
exceção por item. A tool em `server.py` só repassa os argumentos.

### `server.py`

Tools novas, todas com docstring em português no padrão das existentes:

- `mark_as_read(chats: list[str]) -> list[dict]`. Aceita número, JID ou lista mista.
  Docstring começa com: "NUNCA chame esta ferramenta por iniciativa própria ou dentro de
  uma skill automática. Só sob comando explícito do usuário. O 'não lido' é a memória de
  trabalho das pessoas." Explica o comportamento de grupo e `@lid`. Um item de resultado
  por chat pedido, na mesma ordem.
- `download_media(message_id: str) -> dict`. Docstring diz que `message_id` é o `key.id`
  de `get_chat_messages`/`find_messages`, que o arquivo é salvo em disco e que a resposta
  traz o caminho, não o conteúdo.
- `transcribe_audio(message_id: str, language: str | None = None) -> dict`.
- `transcribe_chat_audios(chat: str, limit: int = 50, page: int = 1, language: str | None
  = None) -> dict`: `find_messages(chat_id, limit, page)`, filtra
  `messageType == "audioMessage"`, transcreve cada um; falha individual vira `error` no
  item, não exceção. Retorno: `{chatResolution, scanned, pages, audios: [{messageId,
  timestamp, fromMe, pushName, seconds, text | error, cached}]}`. Se
  `OPENAI_API_KEY` falta, falha antes de transcrever qualquer item.
- `list_chats` passa a chamar `annotate_chats_with_markers` antes de aplicar `limit`.

Instâncias de `ReadMarkerStore` e o `config` ficam no módulo `server.py`, ao lado de
`client`.

## Tratamento de erro

- Toda chamada Evolution já levanta `EvolutionAPIError`; as tools deixam propagar (o
  FastMCP converte em erro de tool com a mensagem).
- `mark_as_read` com lista: falha em um chat não interrompe os demais; o item recebe
  `error: str` e os outros seguem.
- `TranscriptionError` é exceção própria, não subclasse de `EvolutionAPIError`, pra não
  confundir a origem. A mensagem sempre diz se o problema foi chave ausente, HTTP da
  OpenAI ou tipo de mídia.
- Diretórios não graváveis: erro de OS propaga com o caminho, sem swallow.

## Testes

`tests/test_read_markers.py`, `tests/test_chat_read.py`, `tests/test_media.py`,
`tests/test_transcription.py`, reaproveitando `FakeResponse`/`Recorder` de
`tests/test_message_reading.py` (extrair pra `tests/conftest.py`). Tudo com HTTP mockado
e `tmp_path`.

Casos obrigatórios:

- Store: get em arquivo ausente → `None`; set/get; arquivo corrompido → começa vazio;
  escrita deixa só o arquivo final (sem `.tmp` sobrando).
- `mark_chat_read`: `@lid` envia `remoteJidAlt`; grupo não chama `markMessageAsRead` e
  devolve `phoneCleared: false`; duplicatas por `id` são removidas; só mensagens
  `fromMe=false` e mais novas que o marcador entram; marcador gravado é o maior
  timestamp; `resolved: false` grava marcador e não envia receipt; lista vazia não chama
  a API.
- `annotate_chats_with_markers`: sem marcador mantém valor da Evolution; marcador
  atualizado zera; mensagem nova conta só recebidas após o marcador; página cheia marca
  `unreadCountIsLowerBound`; falha HTTP mantém valor da Evolution.
- `save_media`: grava arquivo com extensão certa pra `audio/ogg; codecs=opus`; resposta
  não contém a chave `base64`; segunda chamada devolve `cached: true` sem regravar;
  resposta da Evolution sem `base64` vira `EvolutionAPIError`.
- Transcrição: sem chave falha antes de qualquer HTTP; mídia não-áudio falha com o tipo;
  cache `.txt` evita a chamada OpenAI; `language` só vai no multipart quando informado;
  erro HTTP da OpenAI vira `TranscriptionError` com status.
- `transcribe_chat_audios`: item com erro não derruba a lista; filtra só `audioMessage`.
- `server.list_chats`: chama a anotação (teste leve via monkeypatch).

Validação ao vivo (não automatizada, registrada no PR): `mark_as_read` no contato cobaia
(`@lid`, `phoneCleared: true`) e no grupo cobaia (`phoneCleared: false`), `list_chats`
mostrando `unreadCount: 0` com `unreadSource: local_marker` nos dois, `download_media` +
`transcribe_audio` num áudio de grupo de baixo valor, `transcribe_chat_audios` numa
conversa indicada pelo Ian na hora. Marcar como lido mexe no WhatsApp real: só nas
cobaias, e mostrando o resultado antes de qualquer uso amplo.

## Documentação

- `README.md`: tools novas na seção "Tools Disponíveis"; env vars novas na configuração;
  nota sobre `OPENAI_API_KEY` vir do `settings.json` do Claude Code (herdada pelo processo
  do MCP) ou do `.env`; seção "Próximos passos" com `archiveChat`, ausência de mute na
  2.3.7 e o PR de `markChatRead` na Evolution que destravaria grupo.
- `.env.example`: `EVOLUTION_STATE_DIR`, `EVOLUTION_MEDIA_DIR`, `OPENAI_API_KEY`,
  `OPENAI_TRANSCRIBE_MODEL`, todos comentados como opcionais.
- `CHANGELOG.md`: `[1.3.0]`, com as três limitações da Evolution encontradas.
- `KNOWN_ISSUES.md`: issues novas: `@lid` descartado em `markMessageAsRead`,
  `participant` perdido (grupo), `unreadCount` que só sobe.
- `pyproject.toml`: versão `1.3.0`. Sem dependência nova.

## Riscos e suposições restantes

- O processo do MCP herdar o `env` do `settings.json` do Claude Code é suposição razoável
  (a variável aparece no shell da sessão), mas será confirmado na validação ao vivo. Se
  não herdar, o README manda passar `-e OPENAI_API_KEY=...` no `claude mcp add`, e a
  skill do marketplace é atualizada no PR separado.
- O teste de `@lid` foi feito com uma conversa marcada como não lida via `markChatUnread`,
  não com mensagens realmente novas. Comportamento deve ser o mesmo (o celular reage ao
  receipt por `id` da mensagem), mas fica registrado.
- Limite de 25 MB da OpenAI por arquivo não é problema pra áudio de WhatsApp (minutos, não
  horas); não há tratamento especial.
