import urllib.request
import json
import tomllib
import ssl
import time
import re
import os
from datetime import datetime, UTC
from bs4 import BeautifulSoup

# Start time
START_TIME = datetime.now(UTC).isoformat() + "Z"

# Enable / Disable Housefire
ENABLE_HOUSEFIRE = False

# Paths
BASE_PATH = "_luminara-homebase"
CONFIG_PATH = os.path.join(BASE_PATH, "services_health_config.json")
OUTPUT_PATH = os.path.join(BASE_PATH, "interface-status.json")

# Load configuration
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    HEALTH_CONFIG = json.load(f)

# Interface sources
INTERFACES = {
    "namada": {
        "interface": "https://raw.githubusercontent.com/Luminara-Hub/namada-ecosystem/main/user-and-dev-tools/mainnet/interfaces.json"
    }
}
if ENABLE_HOUSEFIRE:
    INTERFACES["housefire"] = {
        "interface": "https://raw.githubusercontent.com/Luminara-Hub/namada-ecosystem/main/user-and-dev-tools/testnet/housefire/interfaces.json"
    }

HEADERS = {"User-Agent": "Mozilla/5.0"}
SSL_CONTEXT = ssl.create_default_context()

def fetch_url(url, retries=3, timeout=5):
    for _ in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), context=SSL_CONTEXT, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except:
            time.sleep(2)
    return None

def fetch_json(url):
    data = fetch_url(url)
    try:
        return json.loads(data) if data else {}
    except json.JSONDecodeError:
        return {}

def get_interface_version(url):
    if not (r := fetch_url(url)):
        return "n/a"
    soup = BeautifulSoup(r, "html.parser")
    script = soup.find("script", {"type": "module", "crossorigin": True})
    if script and "src" in script.attrs:
        js_url = f"{url.rstrip('/')}/{script['src'].lstrip('/')}"
        js_content = fetch_url(js_url)
        if js_content and (match := re.search(r'version\$1\s*=\s*"([\d.]+)"', js_content)):
            return match.group(1)
    return "n/a"

def parse_config(url):
    data = fetch_url(f"{url}/config.toml", timeout=5)
    if not data or not data.strip():
        return {"rpc": "n/a", "indexer": "n/a", "masp": "n/a"}
    try:
        config = tomllib.loads(data.encode('utf-8'))  # toujours encoder en bytes
        return {
            "rpc": config.get("rpc_url", "n/a"),
            "indexer": config.get("indexer_url", "n/a"),
            "masp": config.get("masp_indexer_url", "n/a")
        }
    except tomllib.TOMLDecodeError:
        return {"rpc": "n/a", "indexer": "n/a", "masp": "n/a"}

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

def get_service_data(service, url):
    if url == "n/a":
        return None
    if service == "rpc":
        rpc_status = fetch_json(f"{url}/status")
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
            block_data = fetch_json(f"{url}/api/v1/chain/block/latest")
        else:
            block_data = fetch_json(f"{url}/api/v1/height")
        health_data = fetch_json(f"{url}/health")
        return {
            "version": health_data.get("version", "n/a"),
            "service": service,
            "url": url,
            "latest_block_height": str(block_data.get("block_height") or block_data.get("block") or "0")
        }

# Structure output
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

for network, sources in INTERFACES.items():
    interfaces_json = fetch_url(sources["interface"], timeout=5)
    if not interfaces_json:
        continue
    try:
        interfaces = json.loads(interfaces_json)
    except:
        continue

    network_interfaces = []
    config_ref = HEALTH_CONFIG.get(network, {})

    for interface in interfaces:
        if "Namadillo" not in interface.get("Interface Name (Namadillo or Custom)", ""):
            continue
        interface_url = interface.get("Interface URL", "").rstrip('/')
        if not interface_url:
            continue

        config = parse_config(interface_url)
        settings = [get_service_data(service, url) for service, url in config.items() if url != "n/a"]
        settings = [s for s in settings if s]

        namada_version = next((s["namada_version"] for s in settings if s["service"] == "rpc"), "n/a")
        latest_block = max(
            int(s["latest_block_height"]) for s in settings
            if s.get("latest_block_height", "").isdigit()
        ) if any(s.get("latest_block_height", "").isdigit() for s in settings) else 0

        for s in settings:
            height = int(s.get("latest_block_height", 0)) if s.get("latest_block_height", "").isdigit() else 0
            service_conf = config_ref.get("services", {}).get(s["service"], {})
            s["status"] = determine_status(height, latest_block, service_conf)
            s["is_up_to_date"] = compare_versions(s.get("version", "n/a"), service_conf.get("required_version", "n/a"))

        interface_version = get_interface_version(interface_url)
        interface_required_version = config_ref.get("interface", {}).get("required_version", "n/a")

        network_interfaces.append({
            "team": interface.get("Team or Contributor Name", "Unknown"),
            "discord": interface.get("Discord UserName", "Unknown"),
            "url": interface_url,
            "version": interface_version,
            "is_up_to_date": compare_versions(interface_version, interface_required_version),
            "settings": settings
        })

    output_data["networks"].append({"network": network, "interface": network_interfaces})

output_data["script_end_time"] = datetime.now(UTC).isoformat() + "Z"

with open(OUTPUT_PATH, "w", encoding="utf-8") as json_file:
    json.dump(output_data, json_file, indent=4)
