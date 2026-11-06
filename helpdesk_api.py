"""
AVAplace HelpDesk API Client
Obsluhuje autentizaci přes OAuth2 a volání HelpDesk REST API.
Pouze pro čtení (Read-Only).
"""

import time
import requests
from typing import Optional, List, Dict, Any


class HelpdeskClient:
    OAUTH_CLIENT_ID = "plaza-pass"
    OAUTH_CLIENT_SECRET = ""
    OAUTH_SCOPE = "apiim openid"

    def __init__(self, api_url: str, auth_url: Optional[str] = None):
        self.api_url = api_url.rstrip("/")
        if auth_url:
            self.auth_url = auth_url
        else:
            base_url = self.api_url.lower()
            if "/asoleu/helpdesk" in base_url:
                self.auth_url = base_url.replace("/asoleu/helpdesk", "/asol/idp/connect/token")
            elif "/helpdesk" in base_url:
                base = base_url.split("/helpdesk")[0]
                self.auth_url = f"{base}/idp/connect/token"
            else:
                self.auth_url = "https://avaplace.com/api/asol/idp/connect/token"

        # Paměť tokenů: {(username, password): (token, expires_at)}
        self._token_cache: Dict[tuple, tuple] = {}

    def get_token(self, username: str, password: str) -> Optional[str]:
        """Získá nebo vrátí z cache platný OAuth2 token pro dané credentials."""
        cache_key = (username, password)
        now = time.time()

        if cache_key in self._token_cache:
            token, expires_at = self._token_cache[cache_key]
            if now < expires_at - 60:  # Rezerva 60s před expirací
                return token

        # Získání nového tokenu
        data = {
            "grant_type": "password",
            "username": username,
            "password": password,
            "scope": self.OAUTH_SCOPE,
            "client_id": self.OAUTH_CLIENT_ID,
        }
        if self.OAUTH_CLIENT_SECRET:
            data["client_secret"] = self.OAUTH_CLIENT_SECRET

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ASOL-Helpdesk-MCP/1.0",
            "Origin": "https://avaplace.com",
            "Referer": f"{self.api_url}/swagger/index.html",
        }

        try:
            resp = requests.post(self.auth_url, data=data, headers=headers, timeout=15)
            if resp.status_code != 200:
                print(f"[Auth Error] Status {resp.status_code}: {resp.text[:200]}")
                return None

            token_data = resp.json()
            access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 3600)

            if access_token:
                self._token_cache[cache_key] = (access_token, now + expires_in)
                return access_token
        except Exception as e:
            print(f"[Auth Exception] {e}")

        return None

    def _get_headers(self, token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ASOL-Helpdesk-MCP/1.0",
        }

    def search_tickets(
        self,
        token: str,
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
    ) -> Dict[str, Any]:
        """Vyhledá tikety podle zadaných filtrů s podporou řazení a oblastí."""
        limit = max(1, min(page_size, 500))
        actual_offset = offset if offset is not None else (page_index * limit)
        headers = self._get_headers(token)

        # Normalizace řazení
        order_val = "Descending"
        if sort_direction:
            d = str(sort_direction).strip().lower()
            if "asc" in d:
                order_val = "Ascending"
            elif "desc" in d:
                order_val = "Descending"
            else:
                order_val = sort_direction
        sort_col = sort_by if sort_by else "CreatedOn"

        # 1. POKUS: Moderní grid endpoint POST /api/v1/Tickets/list (podporuje plné řazení i filtry)
        items = None
        total = 0
        use_post_success = False
        post_error_info = None

        try:
            filters_list = []
            if state:
                filters_list.append({"field": "State", "type": "List", "value": [state], "operator": "Equal"})
            if external_state:
                filters_list.append({"field": "ExternalState", "type": "List", "value": [external_state], "operator": "Equal"})
            if priority:
                filters_list.append({"field": "Priority", "type": "List", "value": [priority], "operator": "Equal"})
            if customer:
                filters_list.append({"field": "Customer", "type": "Text", "value": [customer], "operator": "Contains"})
            if issuer:
                filters_list.append({"field": "IssuerFullName", "type": "Text", "value": [issuer], "operator": "Contains"})
            if application_id:
                filters_list.append({"field": "ApplicationId", "type": "List", "value": [application_id], "operator": "Equal"})
            if application_area_id:
                filters_list.append({"field": "ApplicationAreaId", "type": "List", "value": [application_area_id], "operator": "Equal"})
            if application_sub_area_id:
                filters_list.append({"field": "ApplicationSubAreaId", "type": "List", "value": [application_sub_area_id], "operator": "Equal"})
            if level is not None:
                filters_list.append({"field": "Level", "type": "Number", "value": [level], "operator": "Equal"})
            if partner_l1:
                filters_list.append({"field": "PartnerL1", "type": "Text", "value": [partner_l1], "operator": "Contains"})
            if partner_l2:
                filters_list.append({"field": "PartnerL2", "type": "Text", "value": [partner_l2], "operator": "Contains"})
            if processor:
                filters_list.append({"field": "Solver", "type": "Text", "value": [processor], "operator": "Contains"})

            post_body = {
                "offset": actual_offset,
                "limit": limit,
                "sortColumn": sort_col,
                "sortOrder": order_val,
                "filter": {
                    "wideSearch": search_text if search_text else "",
                    "filters": filters_list,
                }
            }

            post_endpoint = f"{self.api_url}/api/v1/Tickets/list"
            resp = requests.post(post_endpoint, headers=headers, json=post_body, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    items = data.get("items", [])
                    total = data.get("totalItemsCount", data.get("totalCount", len(items)))
                    use_post_success = True
                    print(f"✅ [Tickets/list] Úspěšně načteno {len(items)} tiketů z grid endpointu (total: {total})")
            else:
                post_error_info = {
                    "status_code": resp.status_code,
                    "error_text": resp.text[:1000],
                    "payload_sent": post_body,
                }
                print(f"⚠️ [Tickets/list Error] Status {resp.status_code}: {resp.text[:400]}")
        except Exception as ex:
            post_error_info = {
                "exception": str(ex),
            }
            print(f"⚠️ [Tickets/list Exception] {ex}")

        # 2. POKUS (Fallback): Klasický GET /api/v1/Tickets se všemi variantami parametrů
        if not use_post_success:
            print(f"ℹ️ [Tickets] Volám záložní GET /api/v1/Tickets endpoint...")
            get_endpoint = f"{self.api_url}/api/v1/Tickets"
            params: Dict[str, Any] = {
                "Limit": limit,
                "Offset": actual_offset,
                "pagingFilter.Limit": limit,
                "pagingFilter.Offset": actual_offset,
                "SortBy": sort_col,
                "SortColumn": sort_col,
                "sortColumn": sort_col,
                "Direction": order_val,
                "SortOrder": order_val,
                "sortOrder": order_val,
                "sortingFilter.SortBy": sort_col,
                "sortingFilter.Direction": order_val,
                "sortingFilter.SortColumn": sort_col,
                "sortingFilter.SortOrder": order_val,
            }

            if state:
                params["State"] = state
                params["ticketFilter.State"] = state
            if external_state:
                params["ExternalState"] = external_state
                params["ticketFilter.ExternalState"] = external_state
            if priority:
                params["Priority"] = priority
                params["ticketFilter.Priority"] = priority
            if search_text:
                params["SearchText"] = search_text
                params["ticketFilter.SearchText"] = search_text
            if title:
                params["Title"] = title
                params["ticketFilter.Title"] = title
            if customer:
                params["Customer"] = customer
                params["ticketFilter.Customer"] = customer
            if issuer:
                params["IssuerFullName"] = issuer
                params["ticketFilter.IssuerFullName"] = issuer
            if application_id:
                params["ApplicationId"] = application_id
                params["ticketFilter.ApplicationId"] = application_id
            if application_area_id:
                params["ApplicationAreaId"] = application_area_id
                params["AreaId"] = application_area_id
                params["ticketFilter.ApplicationAreaId"] = application_area_id
            if application_sub_area_id:
                params["ApplicationSubAreaId"] = application_sub_area_id
                params["SubAreaId"] = application_sub_area_id
                params["ticketFilter.ApplicationSubAreaId"] = application_sub_area_id
            if level is not None:
                params["Level"] = level
                params["ticketFilter.Level"] = level
            if partner_l1:
                params["PartnerL1"] = partner_l1
                params["ticketFilter.PartnerL1"] = partner_l1
            if partner_l2:
                params["PartnerL2"] = partner_l2
                params["ticketFilter.PartnerL2"] = partner_l2
            if processor:
                params["Solver"] = processor
                params["ticketFilter.Solver"] = processor
            if created_from:
                params["CreatedFrom"] = created_from
                params["ticketFilter.CreatedFrom"] = created_from
            if created_to:
                params["CreatedTo"] = created_to
                params["ticketFilter.CreatedTo"] = created_to
            if solved_from:
                params["SolvedFrom"] = solved_from
                params["ticketFilter.SolvedFrom"] = solved_from
            if solved_to:
                params["SolvedTo"] = solved_to
                params["ticketFilter.SolvedTo"] = solved_to
            if modified_from:
                params["ModifiedFrom"] = modified_from
                params["ticketFilter.ModifiedFrom"] = modified_from
            if modified_to:
                params["ModifiedTo"] = modified_to
                params["ticketFilter.ModifiedTo"] = modified_to

            resp = requests.get(get_endpoint, headers=headers, params=params, timeout=30)
            resp.raise_for_status()

            data = resp.json()
            if isinstance(data, dict):
                items = data.get("items", [])
                total = data.get("totalCount", data.get("totalItemsCount", len(items)))
            elif isinstance(data, list):
                items = data
                total = len(data)
            else:
                items = []
                total = 0

        # Optimalizace dat pro LLM kontext - vytáhnout nejdůležitější pole dle TicketModelSummary
        formatted = []
        for t in (items or []):
            formatted.append({
                "id": t.get("id"),
                "ticket_code": f"{t.get('applicationCode', '')}-{t.get('number', '')}".strip("-"),
                "title": t.get("title"),
                "state": t.get("stateName") or t.get("state"),
                "external_state": t.get("externalStateName") or t.get("externalState"),
                "priority": t.get("priorityName") or t.get("priority"),
                "level": t.get("level"),
                "customer": t.get("issuerCompany") or t.get("customer"),
                "issuer": t.get("issuerName") or t.get("issuerFullName"),
                "processor": t.get("solverName") or t.get("processorFullName") or t.get("solverL1Name"),
                "application_id": t.get("applicationId"),
                "application_area": t.get("applicationAreaName"),
                "application_area_id": t.get("applicationAreaId"),
                "application_sub_area": t.get("applicationSubAreaName"),
                "application_sub_area_id": t.get("applicationSubAreaId"),
                "partner_l1": t.get("partnerL1Name") or t.get("partnerL1Code"),
                "partner_l2": t.get("partnerL2Name") or t.get("partnerL2Code"),
                "created": t.get("createdOn") or t.get("created"),
                "modified": t.get("modifiedOn") or t.get("modified"),
                "solved": t.get("solvedOn") or t.get("solved"),
                "closed": t.get("closedOn") or t.get("closed"),
                "jira_issue": t.get("jiraIssueKey"),
            })

        # Pojistka: Klientské in-memory řazení, pokud GET endpoint vrátil neseřazená data
        if sort_by and formatted:
            sort_key_map = {
                "createdon": "created",
                "created": "created",
                "modifiedon": "modified",
                "modified": "modified",
                "ticketcode": "ticket_code",
                "number": "ticket_code",
                "title": "title",
                "priority": "priority",
                "state": "state",
            }
            target_key = sort_key_map.get(sort_by.lower(), sort_by.lower())
            is_reverse = ("desc" in order_val.lower())
            try:
                formatted.sort(key=lambda x: str(x.get(target_key) or ""), reverse=is_reverse)
            except Exception:
                pass

        has_more = (actual_offset + len(formatted)) < total
        result = {
            "total_count": total,
            "returned_count": len(formatted),
            "page_index": page_index,
            "page_size": limit,
            "offset": actual_offset,
            "limit": limit,
            "has_more": has_more,
            "next_page_index": (page_index + 1) if has_more else None,
            "next_offset": (actual_offset + len(formatted)) if has_more else None,
            "endpoint_used": "POST /api/v1/Tickets/list" if use_post_success else "GET /api/v1/Tickets (fallback)",
            "tickets": formatted,
        }

        # Pokud POST endpoint selhal, přidáme do odpovědi srozumitelné varování a detail chyby
        if post_error_info:
            result["warning"] = (
                f"Upozornění: Grid endpoint POST /api/v1/Tickets/list vrátil chybu "
                f"(HTTP {post_error_info.get('status_code')}). Použit záložní GET endpoint. "
                f"Detaily: {post_error_info.get('error_text', '')[:300]}"
            )
            result["post_error_debug"] = post_error_info

        return result

    def get_ticket(self, token: str, ticket_identifier: str, load_comments: bool = True) -> Dict[str, Any]:
        """Získá detail konkrétního tiketu podle ID nebo kódu (např. HD-12345) včetně komentářů."""
        ticket_id = ticket_identifier.strip()
        endpoint = f"{self.api_url}/api/v1/Tickets/{ticket_id}"

        headers = self._get_headers(token)
        resp = requests.get(endpoint, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        # Automatické načtení komentářů k tiketu
        if load_comments:
            try:
                real_id = data.get("id") or ticket_id
                data["comments"] = self.get_ticket_comments(token=token, ticket_identifier=real_id)
            except Exception:
                data["comments"] = []

        return data

    def get_ticket_comments(self, token: str, ticket_identifier: str) -> List[Dict[str, Any]]:
        """Získá komentáře (konverzaci a historii řešení) k danému tiketu podle ID nebo kódu."""
        import re
        ticket_id = ticket_identifier.strip()
        
        # Ověřit, zda je identifikátor GUID (36 znaků s pomlčkami). Pokud ne, přeložit přes get_ticket
        is_guid = bool(re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", ticket_id))
        real_id = ticket_id
        if not is_guid:
            try:
                ticket_data = self.get_ticket(token=token, ticket_identifier=ticket_id, load_comments=False)
                if isinstance(ticket_data, dict) and ticket_data.get("id"):
                    real_id = ticket_data.get("id")
            except Exception as e:
                print(f"⚠️ Nelze přeložit kód tiketu '{ticket_id}' na GUID: {e}")

        endpoint = f"{self.api_url}/api/v1/Tickets/{real_id}/comments"
        headers = self._get_headers(token)
        params = {
            "Offset": 0,
            "Limit": 200,
            "SortBy": "CreatedOn",
            "Direction": "Ascending",
        }
        resp = requests.get(endpoint, headers=headers, params=params, timeout=20)
        resp.raise_for_status()

        data = resp.json()
        if isinstance(data, dict) and "items" in data:
            comments = data["items"]
        elif isinstance(data, list):
            comments = data
        else:
            comments = []

        return [
            {
                "id": c.get("id"),
                "created_on": c.get("createdOn"),
                "created_by": c.get("createdBy"),
                "modified_on": c.get("modifiedOn"),
                "title": c.get("title"),
                "content": c.get("content"),
                "is_internal": c.get("isInternal", False),
            }
            for c in comments
        ]

    def get_applications(self, token: str) -> List[Dict[str, Any]]:
        """Získá seznam dostupných aplikací."""
        endpoint = f"{self.api_url}/api/v1/Applications"
        headers = self._get_headers(token)
        resp = requests.get(endpoint, headers=headers, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        if isinstance(data, dict) and "items" in data:
            apps = data["items"]
        elif isinstance(data, list):
            apps = data
        else:
            apps = []

        return [
            {
                "id": a.get("id"),
                "code": a.get("code"),
                "name": a.get("name"),
                "description": a.get("description"),
            }
            for a in apps
        ]

    def get_application_areas(self, token: str, application_id: str) -> List[Dict[str, Any]]:
        """Získá oblasti a podoblasti pro zadanou aplikaci."""
        endpoint = f"{self.api_url}/api/v1/Applications/{application_id}/areas"
        headers = self._get_headers(token)
        resp = requests.get(endpoint, headers=headers, timeout=20)
        resp.raise_for_status()

        data = resp.json()
        if isinstance(data, dict) and "items" in data:
            areas = data["items"]
        elif isinstance(data, list):
            areas = data
        else:
            areas = []

        return [
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "parent_id": a.get("parentId"),
                "is_parent": bool(a.get("isParent") or a.get("isParrent")),
                "nested_level": a.get("nestedLevel", 0),
                "active": a.get("active", True),
                "description": a.get("description"),
            }
            for a in areas
        ]
