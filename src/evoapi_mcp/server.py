"""MCP Server para Evolution API."""

import sys
from pathlib import Path

# Adiciona o diretório src ao path para permitir importações
src_dir = Path(__file__).parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from mcp.server.fastmcp import FastMCP
from evoapi_mcp.config import load_config
from evoapi_mcp.client import EvolutionClient
from evoapi_mcp.chat_read import annotate_chats_with_markers, mark_chat_read
from evoapi_mcp.media import download_media as download_media_to_disk
from evoapi_mcp.read_markers import ReadMarkerStore
from evoapi_mcp.transcription import transcribe_chat_audios as transcribe_chat_audios_in_page
from evoapi_mcp.transcription import transcribe_message

# Inicializa o MCP server
mcp = FastMCP("Evolution API")

# Carrega configuração e inicializa cliente
try:
    config = load_config()
    client = EvolutionClient(config)
    read_markers = ReadMarkerStore(config.state_dir, config.instance_name)
except Exception as e:
    print(f"Falha ao inicializar o servidor: {e}", file=sys.stderr)
    sys.exit(1)


# ============================================================================
# TOOLS - Envio de Mensagens
# ============================================================================

@mcp.tool()
def send_text_message(
    number: str,
    text: str,
    link_preview: bool = True
) -> dict:
    """Envia uma mensagem de texto para um número WhatsApp.

    Args:
        number: Número no formato internacional sem '+' (ex: 5511999999999)
               OU um JID completo, para grupos (ex: 1203630000@g.us) e contatos
               com o endereçamento novo (ex: 100000000000000@lid)
        text: Texto da mensagem a ser enviada
        link_preview: Se deve mostrar preview de links (padrão: True)

    Returns:
        dict: Resposta da API com informações sobre a mensagem enviada

    Example:
        send_text_message(
            number="5511999999999",
            text="Olá! Esta é uma mensagem de teste."
        )
    """
    return client.send_text(
        number=number,
        text=text,
        link_preview=link_preview
    )


@mcp.tool()
def send_image(
    number: str,
    image_url: str,
    caption: str | None = None
) -> dict:
    """Envia uma imagem para um número WhatsApp.

    Args:
        number: Número no formato internacional sem '+' (ex: 5511999999999)
        image_url: URL pública da imagem (jpg, png, etc.)
        caption: Legenda da imagem (opcional)

    Returns:
        dict: Resposta da API

    Example:
        send_image(
            number="5511999999999",
            image_url="https://example.com/image.jpg",
            caption="Confira esta imagem!"
        )
    """
    return client.send_media(
        number=number,
        media_url=image_url,
        media_type="image",
        caption=caption
    )


@mcp.tool()
def send_document(
    number: str,
    document_url: str,
    filename: str | None = None,
    caption: str | None = None
) -> dict:
    """Envia um documento para um número WhatsApp.

    Args:
        number: Número no formato internacional sem '+' (ex: 5511999999999)
        document_url: URL pública do documento (pdf, docx, xlsx, etc.)
        filename: Nome do arquivo a ser exibido (opcional)
        caption: Legenda do documento (opcional)

    Returns:
        dict: Resposta da API

    Example:
        send_document(
            number="5511999999999",
            document_url="https://example.com/relatorio.pdf",
            filename="Relatório Mensal.pdf",
            caption="Segue o relatório solicitado"
        )
    """
    return client.send_media(
        number=number,
        media_url=document_url,
        media_type="document",
        caption=caption,
        filename=filename
    )


@mcp.tool()
def send_video(
    number: str,
    video_url: str,
    caption: str | None = None
) -> dict:
    """Envia um vídeo para um número WhatsApp.

    Args:
        number: Número no formato internacional sem '+' (ex: 5511999999999)
        video_url: URL pública do vídeo (mp4, etc.)
        caption: Legenda do vídeo (opcional)

    Returns:
        dict: Resposta da API

    Example:
        send_video(
            number="5511999999999",
            video_url="https://example.com/video.mp4",
            caption="Veja este vídeo"
        )
    """
    return client.send_media(
        number=number,
        media_url=video_url,
        media_type="video",
        caption=caption
    )


@mcp.tool()
def send_audio(
    number: str,
    audio_url: str
) -> dict:
    """Envia um áudio para um número WhatsApp.

    Args:
        number: Número no formato internacional sem '+' (ex: 5511999999999)
        audio_url: URL pública do áudio (mp3, ogg, etc.)

    Returns:
        dict: Resposta da API

    Example:
        send_audio(
            number="5511999999999",
            audio_url="https://example.com/audio.mp3"
        )
    """
    return client.send_media(
        number=number,
        media_url=audio_url,
        media_type="audio"
    )


# ============================================================================
# TOOLS - Gerenciamento de Chats e Mensagens
# ============================================================================

@mcp.tool()
def get_chat_messages(
    number: str,
    limit: int = 50,
    page: int = 1
) -> dict:
    """Obtém mensagens de uma conversa específica por número de telefone.

    Use esta ferramenta quando o usuário pedir:
    - "mostre as mensagens do número X"
    - "últimas 20 mensagens de fulano"
    - "conversa com 5511999999999"

    Args:
        number: Número no formato internacional sem '+' (ex: 5511999999999)
               OU um JID completo, para grupos (ex: 1203630000@g.us) e contatos
               com o endereçamento novo (ex: 100000000000000@lid). Um número é
               resolvido contra a lista de chats, então funciona nos dois casos.
        limit: Número máximo de mensagens a retornar. SEMPRE ajuste este valor
               quando o usuário especificar quantidade (ex: "últimas 20", "50 mensagens")
               Padrão: 50 mensagens
        page: Página, começando em 1. Use com limit para paginar conversas longas;
              a resposta traz `messages.pages` com o total de páginas.

    Returns:
        dict: Lista de mensagens da conversa. Se o número não bater com nenhuma
            conversa da instância, `messages.chatResolution.resolved` vem
            `false` — a leitura foi num JID adivinhado, e lista vazia significa
            "conversa não encontrada", não "conversa sem mensagens".

    Example:
        # Últimas 50 mensagens (padrão)
        messages = get_chat_messages(number="5511999999999")

        # Últimas 20 mensagens
        messages = get_chat_messages(number="5511999999999", limit=20)

        # Um grupo, por JID
        messages = get_chat_messages(number="120363000000000000@g.us", limit=20)

        # Segunda página de 20
        messages = get_chat_messages(number="5511999999999", limit=20, page=2)
    """
    return client.get_messages_by_number(number=number, limit=limit, page=page)


@mcp.tool()
def list_chats(limit: int | None = None) -> list:
    """Lista conversas ativas do WhatsApp ordenadas por data de atualização.

    Use esta ferramenta quando o usuário pedir:
    - "liste minhas conversas"
    - "mostre minhas conversas mais recentes"
    - "quais são meus últimos chats"

    Args:
        limit: Número máximo de conversas a retornar. SEMPRE use este parâmetro
               quando o usuário especificar uma quantidade (ex: "5 conversas", "10 chats")

    Returns:
        list: Lista de conversas, cada uma com:
              - remoteJid: ID do chat
              - pushName: Nome do contato (ou null)
              - lastMessage: Última mensagem trocada
              - unreadCount: Número de mensagens não lidas
              - unreadSource: "evolution" (contador bruto da Evolution, que nunca decrementa)
                ou "local_marker" (calculado a partir do marcador gravado por mark_as_read)
              - readMarker / unreadCountIsLowerBound: presentes só quando há marcador

    Example:
        # Listar todas as conversas
        chats = list_chats()

        # Listar apenas as 10 mais recentes (IMPORTANTE: sempre passar limit quando especificado)
        chats = list_chats(limit=10)
    """
    chats = client.find_chats()

    # Aplica limit se fornecido
    if limit is not None and isinstance(chats, list):
        chats = chats[:limit]

    if isinstance(chats, list):
        chats = annotate_chats_with_markers(client, read_markers, chats)

    return chats


@mcp.tool()
def find_messages(
    query: str | None = None,
    chat_id: str | None = None,
    limit: int = 50,
    page: int = 1,
    max_pages: int = 1
) -> dict:
    """Busca mensagens com filtros avançados em todas as conversas.

    Use esta ferramenta quando o usuário pedir:
    - "busque mensagens com a palavra X"
    - "encontre mensagens sobre pedido"
    - "mensagens que contenham reunião"

    ATENÇÃO ao usar `query`: a Evolution API não suporta busca por texto no
    servidor, então o filtro é aplicado no cliente, APENAS sobre a página que
    foi buscada. Um `query` sem `chat_id` varre só as `limit` mensagens mais
    recentes da instância inteira e NÃO prova que o termo nunca foi dito.
    Para buscar dentro de uma conversa, passe `chat_id` junto com um `limit`
    alto e use `max_pages` pra varrer várias páginas de uma vez. A resposta traz
    `messages.clientSideFilter` com quantas mensagens e páginas foram varridas
    de fato.

    Quando `chat_id` é um número que não bate com nenhuma conversa da instância,
    a resposta traz `messages.chatResolution.resolved = false`: a leitura foi
    feita num JID adivinhado, então lista vazia ali significa "conversa não
    encontrada", não "conversa sem mensagens".

    Args:
        query: Termo de busca nas mensagens. Filtro client-side, case-insensitive,
               limitado à página buscada (veja o aviso acima)
        chat_id: Número OU JID do chat (ex: 5511999999999, 5511999999999@s.whatsapp.net,
                 100000000000000@lid, 120363000000000000@g.us). É o único jeito de ler
                 um grupo. Um número é resolvido contra a lista de chats.
        limit: Número máximo de mensagens a retornar. SEMPRE ajuste quando
               o usuário especificar quantidade
               Padrão: 50 mensagens
        page: Página, começando em 1. Use com limit para paginar.
        max_pages: Com `query`, quantas páginas varrer a partir de `page`
                   (padrão 1). Use um valor maior antes de concluir que um
                   termo não aparece na conversa.

    Returns:
        dict: Lista de mensagens encontradas

    Example:
        # Ler uma conversa inteira, paginando
        messages = find_messages(chat_id="5511999999999", limit=100, page=1)

        # Ler um grupo
        messages = find_messages(chat_id="120363000000000000@g.us", limit=50)

        # Buscar "reunião" nas últimas 500 mensagens de uma conversa
        messages = find_messages(query="reunião", chat_id="5511999999999", limit=500)

        # Varrer 2000 mensagens (4 páginas de 500) antes de dizer que não achou
        messages = find_messages(
            query="reunião", chat_id="5511999999999", limit=500, max_pages=4
        )
    """
    return client.find_messages(
        query=query, chat_id=chat_id, limit=limit, page=page, max_pages=max_pages
    )


@mcp.tool()
def get_contacts(
    contact_id: str | None = None,
    limit: int | None = None
) -> list:
    """Busca contatos salvos no WhatsApp com filtros opcionais.

    Use esta ferramenta quando o usuário pedir:
    - "liste meus contatos"
    - "mostre 10 contatos"
    - "quais são meus contatos salvos"
    - "busque o contato 5511999999999"
    - "mostre informações do contato X"

    Args:
        contact_id: ID específico do contato (ex: 5511999999999@s.whatsapp.net).
                   Use quando buscar um contato específico.
                   Se None, retorna todos os contatos.

        limit: Número máximo de contatos a retornar. SEMPRE use este parâmetro
               quando o usuário especificar uma quantidade (ex: "10 contatos", "5 primeiros")
               Se não especificado, retorna TODOS os contatos (pode ser muitos!)

    Returns:
        list: Lista de contatos onde cada contato tem:
              - remoteJid: ID do contato (ex: 5511999999999@s.whatsapp.net)
              - pushName: Nome do contato
              - isGroup: Se é grupo ou contato individual
              - profilePicUrl: URL da foto de perfil

    Example:
        # Buscar todos os contatos (pode retornar centenas!)
        contacts = get_contacts()

        # Buscar apenas os primeiros 10 contatos (RECOMENDADO quando há quantidade)
        contacts = get_contacts(limit=10)

        # Buscar contato específico
        contact = get_contacts(contact_id="5511999999999@s.whatsapp.net")

        # Buscar contato específico (apenas 1 resultado)
        contact = get_contacts(contact_id="5511999999999@s.whatsapp.net", limit=1)
    """
    contacts = client.fetch_contacts(contact_id=contact_id)

    # Aplica limit se fornecido
    if limit is not None and isinstance(contacts, list):
        contacts = contacts[:limit]

    return contacts


@mcp.tool()
def get_contact_name_by_number(number: str) -> dict:
    """Obtém o nome de um contato pelo número de telefone.

    Args:
        number: Número no formato internacional sem '+' (ex: 5511999999999)

    Returns:
        dict: {"number": "5511999999999", "name": "Nome do Contato" ou None}

    Example:
        info = get_contact_name_by_number("5511999999999")
        if info['name']:
            print(f"Contato: {info['name']}")
        else:
            print(f"Número não salvo: {info['number']}")
    """
    name = client.get_contact_name(number)
    return {
        "number": number,
        "name": name
    }


# ============================================================================
# TOOLS - Status e Presença
# ============================================================================

@mcp.tool()
def get_connection_status() -> dict:
    """Verifica o status da conexão da instância WhatsApp.

    Returns:
        dict: Estado da conexão contendo informações sobre a instância

    Example:
        status = get_connection_status()
        if status.get('state') == 'open':
            print("WhatsApp conectado!")
    """
    return client.get_connection_state()


@mcp.tool()
def set_presence(
    status: str,
    number: str | None = None
) -> dict:
    """Define o status de presença da instância WhatsApp.

    Args:
        status: Status de presença (available, unavailable, composing, recording)
        number: Número para enviar presença específica (opcional)

    Returns:
        dict: Confirmação da alteração de presença

    Example:
        set_presence("available")  # Fica online
        set_presence("unavailable")  # Fica offline
    """
    valid_statuses = ["available", "unavailable", "composing", "recording"]

    if status not in valid_statuses:
        raise ValueError(
            f"Status inválido: '{status}'. "
            f"Valores válidos: {', '.join(valid_statuses)}"
        )

    return client.set_presence(status=status, number=number)


@mcp.tool()
def get_instance_info() -> dict:
    """Obtém informações detalhadas da instância WhatsApp.

    Returns:
        dict: Informações completas da instância incluindo status e configuração

    Example:
        info = get_instance_info()
        print(f"Instância: {info['instance_name']}")
        print(f"Status: {info['status']}")
    """
    return client.get_instance_info()


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
- Quando não havia nada novo pra marcar, nenhum receipt é mandado e phoneCleared vem
  None (nem True nem False: não houve o que limpar), com reason = "nothing_new".

Args:
    chats: Número internacional sem '+' (ex: 5511999999999), JID completo
        (ex: 120363000000000000@g.us, 100000000000000@lid) ou lista misturando os dois.

Returns:
    Uma entrada por chat pedido, na mesma ordem: requested, jid, resolved, receiptsSent,
    phoneCleared, reason, markerTimestamp, messagesScanned. phoneCleared é True (receipt
    mandado), False (grupo) ou None (nada novo pra marcar). Falha em um chat vira "error"
    nessa entrada e não interrompe os demais.
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
do áudio (<message_id>.transcript.txt), então repetir a chamada não paga de novo.

Args:
    message_id: key.id de uma mensagem do tipo audioMessage.
    language: Código ISO-639-1 (ex: "pt") pra guiar o modelo. Opcional.

Returns:
    text, model, language, audioPath, transcriptPath, cached, messageId.
"""

TRANSCRIBE_CHAT_AUDIOS_DESCRIPTION = """Transcreve os áudios de uma página de mensagens de uma conversa.

Use quando o usuário pedir "o que dizem os áudios que fulano mandou" ou algo equivalente
sobre os áudios de uma conversa específica. Cada áudio é enviado pra OpenAI e cobrado; o
padrão é transcrever no máximo 10 áudios por chamada (max_audios) e pular os seus
próprios áudios (include_own=False), porque transcrever o que você mesmo mandou custa
dinheiro à toa. Busca `limit` mensagens da página `page` (mesma paginação de
find_messages), filtra os áudios e transcreve cada um até o limite. Falha em um áudio
vira "error" naquele item; os outros seguem. Exige OPENAI_API_KEY.

Args:
    chat: Número, ou JID completo (grupos e contatos @lid).
    limit: Tamanho da página de mensagens a varrer (padrão 50).
    page: Página, começando em 1.
    language: Código ISO-639-1 opcional.
    max_audios: Quantos áudios transcrever no máximo nesta chamada (padrão 10).
    include_own: Se True, também transcreve áudios enviados por você (padrão False).

Returns:
    chatResolution, scanned, pages, currentPage, audios: lista com messageId,
    timestamp, fromMe, pushName, seconds e text (ou error), skipped_own (áudios seus
    pulados) e skipped_over_cap (áudios além de max_audios, não transcritos).
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
    language: str | None = None,
    max_audios: int = 10,
    include_own: bool = False
) -> dict:
    return transcribe_chat_audios_in_page(
        client, config, chat, limit=limit, page=page, language=language,
        max_audios=max_audios, include_own=include_own,
    )


# ============================================================================
# Entry Point
# ============================================================================

def main() -> None:
    """Executa o servidor MCP no transporte stdio."""
    mcp.run()


if __name__ == "__main__":
    # Executa o servidor MCP
    main()
