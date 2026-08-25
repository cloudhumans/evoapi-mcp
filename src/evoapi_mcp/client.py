"""Cliente HTTP direto para Evolution API."""

import sys
import re
import requests
from datetime import datetime, timedelta
from typing import Any
from pathlib import Path

# Adiciona o diretório src ao path para permitir importações
src_dir = Path(__file__).parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from evoapi_mcp.config import EvolutionConfig


# Constantes de validação
VALID_MEDIA_TYPES = {"image", "video", "document", "audio"}
VALID_PRESENCE_STATUS = {"available", "unavailable", "composing", "recording"}
MAX_TEXT_LENGTH = 65536  # 64KB - limite do WhatsApp
MAX_CAPTION_LENGTH = 1024  # Limite de legenda
PERSONAL_JID_SUFFIX = "@s.whatsapp.net"
GROUP_JID_SUFFIX = "@g.us"


class EvolutionAPIError(Exception):
    """Erro base para operações da Evolution API."""
    pass


class InstanceDisconnectedError(EvolutionAPIError):
    """Erro quando a instância não está conectada."""
    pass


class InvalidPhoneNumberError(EvolutionAPIError):
    """Erro quando o número de telefone é inválido."""
    pass


class EvolutionClient:
    """Cliente HTTP direto para Evolution API.

    Faz chamadas HTTP diretas à API REST seguindo a documentação oficial.
    Usa o header 'apikey' para autenticação e {instanceId} nos endpoints.
    """

    def __init__(self, config: EvolutionConfig):
        """Inicializa o cliente Evolution API.

        Args:
            config: Configuração da Evolution API
        """
        self.config = config
        self.base_url = config.base_url.rstrip('/')
        self.api_key = config.api_token
        self.instance_id = config.instance_name
        self.timeout = config.timeout

        # Headers padrão para todas as requisições
        self.headers = {
            'apikey': self.api_key,
            'Content-Type': 'application/json'
        }

        # Cache de nomes de contatos (número -> nome)
        self._contact_names_cache: dict[str, str | None] = {}
        self._jid_cache: dict[str, tuple[str, datetime]] = {}
        self._cache_timestamp: datetime | None = None
        self._cache_ttl = timedelta(minutes=5)  # Cache expira após 5 minutos

        self._log(f"Cliente inicializado para instância '{self.instance_id}'")

    def _log(self, message: str, level: str = "INFO") -> None:
        """Registra uma mensagem no stderr.

        Args:
            message: Mensagem a ser registrada
            level: Nível do log (INFO, WARNING, ERROR)
        """
        print(f"[{level}] Evolution API: {message}", file=sys.stderr)

    @staticmethod
    def validate_phone_number(number: str) -> str:
        """Valida e normaliza um número de telefone.

        O número deve estar no formato internacional sem '+' ou espaços.
        Exemplo: 5511999999999 (Brasil)

        Args:
            number: Número de telefone a validar

        Returns:
            str: Número normalizado

        Raises:
            InvalidPhoneNumberError: Se o número for inválido
        """
        # Remove caracteres não numéricos
        clean_number = re.sub(r'\D', '', number)

        # Valida formato básico (mínimo 10 dígitos, máximo 15)
        if not re.match(r'^\d{10,15}$', clean_number):
            raise InvalidPhoneNumberError(
                f"Número inválido: '{number}'. "
                "Use formato internacional sem '+' (ex: 5511999999999)"
            )

        return clean_number

    @staticmethod
    def validate_url(url: str, param_name: str = "url") -> None:
        """Valida se uma URL é válida.

        Args:
            url: URL a validar
            param_name: Nome do parâmetro (para mensagem de erro)

        Raises:
            ValueError: Se a URL for inválida
        """
        if not url or not isinstance(url, str):
            raise ValueError(f"{param_name} não pode ser vazio")

        if not url.startswith(("http://", "https://")):
            raise ValueError(
                f"{param_name} inválida: '{url}'. "
                "URL deve começar com http:// ou https://"
            )

    @staticmethod
    def validate_text_length(text: str, max_length: int, param_name: str = "text") -> None:
        """Valida o tamanho de um texto.

        Args:
            text: Texto a validar
            max_length: Tamanho máximo permitido
            param_name: Nome do parâmetro (para mensagem de erro)

        Raises:
            ValueError: Se o texto exceder o tamanho máximo
        """
        if len(text) > max_length:
            raise ValueError(
                f"{param_name} muito longo: {len(text)} caracteres. "
                f"Máximo permitido: {max_length} caracteres"
            )

    @staticmethod
    def validate_media_type(media_type: str) -> None:
        """Valida o tipo de mídia.

        Args:
            media_type: Tipo de mídia a validar

        Raises:
            ValueError: Se o tipo de mídia for inválido
        """
        if media_type not in VALID_MEDIA_TYPES:
            raise ValueError(
                f"media_type inválido: '{media_type}'. "
                f"Valores válidos: {', '.join(sorted(VALID_MEDIA_TYPES))}"
            )

    def _is_cache_expired(self) -> bool:
        """Verifica se o cache de contatos expirou.

        Returns:
            bool: True se o cache expirou ou nunca foi construído, False caso contrário
        """
        if not self._cache_timestamp:
            return True
        return datetime.now() - self._cache_timestamp > self._cache_ttl

    def clear_cache(self) -> None:
        """Limpa o cache de nomes de contatos e o de JIDs resolvidos.

        Este método é útil quando você quer forçar a atualização dos nomes
        dos contatos sem precisar reiniciar o cliente.

        Example:
            client.clear_cache()  # Cache será reconstruído na próxima chamada
        """
        self._contact_names_cache.clear()
        self._jid_cache.clear()
        self._cache_timestamp = None
        self._log("Cache de contatos limpo")

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: dict | None = None,
        params: dict | None = None
    ) -> dict[str, Any]:
        """Faz uma requisição HTTP à API.

        Args:
            method: Método HTTP (GET, POST, PUT, DELETE)
            endpoint: Endpoint da API (ex: /chat/findChats/{instanceId})
            data: Dados do corpo da requisição (para POST/PUT)
            params: Parâmetros de query string (para GET)

        Returns:
            dict: Resposta JSON da API

        Raises:
            EvolutionAPIError: Se houver erro na requisição
        """
        # Substitui {instanceId} no endpoint
        endpoint = endpoint.replace('{instanceId}', self.instance_id)
        url = f"{self.base_url}{endpoint}"

        try:
            self._log(f"{method} {endpoint}")

            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                json=data,
                params=params,
                timeout=self.timeout
            )

            # Verifica se a resposta foi bem-sucedida
            response.raise_for_status()

            # Tenta retornar JSON, se houver
            try:
                return response.json()
            except ValueError:
                return {"status": "success", "data": response.text}

        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            self._log(error_msg, "ERROR")

            # Detecta erros específicos
            if e.response.status_code == 401:
                raise EvolutionAPIError("Falha de autenticação. Verifique o EVOLUTION_API_TOKEN")
            elif e.response.status_code == 404:
                raise EvolutionAPIError(f"Endpoint não encontrado: {endpoint}")
            else:
                raise EvolutionAPIError(error_msg)

        except requests.exceptions.Timeout:
            raise EvolutionAPIError(
                f"Timeout ao executar {method} {endpoint}. "
                f"Tente novamente ou aumente EVOLUTION_TIMEOUT"
            )

        except requests.exceptions.ConnectionError as e:
            raise EvolutionAPIError(f"Erro de conexão: {str(e)}")

        except Exception as e:
            self._log(f"Erro inesperado: {str(e)}", "ERROR")
            raise EvolutionAPIError(f"Erro em {method} {endpoint}: {str(e)}")

    # =========================================================================
    # CHAT OPERATIONS
    # =========================================================================

    def find_chats(self, enrich_with_names: bool = True) -> dict[str, Any]:
        """Busca todas as conversas ativas.

        Endpoint: POST /chat/findChats/{instanceId}

        Args:
            enrich_with_names: Se True, enriquece conversas com nomes dos contatos quando pushName for null

        Returns:
            dict: Lista de conversas com informações detalhadas

        Raises:
            EvolutionAPIError: Se houver erro na requisição
        """
        self._log("Buscando conversas")
        chats = self._make_request("POST", "/chat/findChats/{instanceId}", data={})

        # Enriquece com nomes de contatos se solicitado
        if enrich_with_names and isinstance(chats, list):
            self._log("Enriquecendo conversas com nomes de contatos")

            # OTIMIZAÇÃO: Busca TODOS os contatos de uma vez ao invés de um por um
            contacts_map = self._build_contacts_map()

            for chat in chats:
                if chat.get("pushName") is None and chat.get("remoteJid"):
                    # Extrai o número do remoteJid
                    remote_jid = chat["remoteJid"]
                    # Ignora grupos (terminam com @g.us)
                    if not remote_jid.endswith(GROUP_JID_SUFFIX):
                        clean_number = (
                            self._personal_jid_number(remote_jid)
                            or self._chat_alt_number(chat)
                        )
                        # Lookup local (muito mais rápido que HTTP)
                        if clean_number and clean_number in contacts_map:
                            chat["pushName"] = contacts_map[clean_number]
                            chat["_enriched"] = True

        return chats

    def _build_contacts_map(self) -> dict[str, str]:
        """Constrói um mapa de número -> nome a partir de todos os contatos.

        Usa cache com TTL de 5 minutos. Se o cache expirou, reconstrói o mapa.

        Returns:
            dict: Mapeamento de número limpo para nome do contato
        """
        # Se cache não expirou, retorna cache existente
        if not self._is_cache_expired() and self._contact_names_cache:
            self._log("Usando cache de contatos existente")
            return self._contact_names_cache

        try:
            # Cache expirou ou está vazio - reconstrói
            self._log("Reconstruindo cache de contatos...")

            # Busca todos os contatos de uma vez (retorna lista direta)
            contact_list = self.fetch_contacts()
            contacts_map = {}

            for contact in contact_list:
                # Extrai número do remoteJid (formato: 5511999999999@s.whatsapp.net)
                remote_jid = contact.get("remoteJid", "")
                # Ignora grupos (terminam com @g.us)
                if remote_jid.endswith(GROUP_JID_SUFFIX):
                    continue

                clean_number = self._personal_jid_number(remote_jid)

                # Pega o pushName
                name = contact.get("pushName")
                if clean_number and name:
                    contacts_map[clean_number] = name

            # Atualiza cache e timestamp
            self._contact_names_cache = contacts_map
            self._cache_timestamp = datetime.now()

            self._log(f"Cache de contatos atualizado: {len(contacts_map)} contatos")
            return contacts_map

        except Exception as e:
            self._log(f"Erro ao construir mapa de contatos: {e}", "WARNING")
            return {}

    def find_messages(
        self,
        query: str | None = None,
        chat_id: str | None = None,
        limit: int = 50,
        page: int = 1
    ) -> dict[str, Any]:
        """Busca mensagens de uma conversa.

        Endpoint: POST /chat/findMessages/{instanceId}

        O filtro de conversa precisa ir aninhado em `where.key.remoteJid`; uma
        chave solta no topo do corpo é descartada pela API, que aí devolve
        todas as mensagens de todas as conversas. O tamanho de página vai
        como `offset`, não como `limit`.

        Args:
            query: Filtro de texto, case-insensitive. Aplicado no cliente e
                apenas sobre os registros da página buscada, porque a API
                descarta `where.message`. Use um limit alto pra varrer mais.
            chat_id: Número ou JID da conversa. Resolvido por resolve_chat_jid,
                então conversas `@lid` e `@g.us` também funcionam.
            limit: Tamanho da página (vai pra API como `offset`)
            page: Número da página, começando em 1

        Returns:
            dict: Lista de mensagens. Quando query é usado, `messages` também
                traz um relatório `clientSideFilter` do que foi varrido.

        Raises:
            EvolutionAPIError: Se houver erro na requisição
        """
        self._log(f"Buscando mensagens (limit={limit}, page={page})")

        payload: dict[str, Any] = {}
        if chat_id:
            payload["where"] = {"key": {"remoteJid": self.resolve_chat_jid(chat_id)}}
        if limit:
            payload["offset"] = limit
        if page and page > 1:
            payload["page"] = page

        result = self._make_request(
            "POST",
            "/chat/findMessages/{instanceId}",
            data=payload
        )

        if query:
            return self._apply_text_filter(result, query)

        return result

    def _apply_text_filter(self, result: Any, query: str) -> Any:
        """Filtra uma resposta de findMessages por texto, no cliente.

        A Evolution API descarta `where.message` em silêncio, então busca de
        texto não pode ser empurrada pro servidor: o filtro só vê os registros
        da página atual. O relatório `clientSideFilter` deixa esse escopo
        explícito, em vez de deixar um resultado vazio parecer que nada foi
        dito.

        Args:
            result: Resposta bruta do findMessages
            query: Trecho de texto a procurar, case-insensitive

        Returns:
            A mesma resposta, com `records` reduzido aos que casaram.
        """
        block = result.get("messages") if isinstance(result, dict) else None
        if not isinstance(block, dict) or not isinstance(block.get("records"), list):
            return result

        records = block["records"]
        needle = query.casefold()
        matched = [
            record for record in records
            if needle in self._message_text(record).casefold()
        ]

        block["records"] = matched
        block["clientSideFilter"] = {
            "query": query,
            "scope": "current_page",
            "scanned": len(records),
            "matched": len(matched),
        }

        return result

    @staticmethod
    def _message_text(record: dict[str, Any]) -> str:
        """Extrai o texto legível de um registro de mensagem.

        Args:
            record: Um item de `messages.records`

        Returns:
            str: O texto ou a legenda, vazio quando a mensagem não tem nenhum
                dos dois.
        """
        message = record.get("message") or {}

        return (
            message.get("conversation")
            or (message.get("extendedTextMessage") or {}).get("text")
            or (message.get("imageMessage") or {}).get("caption")
            or (message.get("videoMessage") or {}).get("caption")
            or (message.get("documentMessage") or {}).get("caption")
            or ""
        )

    def resolve_chat_jid(self, identifier: str) -> str:
        """Resolve um número ou JID pro JID em que a conversa está de fato salva.

        O WhatsApp endereça muita conversa como `<opaco>@lid` em vez de
        `<numero>@s.whatsapp.net`, então o JID não pode ser montado a partir do
        número: o telefone só aparece em `lastMessage.key.remoteJidAlt`.
        Qualquer coisa que já contenha '@' é repassada intacta, e é isso que
        faz grupo e JID explícito funcionarem.

        Só resolução bem-sucedida entra no cache, e cada entrada expira com o
        mesmo TTL do cache de contatos: o WhatsApp está migrando conversa de
        `@s.whatsapp.net` pra `@lid`, então um JID cacheado pra sempre voltaria
        a devolver conversa vazia depois da migração. O fallback nunca é
        cacheado, pra que uma conversa que apareça depois ainda seja
        encontrada.

        Args:
            identifier: Número no formato internacional, ou um JID completo

        Returns:
            str: O JID resolvido, caindo pra `<numero>@s.whatsapp.net` quando a
                lista de conversas não tem nenhuma correspondência.

        Raises:
            InvalidPhoneNumberError: Se o identificador não for JID nem número válido
        """
        if "@" in identifier:
            return identifier

        clean_number = self.validate_phone_number(identifier)
        cached = self._jid_cache.get(clean_number)
        if cached and datetime.now() - cached[1] <= self._cache_ttl:
            return cached[0]

        fallback = f"{clean_number}{PERSONAL_JID_SUFFIX}"

        try:
            chats = self.find_chats(enrich_with_names=False)
        except EvolutionAPIError:
            self._log(
                f"Falha ao listar conversas pra resolver {clean_number}; usando {fallback}",
                "WARNING"
            )
            return fallback

        for chat in chats if isinstance(chats, list) else []:
            remote_jid = chat.get("remoteJid") or ""
            if not remote_jid:
                continue
            if remote_jid == fallback or self._chat_alt_number(chat) == clean_number:
                self._jid_cache[clean_number] = (remote_jid, datetime.now())
                return remote_jid

        self._log(
            f"Nenhuma conversa encontrada para {clean_number}; usando {fallback}",
            "WARNING"
        )

        return fallback

    def resolve_send_target(self, number: str) -> str:
        """Normaliza um destino de envio sem inventar um JID.

        Número puro é validado e normalizado. JID é repassado intacto: remover
        os não-dígitos de `260992344797194@lid` daria uma string de 15 dígitos
        que passa na validação de telefone e endereça outro destinatário,
        possivelmente real.

        Args:
            number: Número no formato internacional, ou um JID completo

        Returns:
            str: O destino a entregar pra API

        Raises:
            InvalidPhoneNumberError: Se o número for inválido
        """
        if "@" in number:
            return number

        return self.validate_phone_number(number)

    @staticmethod
    def _personal_jid_number(remote_jid: str) -> str:
        """Extrai o número de telefone de um JID de contato.

        Args:
            remote_jid: Um JID como `5511999999999@s.whatsapp.net`

        Returns:
            str: Os dígitos, ou vazio para JID de grupo e `@lid`, cuja parte
                local é um id opaco e não um número de telefone.
        """
        if not remote_jid.endswith(PERSONAL_JID_SUFFIX):
            return ""

        return re.sub(r'\D', '', remote_jid[:-len(PERSONAL_JID_SUFFIX)])

    @staticmethod
    def _chat_alt_number(chat: dict[str, Any]) -> str:
        """Extrai o número de telefone pro qual uma conversa `@lid` aponta.

        Args:
            chat: Um item da resposta do findChats

        Returns:
            str: Os dígitos de `lastMessage.key.remoteJidAlt`, ou vazio quando
                a API não expõe esse campo.
        """
        key = (chat.get("lastMessage") or {}).get("key") or {}
        alt = key.get("remoteJidAlt") or ""

        return alt.split("@")[0]

    def get_messages_by_number(
        self,
        number: str,
        limit: int = 50,
        page: int = 1
    ) -> dict[str, Any]:
        """Obtém mensagens de uma conversa por número.

        Args:
            number: Número no formato internacional, ou um JID completo
                (grupos e contatos `@lid` inclusos)
            limit: Número máximo de mensagens
            page: Número da página, começando em 1

        Returns:
            dict: Mensagens da conversa

        Raises:
            InvalidPhoneNumberError: Se o número for inválido
            EvolutionAPIError: Se houver erro
        """
        return self.find_messages(chat_id=number, limit=limit, page=page)

    def fetch_contacts(self, contact_id: str | None = None) -> list[dict[str, Any]]:
        """Busca contatos salvos no WhatsApp com filtros opcionais.

        Endpoint: POST /chat/findContacts/{instanceId}

        Args:
            contact_id: ID do contato específico (ex: 5511999999999@s.whatsapp.net).
                       Se None, retorna todos os contatos.

        Returns:
            list: Lista de contatos com informações completas:
                  - remoteJid: ID do contato
                  - pushName: Nome do contato
                  - isGroup: Se é grupo ou contato individual
                  - profilePicUrl: URL da foto de perfil

        Raises:
            EvolutionAPIError: Se houver erro na requisição

        Example:
            # Buscar todos os contatos
            all_contacts = client.fetch_contacts()

            # Buscar contato específico
            contact = client.fetch_contacts(contact_id="5511999999999@s.whatsapp.net")
        """
        self._log(f"Buscando contatos{' (filtrado)' if contact_id else ''}")

        payload = {}
        if contact_id:
            payload["where"] = {"id": contact_id}

        result = self._make_request(
            "POST",
            "/chat/findContacts/{instanceId}",
            data=payload
        )

        # A API retorna uma lista diretamente, não um objeto com "data"
        if not isinstance(result, list):
            self._log(f"Formato inesperado de resposta: {type(result)}", "WARNING")
            return []

        return result

    def get_contact_name(self, number: str, use_cache: bool = True) -> str | None:
        """Busca o nome de um contato por número.

        Args:
            number: Número de telefone
            use_cache: Se deve usar cache de nomes (padrão: True)

        Returns:
            str | None: Nome do contato ou None se não encontrado

        Raises:
            EvolutionAPIError: Se houver erro
        """
        try:
            if "@" in number:
                cache_key = number
                contact_id = number
            else:
                cache_key = self.validate_phone_number(number)
                contact_id = f"{cache_key}{PERSONAL_JID_SUFFIX}"

            # Verifica cache primeiro (se não expirou)
            if use_cache and not self._is_cache_expired() and cache_key in self._contact_names_cache:
                return self._contact_names_cache[cache_key]

            # Tenta buscar contato específico com filtro (retorna lista direta)
            contact_list = self.fetch_contacts(contact_id=contact_id)

            name = None
            if contact_list and len(contact_list) > 0:
                contact = contact_list[0]
                # Retorna pushName
                name = contact.get("pushName")

            # Salva no cache e atualiza timestamp
            if use_cache:
                self._contact_names_cache[cache_key] = name
                if not self._cache_timestamp:
                    self._cache_timestamp = datetime.now()

            return name

        except Exception as e:
            self._log(f"Erro ao buscar nome do contato: {e}", "WARNING")
            return None

    # =========================================================================
    # MESSAGE SENDING
    # =========================================================================

    def send_text(
        self,
        number: str,
        text: str,
        link_preview: bool = True
    ) -> dict[str, Any]:
        """Envia uma mensagem de texto.

        Endpoint: POST /message/sendText/{instanceId}

        Args:
            number: Número de telefone no formato internacional
            text: Texto da mensagem (máximo 65536 caracteres)
            link_preview: Se deve mostrar preview de links

        Returns:
            dict: Resposta da API

        Raises:
            InvalidPhoneNumberError: Se o número for inválido
            ValueError: Se o texto exceder o tamanho máximo
            EvolutionAPIError: Erros da API
        """
        # Validações
        target = self.resolve_send_target(number)
        self.validate_text_length(text, MAX_TEXT_LENGTH, "text")

        self._log(f"Enviando mensagem de texto para {target}")

        payload = {
            "number": target,
            "text": text,
            "linkPreview": link_preview
        }

        return self._make_request(
            "POST",
            "/message/sendText/{instanceId}",
            data=payload
        )

    def send_media(
        self,
        number: str,
        media_url: str,
        media_type: str,
        caption: str | None = None,
        filename: str | None = None
    ) -> dict[str, Any]:
        """Envia mídia (imagem, vídeo, documento, áudio).

        Endpoint: POST /message/sendMedia/{instanceId}

        Args:
            number: Número de telefone no formato internacional
            media_url: URL da mídia a enviar
            media_type: Tipo de mídia (image, video, document, audio)
            caption: Legenda da mídia (opcional)
            filename: Nome do arquivo para documentos (opcional)

        Returns:
            dict: Resposta da API

        Raises:
            InvalidPhoneNumberError: Se o número for inválido
            ValueError: Se media_type, URL ou caption forem inválidos
            EvolutionAPIError: Erros da API
        """
        # Validações
        target = self.resolve_send_target(number)
        self.validate_media_type(media_type)
        self.validate_url(media_url, "media_url")
        if caption:
            self.validate_text_length(caption, MAX_CAPTION_LENGTH, "caption")

        self._log(f"Enviando {media_type} para {target}")

        payload = {
            "number": target,
            "mediatype": media_type,
            "media": media_url
        }

        if caption:
            payload["caption"] = caption
        if filename:
            payload["fileName"] = filename

        return self._make_request(
            "POST",
            "/message/sendMedia/{instanceId}",
            data=payload
        )

    # =========================================================================
    # INSTANCE OPERATIONS
    # =========================================================================

    def get_connection_state(self) -> dict[str, Any]:
        """Obtém o estado da conexão da instância.

        Endpoint: GET /instance/connectionState/{instanceId}

        Returns:
            dict: Estado da conexão

        Raises:
            EvolutionAPIError: Se houver erro ao consultar o estado
        """
        self._log("Consultando estado da conexão")

        response = self._make_request(
            "GET",
            "/instance/connectionState/{instanceId}"
        )

        state = response.get('state', 'unknown')
        self._log(f"Estado da conexão: {state}")

        return response

    def set_presence(
        self,
        status: str,
        number: str | None = None
    ) -> dict[str, Any]:
        """Define presença.

        Endpoint: POST /chat/presenceUpdate/{instanceId}

        Args:
            status: Status (available, unavailable, composing, recording)
            number: Número para enviar presença (opcional)

        Returns:
            dict: Resposta

        Raises:
            EvolutionAPIError: Se houver erro
        """
        self._log(f"Definindo presença como '{status}'")

        payload = {
            "presence": status
        }

        if number:
            payload["number"] = self.resolve_send_target(number)

        return self._make_request(
            "POST",
            "/chat/presenceUpdate/{instanceId}",
            data=payload
        )

    def get_instance_info(self) -> dict[str, Any]:
        """Obtém informações detalhadas da instância.

        Returns:
            dict: Informações da instância

        Raises:
            EvolutionAPIError: Se houver erro ao consultar
        """
        self._log("Consultando informações da instância")

        # Usa get_connection_state que retorna info da instância
        response = self.get_connection_state()

        return {
            "instance_name": self.instance_id,
            "status": response.get("state", "unknown"),
            "info": response
        }
