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
        """Vyhledá tikety podle zadaných filtrů."""
        endpoint = f"{self.api_url}/api/v1/Tickets"
        limit = max(1, min(page_size, 500))
        actual_offset = offset if offset is not None else (page_index * limit)

        params: Dict[str, Any] = {
            "Limit": limit,
            "Offset": actual_offset,
            "pagingFilter.Limit": limit,
            "pagingFilter.Offset": actual_offset,
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
            params["ticketFilter.ApplicationAreaId"] = application_area_id
        if application_sub_area_id:
            params["ApplicationSubAreaId"] = application_sub_area_id
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
        if sort_by:
            params["SortBy"] = sort_by
        if sort_direction:
            d = str(sort_direction).strip().lower()
            if "desc" in d:
                params["Direction"] = "Descending"
            elif "asc" in d:
                params["Direction"] = "Ascending"
            else:
                params["Direction"] = sort_direction

        headers = self._get_headers(token)
        resp = requests.get(endpoint, headers=headers, params=params, timeout=30)
        resp.raise_for_status()

        data = resp.json()
        if isinstance(data, dict):
            items = data.get("items", [])
            total = data.get("totalCount", len(items))
        elif isinstance(data, list):
            items = data
            total = len(data)
        else:
            items = []
            total = 0

        # Optimalizace dat pro LLM kontext - vytáhnout nejdůležitější pole dle TicketModelSummary
        formatted = []
        for t in items:
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
                "application_area": t.get("applicationAreaName"),
                "application_sub_area": t.get("applicationSubAreaName"),
                "partner_l1": t.get("partnerL1Name") or t.get("partnerL1Code"),
                "partner_l2": t.get("partnerL2Name") or t.get("partnerL2Code"),
                "created": t.get("createdOn") or t.get("created"),
                "modified": t.get("modifiedOn") or t.get("modified"),
                "solved": t.get("solvedOn") or t.get("solved"),
                "closed": t.get("closedOn") or t.get("closed"),
                "jira_issue": t.get("jiraIssueKey"),
            })

        has_more = (actual_offset + len(formatted)) < total
        return {
            "total_count": total,
            "returned_count": len(formatted),
            "page_index": page_index,
            "page_size": limit,
            "offset": actual_offset,
            "limit": limit,
            "has_more": has_more,
            "next_page_index": (page_index + 1) if has_more else None,
            "next_offset": (actual_offset + len(formatted)) if has_more else None,
            "tickets": formatted,
        }

    def get_ticket(self, token: str, ticket_identifier: str) -> Dict[str, Any]:
        """Získá detail konkrétního tiketu podle ID nebo kódu (např. HD-12345)."""
        ticket_id = ticket_identifier.strip()
        endpoint = f"{self.api_url}/api/v1/Tickets/{ticket_id}"

        headers = self._get_headers(token)
        resp = requests.get(endpoint, headers=headers, timeout=20)
        resp.raise_for_status()
        return resp.json()

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
