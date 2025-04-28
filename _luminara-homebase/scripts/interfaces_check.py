import asyncio
import aiohttp
import json
import tomllib
import ssl
import re
import os
from datetime import datetime, UTC
from bs4 import BeautifulSoup

# Start time
START_TIME = datetime.now(UTC).isoformat() + "Z"

# Paths
BASE_PATH = "_luminara-homebase"
CONFIG_PATH = os.path.join(BASE_PATH, "services_health_config.json")
OUTPUT_PATH = os.path.join(BASE_PATH, "interface-status.json")

# Load configuration
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    HEALTH_CONFIG = json.load(f)

# URLs
INTERFACES = {
    "namada": {"interface": "https://raw.githubusercontent.com/Luminara-Hub/namada-ecosystem/main/user-and-dev-tools/mainnet/interfaces.json"},
    "housefire": {"interface": "https://raw.githubusercontent.com/Luminara-Hub/namada-ecosystem/main/user-and-dev-tools/testnet/housefire/interfaces.json"}
}

HEADERS = {"User-Agent": "Mozilla/5.0"}
SSL_CONTEXT = ssl.create_default_context()

async def fetch_url(session, url, retries=3, timeout=5):
    for attempt in range(retries):
        try:
            async with session.get(url, ssl=SSL_CONTEXT, timeout=timeout) as response:
                response.raise_for_status()
                return await response.text()
        except Exception as e:
            if attempt == retries - 1:
                print(f"[WARN] Failed to fetch {url}: {e}")
            await asyncio.sleep(2)
    return None

async def fetch_json(session, url):
    data = await fetch_url(session, url)
    if not data:
        return {}
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        print(f"[WARN] Failed to decode JSON from {url}")
        return {}

def extract_moniker_version(moniker):
    match = re.search(r"[-_]v(\d+\.\d+\.\d+)", moniker)
    return match.group(1) if match else "n/a"

def compare_versions(current, required):
    def version_tuple(v):
        return tuple(map(int, v.split('.')))
    try:
        return version_tuple(current) >= version_tuple(required)
    except:
        return False

def determine_status(block_height, latest_block, service_conf):
    if latest_block == 0 or not service_conf:
        return "Down"
    thresholds = service_conf.get("block_lag_thresholds", {})
    if "healthy" not in thresholds or "max" not in thresholds:
        return "Down"
    healthy = thresholds["healthy"]
    max_lag = thresholds["max"]
    lag = latest_block - block_height
    if lag <= healthy:
        return "Healthy"
    elif lag <= max_lag:
        return "Outdated"
    return "Down"

async def get_interface_version(session, url):
    html = await fetch_url(session, url)
    if not html:
        return "n/a"
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", {"type": "module", "crossorigin": True})
    if script and "src" in script.attrs:
        js_url = f"{url.rstrip('/')}/{script['src'].lstrip('/')}"
        js_content = await fetch_url(session, js_url)
        if js_content:
            match = re.search(r'version\\$1\\s*=\\s*\"([\\d.]+)\"', js_content)
            if match:
                return match.group(1)
    return "n/a"

async def parse_config(session, url):
    try:
        async with session.get(f"{url}/config.toml", ssl=SSL_CONTEXT, timeout=3) as response:
            response.raise_for_status()
            config_data = await response.read()
            config = tomllib.loads(config_data)
            return {
                "rpc": config.get("rpc_url", "n/a"),
                "indexer": config.get("indexer_url", "n/a"),
                "masp": config.get("masp_indexer_url", "n/a")
            }
    except Exception as e:
        print(f"[WARN] Failed to parse config for {url}: {e}")
        return {"rpc": "n/a", "indexer": "n/a", "masp": "n/a"}

async def get_service_data(session, service, url):
    if service == "rpc":
        rpc_status = await fetch_json(session, f"{url}/status")
        sync_info = rpc_status.get("result", {}).get("sync_info", {})
        node_info = rpc_status.get("result", {}).get("node_info", {})
        return {
            "version": node_info.get("version", "n/a"),
            "namada_version": extract_moniker_version(node_info.get("moniker", "")),
            "service": service,
            "url": url,
            "latest_block_height": str(sync_info.get("latest_block_height", "0"))
        }
    else:
        if "indexer" in service:
            block_data = await fetch_json(session, f"{url}/api/v1/chain/block/latest")
        else:
            block_data = await fetch_json(session, f"{url}/api/v1/height")
        health_data = await fetch_json(session, f"{url}/health")
        return {
            "version": health_data.get("version", "n/a"),
            "service": service,
            "url": url,
            "latest_block_height": str(block_data.get("block_height") or block_data.get("block") or "0")
        }

async def process_network(session, network, sources):
    interfaces_json = await fetch_url(session, sources["interface"], timeout=5)
    if not interfaces_json:
        return None
    try:
        interfaces = json.loads(interfaces_json)
    except:
        return None

    config_ref = HEALTH_CONFIG.get(network, {})
    network_interfaces = []

    for interface in interfaces:
        if "Namadillo" not in interface.get("Interface Name (Namadillo or Custom)", ""):
            continue
        interface_url = interface.get("Interface URL", "").rstrip('/')
        if not interface_url:
            continue

        config = await parse_config(session, interface_url)
        settings_tasks = [
            get_service_data(session, "indexer", config.get("indexer")),
            get_service_data(session, "rpc", config.get("rpc")),
            get_service_data(session, "masp", config.get("masp"))
        ]
        settings = await asyncio.gather(*settings_tasks)

        namada_version = next((s.get("namada_version") for s in settings if s["service"] == "rpc"), "n/a")
        latest_block = max((int(s.get("latest_block_height", 0)) for s in settings if s.get("latest_block_height", "0").isdigit()), default=0)

        for idx, s in enumerate(settings):
            height = int(s.get("latest_block_height", 0)) if s.get("latest_block_height", "0").isdigit() else 0
            service_conf = config_ref.get("services", {}).get(s["service"], {})
            settings[idx] = {
                "service": s.get("service"),
                "url": s.get("url", "n/a"),
                "version": s.get("version", "n/a"),
                "is_up_to_date": compare_versions(s.get("version", "n/a"), service_conf.get("required_version", "n/a")),
                "latest_block_height": s.get("latest_block_height", "n/a"),
                "status": determine_status(height, latest_block, service_conf),
                **({"namada_version": s.get("namada_version", "n/a")} if s["service"] == "rpc" else {})
            }

        interface_version = await get_interface_version(session, interface_url)
        interface_required_version = config_ref.get("interface", {}).get("required_version", "n/a")

        network_interfaces.append({
            "team": interface.get("Team or Contributor Name", "Unknown"),
            "discord": interface.get("Discord UserName", "Unknown"),
            "url": interface_url,
            "version": interface_version,
            "is_up_to_date": compare_versions(interface_version, interface_required_version),
            "settings": settings
        })

    return {"network": network, "interface": network_interfaces}

async def main():
    output_data = {
        "script_start_time": START_TIME,
        "script_end_time": "",
        "required_versions": {
            "interface": HEALTH_CONFIG.get("namada", {}).get("interface", {}).get("required_version", "n/a"),
            "indexer": HEALTH_CONFIG.get("namada", {}).get("services", {}).get("indexer", {}).get("required_version", "n/a"),
            "rpc": HEALTH_CONFIG.get("namada", {}).get("services", {}).get("rpc", {}).get("required_version", "n/a"),
            "masp": HEALTH_CONFIG.get("namada", {}).get("services", {}).get("masp", {}).get("required_version", "n/a")
        },
        "networks": []
    }

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tasks = [process_network(session, network, sources) for network, sources in INTERFACES.items()]
        networks = await asyncio.gather(*tasks)
        output_data["networks"] = [net for net in networks if net]

    output_data["script_end_time"] = datetime.now(UTC).isoformat() + "Z"

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=4)

if __name__ == "__main__":
    asyncio.run(main())
