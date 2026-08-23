# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/lang/pt-BR/).

---

## [1.2.0] - 2026-08-23

### 🐛 A Leitura de Mensagens Nunca Funcionou

Toda tool de leitura devolvia um feed global sem filtro em vez da conversa pedida. Como o
retorno era um JSON plausível em vez de um erro, isso se apresentava como "nenhuma
mensagem encontrada". Se você usou este servidor para triar conversas, **os resultados
anteriores não valem nada** — as conversas não foram lidas.

Diagnóstico reproduzido contra uma instância real (Evolution API v2, 831 conversas).
Detalhes e medições em [KNOWN_ISSUES.md](KNOWN_ISSUES.md) (issues #9 a #13).

### 🔧 Corrigido

#### Leitura de mensagens
- **`find_messages()` manda o filtro em `where.key.remoteJid`.** Antes mandava
  `{"chatId": ...}` solto no topo do corpo; a Evolution API descarta chaves
  desconhecidas em silêncio e devolvia a coleção inteira (104195 registros de 14 chats
  onde o correto eram 91 de 1).
- **`limit` virou `offset`** — o parâmetro de tamanho de página da Evolution API. Antes
  todo chamador recebia exatamente 50 registros, sempre.
- **Paginação de verdade:** parâmetro `page` em `find_messages()`,
  `get_messages_by_number()`, nas tools MCP `find_messages` / `get_chat_messages` e no
  endpoint `GET /messages/{number}`.

#### Endereçamento de conversas
- **`resolve_chat_jid()` resolve número → JID real.** O WhatsApp endereça muitas
  conversas como `<opaco>@lid`, onde o número só aparece em
  `lastMessage.key.remoteJidAlt` — na instância de teste, 337 `@lid` + 235 `@g.us` de
  831 conversas, ou seja **cerca de 69% eram inalcançáveis** montando
  `{numero}@s.whatsapp.net` à mão.
- **Grupos podem ser lidos.** `get_chat_messages` / `get_messages_by_number` aceitam um
  JID completo; antes `validate_phone_number()` rejeitava `@g.us` de saída.
- **Envio não transforma mais um JID em outro número.** `resolve_send_target()` repassa o
  JID intacto: remover os não-dígitos de `260992344797194@lid` produz uma string de 15
  dígitos que passa na validação de telefone e endereça outro destinatário.
- **O mapa de contatos não indexa mais um `@lid` como telefone**, e o enriquecimento de
  nomes de uma conversa `@lid` passou a usar `remoteJidAlt`.

#### HTTP server
- **`GET /chats` voltou a funcionar.** Chamava `client.find_chats(limit=limit)`, mas
  `find_chats()` não tem esse parâmetro — o endpoint sempre estourava com `TypeError`.
  O `response_model` também declarava `dict` onde a resposta é `list`.

### ✨ Adicionado

- **`tests/test_message_reading.py`** — 24 testes de regressão com a camada HTTP mockada
  (nada de instância viva): forma do corpo da requisição (`where` presente, `offset`
  carregando o tamanho de página), resolução de `@lid`, repasse de JID de grupo,
  paginação, cache de JID e não-cache do fallback, e o filtro de texto client-side.
  20 deles falham no código anterior.
- **`messages.clientSideFilter`** na resposta quando `query` é usado, com
  `{query, scope, scanned, matched}`.

### ⚠️ Limitação Conhecida

`query` é um filtro **client-side sobre a página buscada**, não uma busca no servidor.
A Evolution API descarta `where.message` (verificado: um termo impossível ainda devolve
todos os registros do chat), então não há como empurrar busca de texto para o banco. Um
`find_messages(query=...)` sem `chat_id` varre só as `limit` mensagens mais recentes da
instância e não prova ausência do termo. O campo `clientSideFilter` existe para deixar
esse escopo explícito.

## [1.1.0] - 2025-10-24

### 🐳 Docker & HTTP Support

Esta release adiciona suporte completo a Docker e modo HTTP, permitindo deploy em produção e acesso via API REST.

### ✨ Adicionado

#### HTTP Server (FastAPI)
- **Servidor HTTP REST** completo expondo todas as 14 ferramentas MCP
- **Swagger UI interativo** em `/docs` para testar endpoints
- **ReDoc** em `/redoc` com documentação alternativa
- **CORS configurado** para permitir chamadas de frontends
- **Pydantic models** para validação de requests
- **Healthcheck endpoint** em `/health` para monitoramento
- **14 endpoints REST:**
  - `POST /messages/text` - Enviar mensagem de texto
  - `POST /messages/media` - Enviar mídia
  - `GET /chats` - Listar conversas
  - `GET /contacts` - Listar contatos
  - `GET /messages/{number}` - Buscar mensagens
  - `GET /instance/status` - Status da instância
  - `POST /presence` - Definir presença
  - `POST /messages/mark-read` - Marcar como lido
  - `POST /chats/archive` - Arquivar conversa
  - `DELETE /chats/{number}` - Deletar conversa
  - `GET /profile/picture/{number}` - Foto de perfil
  - `GET /profile/status/{number}` - Status/bio
  - `POST /check-number` - Verificar número no WhatsApp
  - `GET /profile/business/{number}` - Perfil comercial
  - `POST /cache/clear` - Limpar cache manualmente

#### Docker Compose Stack
- **Stack completa** com 4 serviços orquestrados:
  - PostgreSQL 15 (database para Evolution API)
  - Redis 7 (cache e queue)
  - Evolution API (WhatsApp gateway)
  - MCP HTTP Server (nosso servidor REST)
- **Dockerfile multi-stage** para imagem otimizada
- **Healthchecks** em todos os serviços
- **Volumes persistentes** para dados críticos
- **Network isolada** para comunicação entre containers
- **Variáveis de ambiente** via `.env.docker`
- **Usuário não-root** no container (segurança)

#### Documentação Docker
- **docker/README.md** (500+ linhas) com:
  - Quick start (3 comandos)
  - Guia de QR code para conectar WhatsApp
  - Exemplos de uso da API
  - Troubleshooting completo
  - Procedimentos de backup/restore
  - Comandos úteis (logs, restart, cleanup)
  - Práticas de segurança
- **docker/.env.docker.example** com template de configuração
- **README.md principal atualizado** com seção Docker

### 🔧 Modificado

#### Dependencies
- Adicionado `fastapi>=0.104.0` para servidor HTTP
- Adicionado `uvicorn[standard]>=0.24.0` para ASGI server

#### README.md
- Nova seção "Quick Start com Docker"
- Seção "Modos de Uso" explicando stdio vs HTTP
- Pré-requisitos atualizados incluindo Docker

### 📊 Estatísticas

- **1 novo servidor HTTP** com 14 endpoints REST
- **500+ linhas** de documentação Docker
- **398 linhas** de código HTTP server
- **Stack completa** production-ready
- **Dual-mode** support (stdio + HTTP)

### 🎯 Use Cases

**Modo Stdio (Local):**
- Uso pessoal com Claude Desktop
- Desenvolvimento e testes
- Sem necessidade de servidor

**Modo HTTP (Docker):**
- Deploy em produção
- Acesso remoto/equipes
- Integração com outros sistemas
- Auto-healing com healthchecks
- Escalabilidade horizontal

### 🔒 Segurança

- Container roda com usuário não-root
- Multi-stage build (menor superfície de ataque)
- Variáveis sensíveis via environment
- `.env.docker` no gitignore
- HTTPS recomendado para produção (via reverse proxy)

---

## [1.0.0] - 2025-10-24

### 🎉 Primeira Release Estável!

Esta é a primeira release production-ready do Evolution API MCP Server, com todas as issues críticas resolvidas e funcionalidade completa.

### ✨ Adicionado

#### Core Features
- **14 ferramentas MCP** para integração completa com WhatsApp via Evolution API:
  - `get_chats` - Lista conversas recentes com enriquecimento de nomes
  - `get_contacts` - Busca contatos (unificado com filtros opcionais)
  - `get_messages` - Busca mensagens de uma conversa
  - `send_text` - Envia mensagens de texto
  - `send_media` - Envia mídias (imagem, vídeo, documento, áudio)
  - `get_instance_status` - Status da instância
  - `set_presence` - Define presença (online, offline, etc)
  - `mark_as_read` - Marca mensagem como lida
  - `archive_chat` - Arquiva conversa
  - `delete_chat` - Deleta conversa
  - `get_profile_picture` - Busca foto de perfil
  - `get_profile_status` - Busca status/bio
  - `check_number` - Verifica se número está no WhatsApp
  - `get_business_profile` - Busca perfil comercial

#### Otimizações de Performance
- **Cache inteligente de contatos** com TTL de 5 minutos
- **Enriquecimento automático** de nomes em conversas (bulk fetch)
- **Método `clear_cache()`** para limpeza manual do cache
- Redução de N+1 requests para 2 requests fixos

#### Validações Robustas
- Validação de `media_type` contra tipos permitidos
- Validação de URLs (HTTP/HTTPS) para mídias
- Validação de tamanho de texto (65KB limit do WhatsApp)
- Validação de tamanho de caption (1024 caracteres)
- Mensagens de erro descritivas antes de chamar a API

#### Documentação Completa
- README.md com instalação, configuração e exemplos
- ROADMAP.md com plano de desenvolvimento de 4 fases
- TODO.md com tarefas granulares
- KNOWN_ISSUES.md com issues documentadas e soluções
- LICENSE (MIT)
- Este CHANGELOG.md

### 🔧 Corrigido

#### Issue #1: Duplicação de Código ✅
- **Problema:** Funções `fetch_contacts()` e `find_contacts()` duplicadas
- **Solução:** Unificadas em `fetch_contacts(contact_id=None)`
- **Impacto:** Código mais limpo, menos confusão para LLM

#### Issue #2: Cache Sem Expiração ✅
- **Problema:** Cache de nomes nunca expirava, causando nomes desatualizados
- **Solução:** Implementado TTL de 5 minutos com auto-refresh
- **Impacto:** Nomes sempre atualizados sem necessidade de restart

#### Issue #3: Validações Ausentes ✅
- **Problema:** Validações só na API, erros tardios e genéricos
- **Solução:** Validações client-side com mensagens descritivas
- **Impacto:** Erros detectados imediatamente com feedback claro

#### Issue #4: Endpoint Incorreto de Contatos ✅
- **Problema:** Endpoint `/chat/contacts/{instanceId}` retornava 404
- **Solução:** Corrigido para `/chat/findContacts/{instanceId}`
- **Impacto:** Nomes de contatos aparecendo corretamente

#### Issue #5: Formato de Resposta Incorreto ✅
- **Problema:** Esperava `{"data": [...]}` mas recebia lista direta
- **Solução:** Atualizado parsing para aceitar lista direta
- **Impacto:** 923 contatos detectados e 922 nomes mapeados

### 🧪 Testado

- **Suite de testes automáticos** (`test_phase1.py`)
- **11 testes, 100% de sucesso:**
  - 6 testes de validação
  - 3 testes de cache
  - 2 testes de deduplicação
- Testado com instância real (1170+ contatos)

### 📚 Documentação

#### Arquivos Criados
- `README.md` - Guia completo de uso
- `ROADMAP.md` - Planejamento de 4 fases
- `TODO.md` - Tarefas granulares
- `KNOWN_ISSUES.md` - Documentação de issues
- `LICENSE` - MIT License
- `CHANGELOG.md` - Este arquivo

#### Documentação de Código
- Docstrings completas em todas funções
- Type hints em Python 3.10+
- Exemplos de uso em docstrings
- Comentários explicativos em lógica complexa

### 🏗️ Estrutura Técnica

```
evoapi-mcp/
├── src/evoapi_mcp/
│   ├── __init__.py
│   ├── server.py        # MCP Server (14 tools)
│   ├── client.py        # HTTP Client com validações
│   └── config.py        # Configuração
├── test_phase1.py       # Suite de testes
├── README.md
├── ROADMAP.md
├── TODO.md
├── KNOWN_ISSUES.md
├── CHANGELOG.md
├── LICENSE
└── pyproject.toml
```

### 🔒 Segurança

- API key nunca exposta em logs
- Validação de URLs para prevenir SSRF
- Validação de inputs antes de processar
- Timeout configurável para prevenir DoS

### 📦 Dependências

- `fastmcp >= 0.6.0` - Framework MCP
- `requests >= 2.32.3` - HTTP client
- `python-dotenv >= 1.0.1` - Gerenciamento de .env

### 🎯 Compatibilidade

- **Python:** 3.10+
- **Evolution API:** v2.x
- **Claude Desktop:** Latest
- **OS:** macOS, Linux, Windows

### 📊 Estatísticas

- **14 ferramentas MCP** implementadas
- **5 issues críticas** resolvidas
- **1170+ contatos** testados em produção
- **922 nomes** enriquecidos automaticamente
- **100% testes** passando

---

## [0.1.0] - 2025-10-23

### Versão Inicial (Pré-Release)

- Implementação inicial do MCP Server
- Integração básica com Evolution API
- 14 ferramentas funcionais
- Documentação básica

---

## Links

- [GitHub Repository](https://github.com/PabloBispo/evoapi-mcp)
- [Evolution API Documentation](https://doc.evolution-api.com/)
- [Model Context Protocol](https://modelcontextprotocol.io/)

---

## Convenções de Versionamento

Este projeto usa [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.x.x): Mudanças incompatíveis na API
- **MINOR** (x.1.x): Novas funcionalidades compatíveis
- **PATCH** (x.x.1): Correções de bugs compatíveis

## Tipos de Mudanças

- `Adicionado` - Novas funcionalidades
- `Modificado` - Mudanças em funcionalidades existentes
- `Descontinuado` - Funcionalidades que serão removidas
- `Removido` - Funcionalidades removidas
- `Corrigido` - Correções de bugs
- `Segurança` - Correções de vulnerabilidades
