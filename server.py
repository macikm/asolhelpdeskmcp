"""
ASOL HelpDesk MCP Server
Poskytuje Model Context Protocol (MCP) server pro čtení dat z AVAplace HelpDesku.
Běží přes HTTP / SSE (Server-Sent Events) na zadaném portu (výchozí 8095).
"""

import os
import base64
import contextvars
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

# ContextVar pro přihlášení aktuálního SSE spojení
current_client_auth: contextvars.ContextVar[Optional[tuple]] = contextvars.ContextVar("current_client_auth", default=None)

# Úložiště přihlášených uživatelů: session_id, client_id nebo client_ip -> (username, password)
session_auth_store: Dict[str, tuple] = {}
# Globální fallback přihlášení v rámci běhu (pokud uživatel zavolá helpdesk_login nebo pošle hlavičky)
active_login: Optional[tuple] = None

# Vytvoření FastMCP instance
mcp = FastMCP("ASOL AVAplace Helpdesk", dependencies=["requests"])


def _extract_credentials_from_request(request: Request) -> Optional[tuple]:
    """Získá přihlašovací údaje z HTTP hlaviček nebo query parametrů."""
    # 1. Vlastní hlavičky (X-Helpdesk-User / Password, X-User / Password)
    user = request.headers.get("x-helpdesk-user") or request.headers.get("x-user")
    pwd = request.headers.get("x-helpdesk-password") or request.headers.get("x-password")
    if user and pwd:
        return (user.strip(), pwd.strip())

    # 2. HTTP Basic Auth
    auth = request.headers.get("authorization", "")
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode("utf-8")
            if ":" in decoded:
                u, p = decoded.split(":", 1)
                return (u.strip(), p.strip())
        except Exception:
            pass

    # 3. Query parametry (?user=...&password=...)
    q_user = request.query_params.get("user") or request.query_params.get("username")
    q_pwd = request.query_params.get("password") or request.query_params.get("pass")
    if q_user and q_pwd:
        return (q_user.strip(), q_pwd.strip())

    return None


def resolve_auth(ctx: Optional[Context] = None, username: Optional[str] = None, password: Optional[str] = None) -> Optional[str]:
    """Získá platný token pro aktuální kontext/uživatele z hlaviček, session nebo přihlášení."""
    # 1. Přímo předané credentials v parametru nástroje
    if username and password:
        token = client.get_token(username, password)
        if token:
            return token

    # 2. ContextVar z aktuálního spojení SSE (nastaveno v handle_sse)
    creds = current_client_auth.get()
    if creds:
        u, p = creds
        token = client.get_token(u, p)
        if token:
            return token

    # 3. Z kontextu FastMCP (pokud je dostupný client_id nebo session)
    if ctx:
        cid = getattr(ctx, "client_id", None)
        if cid and cid in session_auth_store:
            u, p = session_auth_store[cid]
            token = client.get_token(u, p)
            if token:
                return token

    # 4. Poslední aktivní přihlášení (např. z helpdesk_login nebo POST zpráv)
    global active_login
    if active_login:
        u, p = active_login
        token = client.get_token(u, p)
        if token:
            return token

    # 5. Fallback na jediného přihlášeného klienta ve store (např. z hlaviček POST/GET)
    if session_auth_store:
        # Použijeme naposledy přidané credentials
        last_creds = list(session_auth_store.values())[-1]
        token = client.get_token(last_creds[0], last_creds[1])
        if token:
            return token

    # 6. Fallback na výchozí uživatele z .env (pokud je nastaven)
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

    creds = (username.strip(), password.strip())
    global active_login
    active_login = creds
    current_client_auth.set(creds)

    if ctx:
        cid = getattr(ctx, "client_id", None)
        if cid:
            session_auth_store[cid] = creds

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
    application_area_id: Optional[str] = None,
    application_sub_area_id: Optional[str] = None,
    level: Optional[int] = None,
    partner_l1: Optional[str] = None,
    partner_l2: Optional[str] = None,
    processor: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    solved_from: Optional[str] = None,
    solved_to: Optional[str] = None,
    modified_from: Optional[str] = None,
    modified_to: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_direction: Optional[str] = None,
    page_size: int = 50,
    page_index: int = 0,
    offset: Optional[int] = None,
    ctx: Context = None,
) -> Any:
    """
    Vyhledá tikety v AVAplace Helpdesku podle zadaných filtrů.
    Všechny filtry jsou volitelné.
    
    Parametry filtrů:
    - state: Interní stav (Draft, ToDo, Assigned, InProgress, Postponed, Question, Solved, Done)
    - external_state: Externí stav (Draft, InProgress, Question, Solved, Done)
    - priority: Priorita tiketu ('A' = Vysoká, 'B' = Střední, 'C' = Nízká)
    - search_text: Fulltextové vyhledávání v obsahu tiketu
    - title: Částečná shoda v názvu tiketu
    - customer: Název zákazníka/firmy (issuerCompany)
    - issuer: Jméno žadatele (issuerName)
    - application_id: ID aplikace (lze zjistit nástrojem 'get_applications')
    - application_area_id: ID oblasti aplikace (lze zjistit nástrojem 'get_application_areas')
    - application_sub_area_id: ID podoblasti aplikace (lze zjistit nástrojem 'get_application_areas')
    - level: Úroveň tiketu (např. 1 pro L1, 2 pro L2)
    - partner_l1 / partner_l2: Název nebo kód partnera L1 / L2
    - processor: Jméno řešitele tiketu (solverName)
    - created_from / created_to: Datum založení od/do (YYYY-MM-DD)
    - solved_from / solved_to: Datum vyřešení od/do (YYYY-MM-DD)
    - modified_from / modified_to: Datum změny od/do (YYYY-MM-DD)
    
    Parametry řazení:
    - sort_by: Název sloupce pro řazení (např. 'CreatedOn', 'ModifiedOn', 'Priority', 'TicketNumber', 'State')
    - sort_direction: Směr řazení ('Ascending' / 'Descending' nebo 'asc' / 'desc')
    
    Parametry stránkování:
    - page_size: Počet položek na stránku (výchozí 50, max 500)
    - page_index: Číslo stránky (0 = první stránka, 1 = druhá stránka atd.)
    - offset: Přímý offset přeskočených záznamů (volitelné, alternativa k page_index)
    
    Odpověď obsahuje 'has_more' (boolean) a 'next_page_index' pro načtení další stránky.
    """
    token = resolve_auth(ctx)
    if not token:
        return "⚠️ Nejste přihlášeni. Použijte nástroj 'helpdesk_login(username, password)' nebo nastavte hlavičky X-Helpdesk-User a X-Helpdesk-Password v konfiguraci klienta."

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
            application_area_id=application_area_id,
            application_sub_area_id=application_sub_area_id,
            level=level,
            partner_l1=partner_l1,
            partner_l2=partner_l2,
            processor=processor,
            created_from=created_from,
            created_to=created_to,
            solved_from=solved_from,
            solved_to=solved_to,
            modified_from=modified_from,
            modified_to=modified_to,
            sort_by=sort_by,
            sort_direction=sort_direction,
            page_size=page_size,
            page_index=page_index,
            offset=offset,
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
def get_application_areas(application_id: str, ctx: Context = None) -> Any:
    """
    Vrátí hierarchický seznam oblastí a podoblastí pro vybranou aplikaci (modul).
    Použijte získaná ID ('id') pro filtrování v search_tickets pomocí application_area_id nebo application_sub_area_id.
    
    Parametry:
    - application_id: ID aplikace (lze získat nástrojem 'get_applications')
    """
    token = resolve_auth(ctx)
    if not token:
        return "⚠️ Nejste přihlášeni. Použijte nástroj 'helpdesk_login(username, password)'."

    try:
        return client.get_application_areas(token=token, application_id=application_id)
    except Exception as e:
        return f"Chyba při načítání oblastí aplikace '{application_id}': {e}"


@mcp.tool()
def get_filter_options() -> Dict[str, Any]:
    """Vrátí přehled platných hodnot pro filtrování tiketů (stavy, priority, úrovně, typy)."""
    return {
        "states": [
            {"code": "Draft", "name": "Koncept / Návrh"},
            {"code": "ToDo", "name": "K vyřízení"},
            {"code": "Assigned", "name": "Přiřazeno"},
            {"code": "InProgress", "name": "Rozpracováno / K řešení"},
            {"code": "Postponed", "name": "Odloženo"},
            {"code": "Question", "name": "Dotaz"},
            {"code": "Solved", "name": "Vyřešeno"},
            {"code": "Done", "name": "Hotovo / Uzavřeno"},
        ],
        "priorities": [
            {"code": "A", "name": "Vysoká (High)"},
            {"code": "B", "name": "Střední (Medium)"},
            {"code": "C", "name": "Nízká (Low)"},
        ],
        "levels": [
            {"code": 1, "name": "Úroveň L1 (první linie podpory)"},
            {"code": 2, "name": "Úroveň L2 (specialisté / vývoj)"},
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

    token_ctx = None
    if creds:
        token_ctx = current_client_auth.set(creds)
        session_auth_store[client_ip] = creds
        global active_login
        active_login = creds
        print(f"🔐 Klient {client_ip} připojen přes SSE s údaji pro '{creds[0]}'")

    try:
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp_server.run(
                streams[0],
                streams[1],
                mcp_server.create_initialization_options(),
            )
    finally:
        if token_ctx:
            current_client_auth.reset(token_ctx)

    return Response()


async def messages_endpoint(scope, receive, send):
    """Wrapper pro POST /messages/ endpoint, který zachytává credentials z hlaviček a session_id."""
    if scope["type"] == "http":
        request = Request(scope)
        creds = _extract_credentials_from_request(request)
        session_id = request.query_params.get("session_id")
        client_ip = request.client.host if request.client else "unknown"

        if creds:
            if session_id:
                session_auth_store[session_id] = creds
            session_auth_store[client_ip] = creds
            global active_login
            active_login = creds
            current_client_auth.set(creds)
            print(f"🔐 Zpráva na /messages/ od {client_ip} s údaji pro '{creds[0]}'")

        await sse.handle_post_message(scope, receive, send)
    else:
        await sse.handle_post_message(scope, receive, send)


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
    Mount("/messages/", app=messages_endpoint),
]

app = Starlette(routes=routes)

if __name__ == "__main__":
    print(f"🚀 Spouštím ASOL HelpDesk MCP server na http://{HOST}:{PORT}")
    print(f"   Health check: http://{HOST}:{PORT}/health")
    print(f"   SSE endpoint: http://{HOST}:{PORT}/sse")
    uvicorn.run(app, host=HOST, port=PORT)
