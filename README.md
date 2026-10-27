# ASOL HelpDesk MCP Server (Read-Only)

Tento repozitář obsahuje **Model Context Protocol (MCP)** server pro čtení dat z HelpDesku platformy **AVAplace** (Asseco Solutions).

Server běží v Docker kontejneru a poskytuje rozhraní přes **Server-Sent Events (SSE)** na portu **8095**. Umožňuje kolegům i AI asistentům (Claude Desktop, Cursor, VS Code Copilot, Antigravity) přistupovat k tiketům pod jejich vlastními přihlašovacími údaji.

---

## 🌟 Hlavní vlastnosti

- **Striktně Read-Only:** Žádné metody pro zápis, editaci nebo mazání neexistují.
- **Podpora přihlášení uživatele:** Každý uživatel vidí data dle svých oprávnění v AVAplace:
  - **Možnost A:** Zadáním hlaviček `X-Helpdesk-User` a `X-Helpdesk-Password` do konfigurace klienta.
  - **Možnost B:** Voláním nástroje `helpdesk_login(username, password)` přímo v okně chatu.
  - **Možnost C:** Výchozí servisní účet v `.env` (pokud je nastaven).
- **Optimalizováno pro LLM:** Vyhledávání tiketů vrací přehledný, ořezaný souhrn důležitých polí bez zahlcení kontextového okna.
- **Docker & Cloudflare Tunnel ready:** Běží na portu 8095 a zapadá do sítě `infrastructure_default`.

---

## 🚀 Rychlé zprovoznění na serveru (`/opt/asolhelpdeskmcp`)

Na vašem Linux/Docker serveru spusťte následující příkazy:

```bash
# 1. Vytvoření složky a přechod do ní
sudo mkdir -p /opt/asolhelpdeskmcp
sudo chown -R $USER:$USER /opt/asolhelpdeskmcp
cd /opt/asolhelpdeskmcp

# 2. Naklonování repozitáře
git clone https://github.com/macikm/asolhelpdeskmcp.git .

# 3. Nastavení spustitelnosti aktualizačního skriptu
chmod +x update.sh

# 4. Příprava .env souboru
cp .env.example .env
# (Volitelně upravte nastavení pomocí: nano .env)

# 5. Ověření existence Docker sítě (pokud ještě neexistuje)
docker network inspect infrastructure_default >/dev/null 2>&1 || docker network create infrastructure_default

# 6. Sestavení a spuštění kontejneru
docker compose up -d --build
```

### Ověření běhu:
```bash
# Test health checku:
curl http://localhost:8095/health
# Mělo by vrátit: {"status":"healthy","service":"asolhelpdeskmcp",...}

# Kontrola logů:
docker compose logs -f
```

---

## 🔄 Automatické aktualizace (`update.sh`)

Skript `update.sh` zkontroluje novou verzi v Git repozitáři. Pokud najde změny, stáhne je (`git pull`) a automaticky přebuduje a restartuje kontejner:

```bash
./update.sh
```

Pro pravidelné automatické kontroly (např. každých 15 minut) přidejte do `crontab -e`:
```cron
*/15 * * * * cd /opt/asolhelpdeskmcp && ./update.sh >> /var/log/asolhelpdeskmcp_update.log 2>&1
```

---

## 🌐 Cloudflare Tunnel konfigurace

V Cloudflare Zero Trust (Tunnels) nastavte novou routu / Public Hostname:
- **Subdomain / Domain:** např. `helpdesk-mcp.vasedomena.cz`
- **Service Type:** `HTTP`
- **URL:** `localhost:8095` (nebo `asolhelpdeskmcp:8095` pokud cloudflared běží ve stejné Docker síti)

---

## 💻 Jak se připojí kolegové z AI klientů

### 1. Claude Desktop (`claude_desktop_config.json`)

Pokud používají Claude Desktop s podporou SSE transportu:
```json
{
  "mcpServers": {
    "asol-helpdesk": {
      "url": "https://helpdesk-mcp.vasedomena.cz/sse",
      "headers": {
        "X-Helpdesk-User": "kolega@assecosol.com",
        "X-Helpdesk-Password": "JehoHeslo123"
      }
    }
  }
}
```

### 2. Cursor IDE (`.cursor/mcp.json` nebo nastavení Features -> MCP)
Přidat nový MCP Server:
- **Type:** `SSE`
- **URL:** `https://helpdesk-mcp.vasedomena.cz/sse`
- **Headers:**
  - `X-Helpdesk-User`: `kolega@assecosol.com`
  - `X-Helpdesk-Password`: `JehoHeslo123`

### 3. Klienti bez podpory HTTP hlaviček
Pokud klient neumí posílat vlastní hlavičky, kolega se jednoduše připojí na `https://helpdesk-mcp.vasedomena.cz/sse` a v chatu s AI napíše:
> *"Přihlas mě do helpdesku jako uzivatel@assecosol.com s heslem MojeHeslo123"*

Model automaticky zavolá nástroj `helpdesk_login`, získá OAuth2 token a od té chvíle má přístup k tiketům.

---

## 🛠️ Dostupné nástroje (MCP Tools)

| Nástroj | Popis |
|---|---|
| `helpdesk_login(username, password)` | Přihlášení do AVAplace (získá a uloží OAuth2 token pro session). |
| `search_tickets(...)` | Filtrování tiketů podle stavu (`InProgress`, `Solved`), priority (`A`, `B`, `C`), zákazníka, řešitele, data či fulltextu. |
| `get_ticket_detail(ticket_identifier)` | Vrátí kompletní detail tiketu dle ID nebo kódu (např. `HD-12345`). |
| `get_applications()` | Seznam modulů / aplikací v Helpdesku. |
| `get_filter_options()` | Vrátí číselníky platných stavů a priorit pro nápovědu modelu. |
