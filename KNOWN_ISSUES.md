# 🐛 Known Issues - Evolution API MCP Server

Problemas conhecidos, limitações e workarounds.

**Última atualização:** 2026-08-23

---

## 🔴 Crítico

### Issue #1: Duplicação de Código - fetch_contacts vs find_contacts

**Status:** ✅ Resolvido (2025-10-23)
**Prioridade:** Alta
**Arquivo:** `src/evoapi_mcp/client.py:367-450`

**Descrição:**
Duas funções fazem essencialmente a mesma coisa:

```python
# Linha 306
def fetch_contacts(self) -> list[dict[str, Any]]:
    result = self._make_request("POST", "/chat/findContacts/{instanceId}", data={})
    ...

# Linha 327
def find_contacts(self, contact_id: str | None = None) -> list[dict[str, Any]]:
    payload = {}
    if contact_id:
        payload["where"] = {"id": contact_id}
    result = self._make_request("POST", "/chat/findContacts/{instanceId}", data=payload)
    ...
```

Ambas chamam o mesmo endpoint, apenas com filtros diferentes.

**Impacto:**
- Código duplicado
- Confunde o LLM ao escolher qual ferramenta usar
- Mais difícil de manter

**Solução Proposta:**
```python
def fetch_contacts(
    self,
    contact_id: str | None = None,
    filters: dict | None = None
) -> list[dict[str, Any]]:
    """Busca contatos com filtros opcionais.

    Args:
        contact_id: ID específico do contato
        filters: Filtros adicionais (where, limit, etc)
    """
    payload = {}
    if contact_id:
        payload["where"] = {"id": contact_id}
    if filters:
        payload.update(filters)

    result = self._make_request("POST", "/chat/findContacts/{instanceId}", data=payload)
    # ... resto da lógica
```

**Solução Aplicada:**
Unificadas em uma única função `fetch_contacts()` com parâmetro opcional `contact_id`.
Removida a tool `find_contact()` do server, mantendo apenas `get_contacts()` que aceita
tanto `contact_id` quanto `limit`.

---

### Issue #2: Cache de Contatos Nunca Expira

**Status:** ✅ Resolvido (2025-10-23)
**Prioridade:** Alta
**Arquivo:** `src/evoapi_mcp/client.py:65-67`

**Descrição:**
O cache de nomes de contatos é criado na inicialização e nunca expira:

```python
def __init__(self, config: EvolutionConfig):
    # ...
    self._contact_names_cache: dict[str, str | None] = {}
```

Se um contato mudar o nome no WhatsApp, o cache fica desatualizado até reiniciar o Claude Desktop.

**Impacto:**
- Nomes desatualizados podem aparecer
- Único jeito de atualizar é reiniciar o Claude Desktop

**Solução Proposta:**
Adicionar TTL (Time To Live) no cache:

```python
from datetime import datetime, timedelta

class EvolutionClient:
    def __init__(self, config):
        self._contact_names_cache = {}
        self._cache_timestamp: datetime | None = None
        self._cache_ttl = timedelta(minutes=5)

    def _is_cache_expired(self) -> bool:
        if not self._cache_timestamp:
            return True
        return datetime.now() - self._cache_timestamp > self._cache_ttl

    def _build_contacts_map(self):
        if self._is_cache_expired():
            # Recarrega
            ...
            self._cache_timestamp = datetime.now()
        return self._contact_cache
```

**Solução Aplicada:**
Implementado TTL de 5 minutos no cache:
- Adicionado `_cache_timestamp` e `_cache_ttl = timedelta(minutes=5)`
- Criado método `_is_cache_expired()` para verificar expiração
- Criado método público `clear_cache()` para limpeza manual
- Atualizado `_build_contacts_map()` para verificar expiração e reconstruir quando necessário
- Atualizado `get_contact_name()` para respeitar TTL do cache

---

### Issue #3: Sem Validação de media_type em send_media()

**Status:** ✅ Resolvido (2025-10-23)
**Prioridade:** Alta
**Arquivo:** `src/evoapi_mcp/client.py:498-543`

**Descrição:**
A função `send_media()` aceita qualquer string como `media_type`:

```python
def send_media(
    self,
    number: str,
    media_url: str,
    media_type: str,  # ❌ Sem validação!
    caption: str | None = None,
    filename: str | None = None
):
    payload = {
        "mediatype": media_type,  # Vai direto pra API
        ...
    }
```

Valores inválidos só são detectados quando a API retorna erro.

**Impacto:**
- Erro tarde demais (após chamada HTTP)
- Mensagem de erro genérica da API
- Pior experiência do desenvolvedor

**Exemplo do Problema:**
```python
# Isso não dá erro até chamar a API:
client.send_media(
    number="5511999999999",
    media_url="https://example.com/file.pdf",
    media_type="pdf"  # ❌ Deveria ser "document"
)
```

**Solução Proposta:**
```python
VALID_MEDIA_TYPES = {"image", "video", "document", "audio"}

def send_media(self, ..., media_type: str, ...):
    if media_type not in VALID_MEDIA_TYPES:
        raise ValueError(
            f"media_type inválido: '{media_type}'. "
            f"Valores válidos: {', '.join(VALID_MEDIA_TYPES)}"
        )
    ...
```

**Solução Aplicada:**
Implementadas validações completas em `send_media()` e `send_text()`:
- Constantes: `VALID_MEDIA_TYPES`, `MAX_TEXT_LENGTH`, `MAX_CAPTION_LENGTH`
- Método `validate_media_type()` que valida contra tipos permitidos
- Método `validate_url()` que valida URLs de mídia
- Método `validate_text_length()` que valida tamanho de textos e captions
- Todas as validações lançam `ValueError` com mensagens descritivas antes da chamada à API

---

### Issue #9: `find_messages()` Ignora o Filtro de Chat em Silêncio

**Status:** ✅ Resolvido (2026-08-23)
**Prioridade:** Alta
**Arquivo:** `src/evoapi_mcp/client.py` (`find_messages`)

**Descrição:**
O corpo da requisição mandava as chaves de filtro soltas no topo do JSON:

```python
payload = {}
if query:
    payload["query"] = query
if chat_id:
    payload["chatId"] = chat_id
if limit:
    payload["limit"] = limit
```

`POST /chat/findMessages/{instance}` espera o filtro dentro de um objeto `where`.
Chaves desconhecidas no topo são descartadas sem erro, então a API devolvia a coleção
inteira. Medido no mesmo chat de uma instância com 831 conversas:

| Corpo | total | remoteJids distintos |
|---|---|---|
| `{"where":{"key":{"remoteJid": JID}}}` | 91 | 1 (correto) |
| `{"chatId": JID, "limit": 20}` | 104195 | 14 (sem filtro) |

**Impacto:**
Toda leitura de mensagem devolvia um feed global. Como o retorno era um JSON plausível
em vez de um erro, isso se apresentava como "nenhuma mensagem encontrada" — várias
triagens reportaram conversas como limpas quando elas simplesmente nunca foram lidas.
Este é o pior tipo de bug: falha silenciosa com aparência de sucesso.

**Solução Aplicada:**
`find_messages()` agora manda `where.key.remoteJid`. O mesmo arquivo já usava o padrão
correto em `fetch_contacts()` (`payload["where"] = {"id": contact_id}`) — era uma
inconsistência interna, não uma ambiguidade da API.

---

### Issue #10: Endereçamento `@lid` Não é Tratado

**Status:** ✅ Resolvido (2026-08-23)
**Prioridade:** Alta
**Arquivo:** `src/evoapi_mcp/client.py` (`get_messages_by_number`)

**Descrição:**
O JID era construído à mão a partir do número:

```python
clean_number = self.validate_phone_number(number)
chat_id = f"{clean_number}@s.whatsapp.net"
```

O WhatsApp endereça muitas conversas como `<opaco>@lid` (ex: `100000000000000@lid`),
onde o número de telefone só aparece em `chat.lastMessage.key.remoteJidAlt`. Na
instância de teste: **337 `@lid` + 235 `@g.us` de 831 conversas — cerca de 69%
inalcançáveis** por essa construção. `validate_phone_number()` também rejeita JID de
grupo ("Número inválido"), então grupos nunca podiam ser lidos por essa porta de entrada.

**Impacto:**
Ler uma conversa pelo número falhava para a maioria das conversas, e grupos eram
inacessíveis por completo.

**Solução Aplicada:**
Novo `resolve_chat_jid()`: repassa qualquer coisa com `@` (grupos e JIDs explícitos) e
resolve um número contra `find_chats()`, comparando `remoteJid` e
`lastMessage.key.remoteJidAlt`. Só resolução bem-sucedida entra no cache — o fallback
`{numero}@s.whatsapp.net` nunca é cacheado, para que uma conversa que apareça depois
ainda seja encontrada.

---

### Issue #11: `limit` é Ignorado; o Parâmetro de Página é `offset`

**Status:** ✅ Resolvido (2026-08-23)
**Prioridade:** Alta
**Arquivo:** `src/evoapi_mcp/client.py` (`find_messages`)

**Descrição:**
A Evolution API usa `offset` como tamanho de página e `page` como número da página.
Um `limit` no topo do corpo não faz nada:

| Corpo | registros |
|---|---|
| `{"where":…, "limit": 10}` | 50 |
| `{"where":…, "offset": 10}` | 10 |
| `{"where":…, "page": 2, "offset": 10}` | 10 (página 2) |

**Impacto:**
Todo chamador recebia exatamente 50 registros, sem jeito de paginar — uma conversa com
629 mensagens era irrecuperável além das 50 primeiras.

**Solução Aplicada:**
`limit` é mapeado para `offset` e um parâmetro `page` foi adicionado a
`find_messages()`, `get_messages_by_number()`, às tools MCP `find_messages` e
`get_chat_messages`, e ao endpoint `GET /messages/{number}`.

---

### Issue #12: `@lid` Tratado como Número em Envios e no Mapa de Contatos

**Status:** ✅ Resolvido (2026-08-23)
**Prioridade:** Alta
**Arquivo:** `src/evoapi_mcp/client.py` (`send_text`, `send_media`, `set_presence`, `_build_contacts_map`)

**Descrição:**
Encontrado auditando a mesma classe de bug das issues #9-#11. Os envios normalizavam o
destino com `validate_phone_number()`, que remove os não-dígitos: `100000000000000@lid`
virava `100000000000000`, uma string de 15 dígitos que **passa** na validação de telefone
e endereça um destinatário diferente — possivelmente real. Um JID de grupo era rejeitado,
o que ao menos falhava alto.

`_build_contacts_map()` e o enriquecimento de nomes em `find_chats()` faziam
`remote_jid.replace("@s.whatsapp.net", "")` seguido de remoção de não-dígitos, o que
indexa o id opaco de um `@lid` como se fosse número de telefone.

**Impacto:**
Mandar mensagem para o destinatário errado, silenciosamente. Nomes de contato
potencialmente cruzados entre pessoas diferentes.

**Solução Aplicada:**
Novo `resolve_send_target()`: repassa JID intacto, valida número puro. Novo
`_personal_jid_number()`, que só extrai número de JID `@s.whatsapp.net` e devolve vazio
para `@lid`/`@g.us`. O enriquecimento de `find_chats()` passou a usar
`lastMessage.key.remoteJidAlt` para achar o nome de uma conversa `@lid`.

O envio para grupo e para `@lid` **não foi verificado ao vivo** (mandar mensagem de
teste para terceiros estava fora de escopo); o que foi verificado é que o JID chega
intacto ao corpo da requisição em vez de ser transformado em outro número.

---

### Issue #13: A API Não Suporta Busca de Texto no Servidor

**Status:** 🟢 Aberto (limitação da Evolution API, não do MCP)
**Prioridade:** Média
**Arquivo:** `src/evoapi_mcp/client.py` (`_apply_text_filter`)

**Descrição:**
`POST /chat/findMessages` descarta `where.message` por completo. Verificado contra uma
instância real (196 mensagens no chat): buscar por um termo impossível
(`zzzzzzUNLIKELYzzzzz`) ainda devolve as 196. Só `where.key` chega ao Prisma — e
`key.fromMe: false` também é descartado, por ser falsy no controller.

**Impacto:**
`query` só pode ser aplicado no cliente, ou seja **apenas sobre a página buscada**. Um
`find_messages(query=...)` sem `chat_id` varre só as `limit` mensagens mais recentes da
instância inteira e **não prova** que o termo nunca foi dito.

**Workaround Atual:**
O filtro client-side devolve `messages.clientSideFilter` com
`{query, scope, scanned, matched, pages_scanned}`, para que um resultado vazio mostre o
que foi de fato varrido em vez de parecer uma resposta definitiva. Para buscar dentro de
uma conversa, passe `chat_id` com um `limit` alto e use `max_pages` (desde 1.2.1) para
varrer várias páginas numa chamada — a varredura para na primeira página vazia.

### Issue #14: Fallback de JID Invisível pro Chamador

**Status:** ✅ Resolvido em 2026-08-27
**Prioridade:** Média
**Arquivo:** `src/evoapi_mcp/client.py` (`resolve_chat_jid_detail`, `find_messages`)

**Descrição:**
`resolve_chat_jid()` cai pro palpite `<numero>@s.whatsapp.net` quando o número não bate
com nenhuma conversa da lista, e sinalizava isso apenas num log `WARNING`. Pro chamador,
a leitura voltava como uma conversa que existe e está vazia.

**Impacto:**
A mesma confusão da issue #9 em escala menor: `records: []` podia significar "conversa sem
mensagens" ou "conversa nunca encontrada", e nada na resposta distinguia os dois. Quem
tria conversa lê os dois como "nada aqui".

**Solução:**
`resolve_chat_jid_detail()` devolve `(jid, resolved)` e `find_messages()` anexa
`messages.chatResolution` com `{requested, jid, resolved}`. JID explícito conta como
resolvido; leitura sem `chat_id` não recebe o relatório. `resolve_chat_jid()` continua
devolvendo só a string, para não quebrar chamador existente.

## 🟡 Médio

### Issue #4: Type Hints Muito Genéricos

**Status:** 🟡 Aberto
**Prioridade:** Média
**Arquivo:** `src/evoapi_mcp/client.py` (vários locais)

**Descrição:**
Muitas funções retornam `dict[str, Any]`, o que não ajuda o desenvolvedor:

```python
def find_chats(...) -> dict[str, Any]:  # O que tem nesse dict?
def send_text(...) -> dict[str, Any]:   # E nesse?
def fetch_contacts(...) -> list[dict[str, Any]]:  # E aqui?
```

**Impacto:**
- Sem autocomplete no IDE
- Não detecta erros em tempo de desenvolvimento
- Código menos type-safe

**Solução Proposta:**
Usar Pydantic para criar models:

```python
from pydantic import BaseModel

class Contact(BaseModel):
    remote_jid: str
    push_name: str | None
    is_group: bool
    profile_pic_url: str | None

class Chat(BaseModel):
    remote_jid: str
    push_name: str | None
    last_message: dict | None
    unread_count: int

def find_chats(...) -> list[Chat]:  # ✅ Type-safe!
def fetch_contacts(...) -> list[Contact]:  # ✅ Type-safe!
```

**Workaround Atual:**
Consultar documentação ou código-fonte para saber o formato.

---

### Issue #5: Sem Retry em Falhas Temporárias

**Status:** 🟡 Aberto
**Prioridade:** Média
**Arquivo:** `src/evoapi_mcp/client.py:99-168`

**Descrição:**
A função `_make_request()` não tenta novamente em caso de falhas temporárias:

```python
def _make_request(self, ...):
    response = requests.request(...)  # ❌ Se falhar → erro imediato
    response.raise_for_status()
```

**Impacto:**
- Falhas temporárias de rede causam erro
- Usuário precisa tentar novamente manualmente

**Exemplo do Problema:**
```python
# Se a rede estiver instável:
client.send_text(...)  # Pode falhar com ConnectionError
# Usuário precisa executar comando novamente
```

**Solução Proposta:**
Usar biblioteca `tenacity` para retry automático:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((ConnectionError, Timeout))
)
def _make_request(self, ...):
    ...
```

**Workaround Atual:**
Usuário tenta novamente manualmente.

---

### Issue #6: Logs Podem Expor API Key

**Status:** 🟡 Aberto
**Prioridade:** Média
**Arquivo:** `src/evoapi_mcp/client.py:146`

**Descrição:**
Ao logar erros HTTP, o response.text pode conter informações sensíveis:

```python
except requests.exceptions.HTTPError as e:
    error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
    self._log(error_msg, "ERROR")  # ⚠️ Pode ter API key!
```

Algumas APIs retornam headers ou detalhes que incluem credenciais.

**Impacto:**
- Risco de segurança
- API key pode aparecer em logs

**Solução Proposta:**
Sanitizar response antes de logar:

```python
def _sanitize_error(self, text: str) -> str:
    """Remove informações sensíveis."""
    return text.replace(self.api_key, "***APIKEY***")

except requests.exceptions.HTTPError as e:
    error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
    self._log(self._sanitize_error(error_msg), "ERROR")
```

**Workaround Atual:**
Não compartilhar logs públicos.

---

## 🟢 Baixo

### Issue #7: Timeout Muito Alto (30s)

**Status:** 🟢 Aberto
**Prioridade:** Baixa
**Arquivo:** `src/evoapi_mcp/config.py:21`

**Descrição:**
Timeout padrão é 30 segundos:

```python
timeout: int = 30  # Muito tempo para usuário esperar
```

Se a API estiver lenta, usuário fica esperando 30 segundos antes de ver erro.

**Impacto:**
- Experiência ruim quando API está lenta
- Usuário acha que travou

**Solução Proposta:**
Reduzir para 10-15 segundos:

```python
timeout: int = 15  # Mais razoável
```

**Workaround Atual:**
Configurar `EVOLUTION_TIMEOUT=15` no `.env`.

---

### Issue #8: Nomenclatura Confusa para LLM

**Status:** 🟢 Aberto
**Prioridade:** Baixa
**Arquivo:** `src/evoapi_mcp/server.py`

**Descrição:**
Alguns tools têm nomes similares que podem confundir o LLM:

```python
get_chat_messages()  # Mensagens de um chat
find_messages()      # Busca em todos os chats

get_contacts()       # Lista contatos
find_contact()       # Busca contatos (mesma coisa?)
```

**Impacto:**
- LLM pode escolher tool errado
- Usuário recebe resultado inesperado

**Solução Proposta:**
Renomear para maior clareza:

```python
get_messages_from_chat()      # Claro que é de um chat específico
search_messages_globally()    # Claro que busca em todos
```

**Workaround Atual:**
Docstrings bem detalhadas ajudam o LLM a escolher certo.

---

## 📊 Estatísticas

### Por Prioridade
- 🔴 Crítico: 0 issues abertas (7 resolvidas)
- 🟡 Médio: 4 issues abertas (1 é limitação da API upstream) + 1 resolvida
- 🟢 Baixo: 2 issues

### Por Status
- 🔴 Aberto: 6 issues
- ✅ Resolvido: 8 issues

---

## 🔄 Issues Resolvidas

### ✅ Issue #1: Duplicação de Código (Resolvido em 2025-10-23)
Unificadas `fetch_contacts()` e `find_contacts()` em uma única função com parâmetro opcional.

### ✅ Issue #2: Cache Nunca Expira (Resolvido em 2025-10-23)
Implementado TTL de 5 minutos com métodos `_is_cache_expired()` e `clear_cache()`.

### ✅ Issue #3: Sem Validação de media_type (Resolvido em 2025-10-23)
Adicionadas validações completas para media_type, URLs e tamanhos de texto/caption.

### ✅ Issue #9: Filtro de Chat Ignorado (Resolvido em 2026-08-23)
`find_messages()` passou a mandar `where.key.remoteJid` em vez de `chatId` solto no topo.

### ✅ Issue #10: Endereçamento `@lid` (Resolvido em 2026-08-23)
`resolve_chat_jid()` resolve número → JID real (`@lid` incluso) e repassa JID de grupo.

### ✅ Issue #11: `limit` Ignorado (Resolvido em 2026-08-23)
`limit` virou `offset` e um parâmetro `page` foi adicionado à leitura de mensagens.

### ✅ Issue #12: `@lid` Como Número em Envios (Resolvido em 2026-08-23)
`resolve_send_target()` e `_personal_jid_number()` pararam de transformar um JID `@lid`
em um número de telefone diferente.

### ✅ Issue #14: Fallback de JID Invisível (Resolvido em 2026-08-27)
A resposta de leitura agora traz `messages.chatResolution`.

---

## 📝 Como Reportar Nova Issue

1. Adicione seção com título descritivo
2. Defina Status (🔴/🟡/🟢)
3. Defina Prioridade (Alta/Média/Baixa)
4. Informe arquivo e linha
5. Descreva o problema com código
6. Explique o impacto
7. Proponha solução
8. Documente workaround se existir

**Template:**
```markdown
### Issue #X: Título Descritivo

**Status:** 🔴 Aberto
**Prioridade:** Alta
**Arquivo:** `path/to/file.py:123`

**Descrição:**
...código exemplo...

**Impacto:**
- ...

**Solução Proposta:**
...código proposto...

**Workaround Atual:**
...
```

---

**Última revisão:** 2026-08-27
