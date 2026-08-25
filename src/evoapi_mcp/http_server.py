"""HTTP Server para expor MCP tools via REST API.

Este servidor permite acessar as ferramentas MCP via HTTP/REST em vez de stdio,
possibilitando uso em containers Docker e acesso remoto.
"""

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Any
import sys

from .client import EvolutionClient
from .config import load_config

# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="Evolution API MCP Server",
    description="MCP Server para Evolution API - Integração WhatsApp via HTTP",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS para permitir chamadas de frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especificar origins permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cliente Evolution API (global)
client: EvolutionClient | None = None


# =============================================================================
# MODELS (Pydantic)
# =============================================================================

class HealthResponse(BaseModel):
    status: str
    version: str
    instance: str


class SendTextRequest(BaseModel):
    number: str = Field(..., description="Número de telefone (formato internacional)")
    text: str = Field(..., description="Texto da mensagem")
    link_preview: bool = Field(True, description="Exibir preview de links")


class SendMediaRequest(BaseModel):
    number: str = Field(..., description="Número de telefone")
    media_url: str = Field(..., description="URL da mídia")
    media_type: str = Field(..., description="Tipo: image, video, document, audio")
    caption: str | None = Field(None, description="Legenda da mídia")
    filename: str | None = Field(None, description="Nome do arquivo")


class SetPresenceRequest(BaseModel):
    number: str = Field(..., description="Número de telefone")
    presence: str = Field(..., description="Presença: available, unavailable, composing, recording")


class MarkAsReadRequest(BaseModel):
    number: str = Field(..., description="Número de telefone")


class ArchiveChatRequest(BaseModel):
    number: str = Field(..., description="Número de telefone")
    archive: bool = Field(True, description="True para arquivar, False para desarquivar")


class DeleteChatRequest(BaseModel):
    number: str = Field(..., description="Número de telefone")


class CheckNumberRequest(BaseModel):
    number: str = Field(..., description="Número de telefone")


# =============================================================================
# LIFECYCLE EVENTS
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Inicializa o cliente Evolution API ao iniciar o servidor."""
    global client
    try:
        config = load_config()
        client = EvolutionClient(config)
        print(f"✅ MCP HTTP Server inicializado - Instância: {config.instance_name}", file=sys.stderr)
    except Exception as e:
        print(f"❌ Erro ao inicializar cliente: {e}", file=sys.stderr)
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup ao desligar o servidor."""
    print("🛑 MCP HTTP Server desligado", file=sys.stderr)


# =============================================================================
# ENDPOINTS - HEALTH & INFO
# =============================================================================

@app.get("/", response_model=dict)
async def root():
    """Endpoint raiz - informações básicas do servidor."""
    return {
        "name": "Evolution API MCP Server",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Healthcheck para Docker e monitoramento."""
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cliente não inicializado"
        )

    return HealthResponse(
        status="healthy",
        version="1.0.0",
        instance=client.instance_id
    )


# =============================================================================
# ENDPOINTS - CHAT OPERATIONS
# =============================================================================

@app.get("/chats", response_model=list[dict[str, Any]])
async def get_chats(limit: int = 50):
    """Lista conversas recentes com enriquecimento de nomes."""
    if not client:
        raise HTTPException(status_code=503, detail="Cliente não inicializado")

    try:
        chats = client.find_chats()
        if isinstance(chats, list):
            return chats[:limit]
        return chats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/contacts", response_model=list[dict[str, Any]])
async def get_contacts(contact_id: str | None = None, limit: int | None = None):
    """Busca contatos salvos no WhatsApp."""
    if not client:
        raise HTTPException(status_code=503, detail="Cliente não inicializado")

    try:
        contacts = client.fetch_contacts(contact_id=contact_id)
        if limit is not None:
            contacts = contacts[:limit]
        return contacts
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/messages/{number}", response_model=dict[str, Any])
async def get_messages(number: str, limit: int = 50, page: int = 1):
    """Busca mensagens de uma conversa, por número ou JID."""
    if not client:
        raise HTTPException(status_code=503, detail="Cliente não inicializado")

    try:
        return client.get_messages_by_number(number=number, limit=limit, page=page)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ENDPOINTS - MESSAGE SENDING
# =============================================================================

@app.post("/messages/text", response_model=dict[str, Any])
async def send_text(request: SendTextRequest):
    """Envia mensagem de texto."""
    if not client:
        raise HTTPException(status_code=503, detail="Cliente não inicializado")

    try:
        return client.send_text(
            number=request.number,
            text=request.text,
            link_preview=request.link_preview
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/messages/media", response_model=dict[str, Any])
async def send_media(request: SendMediaRequest):
    """Envia mídia (imagem, vídeo, documento, áudio)."""
    if not client:
        raise HTTPException(status_code=503, detail="Cliente não inicializado")

    try:
        return client.send_media(
            number=request.number,
            media_url=request.media_url,
            media_type=request.media_type,
            caption=request.caption,
            filename=request.filename
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ENDPOINTS - INSTANCE & PRESENCE
# =============================================================================

@app.get("/instance/status", response_model=dict[str, Any])
async def get_instance_status():
    """Busca status da instância."""
    if not client:
        raise HTTPException(status_code=503, detail="Cliente não inicializado")

    try:
        return client.get_instance_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/presence", response_model=dict[str, Any])
async def set_presence(request: SetPresenceRequest):
    """Define presença (online, offline, digitando, gravando)."""
    if not client:
        raise HTTPException(status_code=503, detail="Cliente não inicializado")

    try:
        return client.set_presence(
            number=request.number,
            presence=request.presence
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ENDPOINTS - CHAT MANAGEMENT
# =============================================================================

@app.post("/messages/mark-read", response_model=dict[str, Any])
async def mark_as_read(request: MarkAsReadRequest):
    """Marca mensagem como lida."""
    if not client:
        raise HTTPException(status_code=503, detail="Cliente não inicializado")

    try:
        return client.mark_message_as_read(number=request.number)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chats/archive", response_model=dict[str, Any])
async def archive_chat(request: ArchiveChatRequest):
    """Arquiva ou desarquiva uma conversa."""
    if not client:
        raise HTTPException(status_code=503, detail="Cliente não inicializado")

    try:
        return client.archive_chat(
            number=request.number,
            archive=request.archive
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/chats/{number}", response_model=dict[str, Any])
async def delete_chat(number: str):
    """Deleta uma conversa."""
    if not client:
        raise HTTPException(status_code=503, detail="Cliente não inicializado")

    try:
        return client.delete_chat(number=number)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ENDPOINTS - PROFILE & UTILITIES
# =============================================================================

@app.get("/profile/picture/{number}", response_model=dict[str, Any])
async def get_profile_picture(number: str):
    """Busca foto de perfil de um contato."""
    if not client:
        raise HTTPException(status_code=503, detail="Cliente não inicializado")

    try:
        return client.get_profile_picture(number=number)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/profile/status/{number}", response_model=dict[str, Any])
async def get_profile_status(number: str):
    """Busca status/bio de um contato."""
    if not client:
        raise HTTPException(status_code=503, detail="Cliente não inicializado")

    try:
        return client.get_profile_status(number=number)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/check-number", response_model=dict[str, Any])
async def check_number(request: CheckNumberRequest):
    """Verifica se um número está registrado no WhatsApp."""
    if not client:
        raise HTTPException(status_code=503, detail="Cliente não inicializado")

    try:
        return client.check_number_on_whatsapp(number=request.number)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/profile/business/{number}", response_model=dict[str, Any])
async def get_business_profile(number: str):
    """Busca perfil comercial de um contato."""
    if not client:
        raise HTTPException(status_code=503, detail="Cliente não inicializado")

    try:
        return client.get_business_profile(number=number)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# CACHE MANAGEMENT
# =============================================================================

@app.post("/cache/clear", response_model=dict[str, str])
async def clear_cache():
    """Limpa o cache de contatos manualmente."""
    if not client:
        raise HTTPException(status_code=503, detail="Cliente não inicializado")

    try:
        client.clear_cache()
        return {"status": "success", "message": "Cache limpo com sucesso"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# MAIN (para desenvolvimento local)
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "evoapi_mcp.http_server:app",
        host="0.0.0.0",
        port=3000,
        reload=True,
        log_level="info"
    )
