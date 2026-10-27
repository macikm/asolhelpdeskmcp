"""
ASOL HelpDesk MCP Server
Poskytuje Model Context Protocol (MCP) server pro čtení dat z AVAplace HelpDesku.
Běží přes HTTP / SSE (Server-Sent Events) na zadaném portu (výchozí 8095).
"""

import os
import base64
from typing import Optional, Dict, Any
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, Mount
from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.sse import SseServerTransport
from helpdesk_api import HelpdeskClient

# Načtení .env pokud existuje
load_dotenv()

PORT = int(os.environ.get("PORT", "8095"))
HOST = os.environ.get("HOST", "0.0.0.0")
API_URL = os.environ.get("API_URL", "https://avaplace.com/api/asoleu/helpdesk")
AUTH_URL = os.environ.get("AUTH_URL", "https://avaplace.com/api/asol/idp/connect/token")
DEFAULT_USER = os.environ.get("HELPDESK_DEFAULT_USER", "")
DEFAULT_PASS = os.environ.get("HELPDESK_DEFAULT_PASSWORD", "")

client = HelpdeskClient(api_url=API_URL, auth_url=AUTH_URL)

# Úložiště přihlášených uživatelů: session_id nebo client_ip -> (username, password)
session_auth_store: Dict[str, tuple] = {}
# Globální fallback přihlášení v rámci běhu (pokud uživatel zavolá helpdesk_login)
active_login: Optional[tuple] = None

# Vytvoření FastMCP instance
mcp = FastMCP("ASOL AVAplace Helpdesk", dependencies=["requests"])


def _extract_credentials_from_request(request: Request) -> Optional[tuple]:
    """Získá přihlašovací údaje z HTTP hlaviček nebo query parametrů."""
    # 1. Vlastní hlavičky
    user = request.headers.get("x-helpdesk-user") or request.headers.get("x-user")
    pwd = request.headers.get("x-helpdesk-password") or request.headers.get("x-password")
    if user and pwd:
        return (user, pwd)

    # 2. HTTP Basic Auth
    auth = request.headers.get("authorization", "")
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode("utf-8")
            if ":" in decoded:
                u, p = decoded.split(":", 1)
                return (u, p)
        except Exception:
            pass

    # 3. Query parametry (?user=...&password=...)
    q_user = request.query_params.get("user") or request.query_params.get("username")
    q_pwd = request.query_params.get("password") or request.query_params.get("pass")
    if q_user and q_pwd:
        return (q_user, q_pwd)

    return None


def resolve_auth(ctx: Optional[Context] = None, username: Optional[str] = None, password: Optional[str] = None) -> Optional[str]:
    """Získá platný token pro aktuální kontext/uživatele."""
    # 1. Přímo předané credentials v parametru nástroje
    if username and password:
        token = client.get_token(username, password)
        if token:
            return token

    # 2. Session auth podle session_id z MCP kontextu
    if ctx and hasattr(ctx, "session_id") and ctx.session_id:
        if ctx.session_id in session_auth_store:
            u, p = session_auth_store[ctx.session_id]
            token = client.get_token(u, p)
            if token:
                return token

    # 3. Poslední aktivní login přes nástroj helpdesk_login
    global active_login
    if active_login:
        u, p = active_login
        token = client.get_token(u, p)
        if token:
            return token

    # 4. Fallback na výchozí uživatele z .env (pokud je nastaven)
    if DEFAULT_USER and DEFAULT_PASS:
        token = client.get_token(DEFAULT_USER, DEFAULT_PASS)
        if token:
            return token

    return None


# --- MCP NÁSTROJE (TOOLS) - POUZE PRO ČTENÍ ---

@mcp.tool()
def helpdesk_login(username: str, password: str, ctx: Context = None) -> str:
    """
    Přihlásí uživatele k Helpdesku pomocí jeho přihlašovacího jména a hesla do AVAplace.
    Použijte, pokud v nastavení klienta nebyly předány přihlašovací hlavičky.
    """
    token = client.get_token(username, password)
    if not token:
        return "❌ Přihlášení se nezdařilo. Zkontrolujte prosím uživatelské jméno a heslo."

    global active_login
    active_login = (username, password)

    if ctx and hasattr(ctx, "session_id") and ctx.session_id:
        session_auth_store[ctx.session_id] = (username, password)

    return f"✅ Úspěšně přihlášen uživatel '{username}'. MCP server má nyní přístup k Helpdesku."


@mcp.tool()
def search_tickets(
    state: Optional[str] = None,
    external_state: Optional[str] = None,
    priority: Optional[str] = None,
    search_text: Optional[str] = None,
    title: Optional[str] = None,
    customer: Optional[str] = None,
    issuer: Optional[str] = None,
    application_id: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    page_size: int = 50,
    page_index: int = 0,
    ctx: Context = None,
) -> Any:
    """
    Vyhledá tikety v AVAplace Helpdesku podle zadaných filtrů.
    Všechny filtry jsou volitelné.
    
    Parametry:
    - state: Interní stav (Draft, ToDo, Assigned, InProgress, Postponed, Question, Solved, Done)
    - external_state: Externí stav (Draft, InProgress, Question, Solved, Done)
    - priority: Priorita tiketu ('A' = Vysoká, 'B' = Střední, 'C' = Nízká)
    - search_text: Fulltextové vyhledávání v obsahu tiketu
    - title: Částečná shoda v názvu tiketu
    - customer: Název zákazníka/firmy
    - issuer: Jméno žadatele
    - created_from / created_to: Datumové filtry ve formátu YYYY-MM-DD
    - page_size: Počet položek na stránku (výchozí 50, max 500)
    """
    token = resolve_auth(ctx)
    if not token:
        return "⚠️ Nejste přihlášeni. Použijte nástroj 'helpdesk_login(username, password)' nebo nastavte hlavičky X-Helpdesk-User a X-Helpdesk-Password."

    try:
        return client.search_tickets(
            token=token,
            state=state,
            external_state=external_state,
            priority=priority,
            search_text=search_text,
            title=title,
            customer=customer,
            issuer=issuer,
            application_id=application_id,
            created_from=created_from,
            created_to=created_to,
            page_size=page_size,
            page_index=page_index,
        )
    except Exception as e:
        return f"Chyba při volání Helpdesk API: {e}"


@mcp.tool()
def get_ticket_detail(ticket_identifier: str, ctx: Context = None) -> Any:
    """
    Vrátí kompletní detail konkrétního tiketu.
    
    Parametry:
    - ticket_identifier: Unikátní identifikátor (GUID) nebo kód tiketu včetně aplikace, např. 'HD-12345'
    """
    token = resolve_auth(ctx)
    if not token:
        return "⚠️ Nejste přihlášeni. Použijte nástroj 'helpdesk_login(username, password)'."

    try:
        return client.get_ticket(token=token, ticket_identifier=ticket_identifier)
    except Exception as e:
        return f"Chyba při načítání detailu tiketu '{ticket_identifier}': {e}"


@mcp.tool()
def get_applications(ctx: Context = None) -> Any:
    """Vrátí seznam aplikací (oddělení/projektů) dostupných v Helpdesku."""
    token = resolve_auth(ctx)
    if not token:
        return "⚠️ Nejste přihlášeni. Použijte nástroj 'helpdesk_login(username, password)'."

    try:
        return client.get_applications(token=token)
    except Exception as e:
        return f"Chyba při načítání aplikací: {e}"


@mcp.tool()
def get_filter_options() -> Dict[str, Any]:
    """Vrátí přehled platných hodnot pro filtrování tiketů (stavy, priority, typy)."""
    return {
        "states": [
            {"code": "Draft", "name": "Koncept / Návrh"},
            {"code": "ToDo", "name": "K vyřízení"},
            {"code": "Assigned", "name": "Přiřazeno"},
            {"code": "InProgress", "name": "Rozpracováno"},
            {"code": "Postponed", "name": "Odloženo"},
            {"code": "Question", "name": "Dotaz"},
            {"code": "Solved", "name": "Vyřešeno"},
            {"code": "Done", "name": "Hotovo"},
        ],
        "priorities": [
            {"code": "A", "name": "Vysoká (High)"},
            {"code": "B", "name": "Střední (Medium)"},
            {"code": "C", "name": "Nízká (Low)"},
        ],
        "types": [
            {"code": "TicketTypeInquiry", "name": "Požadavek / Dotaz"},
            {"code": "TicketTypeTopic", "name": "Téma"},
            {"code": "TicketTypeIncident", "name": "Incident"},
        ]
    }


# --- STARLETTE / SSE APLIKACE ---

sse = SseServerTransport("/messages/")
mcp_server = mcp._mcp_server


async def handle_sse(request: Request) -> Response:
    """Endpoint pro navázání SSE spojení s klientem."""
    creds = _extract_credentials_from_request(request)
    client_ip = request.client.host if request.client else "unknown"

    if creds:
        session_auth_store[client_ip] = creds
        print(f"🔐 Klient {client_ip} připojen s údaji pro '{creds[0]}'")

    async with sse.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp_server.run(
            streams[0],
            streams[1],
            mcp_server.create_initialization_options(),
        )

    return Response()


async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint pro Docker a monitoring."""
    return JSONResponse({
        "status": "healthy",
        "service": "asolhelpdeskmcp",
        "port": PORT,
        "api_url": API_URL,
    })


routes = [
    Route("/health", endpoint=health_check, methods=["GET"]),
    Route("/sse", endpoint=handle_sse, methods=["GET"]),
    Mount("/messages/", app=sse.handle_post_message),
]

app = Starlette(routes=routes)

if __name__ == "__main__":
    print(f"🚀 Spouštím ASOL HelpDesk MCP server na http://{HOST}:{PORT}")
    print(f"   Health check: http://{HOST}:{PORT}/health")
    print(f"   SSE endpoint: http://{HOST}:{PORT}/sse")
    uvicorn.run(app, host=HOST, port=PORT)
