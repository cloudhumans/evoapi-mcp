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

# Inicializa o MCP server
mcp = FastMCP("Evolution API")

# Carrega configuração e inicializa cliente
try:
    config = load_config()
    client = EvolutionClient(config)
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
               com o endereçamento novo (ex: 260992344797194@lid)
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
               com o endereçamento novo (ex: 260992344797194@lid). Um número é
               resolvido contra a lista de chats, então funciona nos dois casos.
        limit: Número máximo de mensagens a retornar. SEMPRE ajuste este valor
               quando o usuário especificar quantidade (ex: "últimas 20", "50 mensagens")
               Padrão: 50 mensagens
        page: Página (1-based). Use com limit para paginar conversas longas;
              a resposta traz `messages.pages` com o total de páginas.

    Returns:
        dict: Lista de mensagens da conversa

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

    return chats


@mcp.tool()
def find_messages(
    query: str | None = None,
    chat_id: str | None = None,
    limit: int = 50,
    page: int = 1
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
    alto e pagine. A resposta traz `messages.clientSideFilter` com quantas
    mensagens foram varridas de fato.

    Args:
        query: Termo de busca nas mensagens. Filtro client-side, case-insensitive,
               limitado à página buscada (veja o aviso acima)
        chat_id: Número OU JID do chat (ex: 5511999999999, 5511999999999@s.whatsapp.net,
                 260992344797194@lid, 120363000000000000@g.us). É o único jeito de ler
                 um grupo. Um número é resolvido contra a lista de chats.
        limit: Número máximo de mensagens a retornar. SEMPRE ajuste quando
               o usuário especificar quantidade
               Padrão: 50 mensagens
        page: Página (1-based). Use com limit para paginar.

    Returns:
        dict: Lista de mensagens encontradas

    Example:
        # Ler uma conversa inteira, paginando
        messages = find_messages(chat_id="5511999999999", limit=100, page=1)

        # Ler um grupo
        messages = find_messages(chat_id="120363000000000000@g.us", limit=50)

        # Buscar "reunião" nas últimas 500 mensagens de uma conversa
        messages = find_messages(query="reunião", chat_id="5511999999999", limit=500)
    """
    return client.find_messages(query=query, chat_id=chat_id, limit=limit, page=page)


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


# ============================================================================
# Entry Point
# ============================================================================

def main() -> None:
    """Executa o servidor MCP no transporte stdio."""
    mcp.run()


if __name__ == "__main__":
    # Executa o servidor MCP
    main()
