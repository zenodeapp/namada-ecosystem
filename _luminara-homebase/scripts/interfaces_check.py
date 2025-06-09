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
ENABLE_HOUSEFIRE = True

# Paths
BASE_PATH = "_luminara-homebase"
CONFIG_PATH = os.path.join(BASE_PATH, "services_health_config.json")
OUTPUT_PATH = os.path.join(BASE_PATH, "interface-status.json")

# Load configuration
try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        HEALTH_CONFIG = json.load(f)
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"Error loading configuration: {e}")
    HEALTH_CONFIG = {}

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
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), context=SSL_CONTEXT, timeout=timeout) as response:
                return response.read().decode('utf-8')
        except Exception as e:
            if attempt == retries - 1:
                print(f"Error fetching {url}: {e}")
            time.sleep(2)
    return None

def fetch_url_bytes(url, retries=3, timeout=5):
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), context=SSL_CONTEXT, timeout=timeout) as response:
                return response.read()
        except Exception as e:
            if attempt == retries - 1:
                print(f"Error fetching bytes from {url}: {e}")
            time.sleep(2)
    return None

def fetch_json(url):
    data = fetch_url(url)
    try:
        return json.loads(data) if data else {}
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from {url}: {e}")
        return {}

def get_interface_version(url):
    if not (r := fetch_url(url)):
        return "n/a"
    try:
        soup = BeautifulSoup(r, "html.parser")
        script = soup.find("script", {"type": "module", "crossorigin": True})
        if script and "src" in script.attrs:
            js_url = f"{url.rstrip('/')}/{script['src'].lstrip('/')}"
            js_content = fetch_url(js_url)
            if js_content and (match := re.search(r'version\$1\s*=\s*"([^"]+)"', js_content)):
                return match.group(1)
    except Exception as e:
        print(f"Error getting interface version from {url}: {e}")
    return "n/a"

def parse_config(url):
    data = fetch_url_bytes(f"{url}/config.toml", timeout=5)
    if not data:
        return {"rpc": "n/a", "indexer": "n/a", "masp": "n/a"}
    try:
        config = tomllib.loads(data.decode("utf-8"))
        return {
            "rpc": config.get("rpc_url", "n/a"),
            "indexer": config.get("indexer_url", "n/a"),
            "masp": config.get("masp_indexer_url", "n/a")
        }
    except tomllib.TOMLDecodeError as e:
        print(f"Error parsing TOML from {url}: {e}")
        return {"rpc": "n/a", "indexer": "n/a", "masp": "n/a"}

def extract_moniker_version(moniker):
    if not moniker:
        return "n/a"
    match = re.search(r"[-_]v(\d+\.\d+\.\d+)", moniker)
    return match.group(1) if match else "n/a"

def version_tuple(v):
    main, *rest = v.split('-', 1)
    nums = tuple(map(int, main.split('.')))
    suffix = rest[0] if rest else ''
    return nums, suffix

def compare_versions(current, required):
    if current == "n/a" or required == "n/a":
        return False
    c_nums, c_suf = version_tuple(current)
    r_nums, r_suf = version_tuple(required)
    return c_nums == r_nums and c_suf == r_suf

def determine_sync_state(block_height, reference_block, service_conf):
    if not service_conf or reference_block == 0 or block_height == 0:
        return "sync_nok"
    thresholds = service_conf.get("block_lag_thresholds", {})
    if not isinstance(thresholds, dict) or "healthy" not in thresholds or "max" not in thresholds:
        return "sync_nok"
    try:
        healthy = int(thresholds["healthy"])
        max_lag = int(thresholds["max"])
        lag = reference_block - block_height
        if lag <= healthy:
            return "sync_ok"
        elif lag <= max_lag:
            return "sync_lag"
        return "sync_nok"
    except (ValueError, TypeError):
        return "sync_nok"

def get_service_data(service, url):
    if not url or url == "n/a":
        return None
        
    if service == "rpc":
        rpc_status = fetch_json(f"{url}/status")
        if not rpc_status or "result" not in rpc_status:
            return {
                "service": service,
                "url": url,
                "status": "down",
                "version": "n/a",
                "is_up_to_date": False,
                "namada_version": "n/a",
                "latest_block_height": "0"
            }
            
        sync_info = rpc_status.get("result", {}).get("sync_info", {})
        node_info = rpc_status.get("result", {}).get("node_info", {})
        service_data = {
            "service": service,
            "url": url,
            "status": "up",
            "version": node_info.get("version", "n/a"),
            "is_up_to_date": False,
            "namada_version": extract_moniker_version(node_info.get("moniker", "")),
            "latest_block_height": str(sync_info.get("latest_block_height", "0"))
        }
    else:
        if "indexer" in service:
            block_data = fetch_json(f"{url}/api/v1/chain/block/latest")
        else:
            block_data = fetch_json(f"{url}/api/v1/height")
            
        health_data = fetch_json(f"{url}/health")
        
        if not block_data or not health_data:
            return {
                "service": service,
                "url": url,
                "status": "down",
                "version": "n/a",
                "is_up_to_date": False,
                "latest_block_height": "0"
            }
            
        service_data = {
            "service": service,
            "url": url,
            "status": "up",
            "version": health_data.get("version", "n/a"),
            "is_up_to_date": False,
            "latest_block_height": str(block_data.get("block_height") or block_data.get("block") or "0")
        }
    
    return service_data

# --- First pass: collect all data and block heights ---
network_block_heights = {}
network_data = {}

for network, sources in INTERFACES.items():
    interfaces_json = fetch_url(sources["interface"], timeout=5)
    if not interfaces_json:
        continue
    try:
        interfaces = json.loads(interfaces_json)
    except json.JSONDecodeError:
        print(f"Error parsing interfaces JSON for network {network}")
        continue
    network_interfaces = []
    config_ref = HEALTH_CONFIG.get(network, {})
    block_heights = []
    for interface in interfaces:
        if "Namadillo" not in interface.get("Interface Name (Namadillo or Custom)", ""):
            continue
        interface_url = interface.get("Interface URL", "").rstrip('/')
        if not interface_url:
            continue
        config = parse_config(interface_url)
        settings = [get_service_data(service, url) for service, url in config.items() if url != "n/a"]
        settings = [s for s in settings if s]
        # Collect block heights
        for s in settings:
            try:
                height = int(s.get("latest_block_height", 0))
                if height > 0:
                    block_heights.append(height)
            except Exception:
                pass
        interface_version = get_interface_version(interface_url)
        # Use the correct required version for each network
        interface_required_version = config_ref.get("interface", {}).get("required_version", "n/a")
        interface_entry = {
            "team": interface.get("Team or Contributor Name", "Unknown"),
            "discord": interface.get("Discord UserName", "Unknown"),
            "url": interface_url,
            "status": "up" if interface_version != "n/a" else "down",
            "version": interface_version,
            "is_up_to_date": compare_versions(interface_version, interface_required_version),
            "settings": settings
        }
        network_interfaces.append(interface_entry)
    network_data[network] = network_interfaces
    network_block_heights[network] = max(block_heights) if block_heights else 0

# --- Calculate reference_latest_block_height for each network ---
reference_latest_block_height = network_block_heights.get("namada", 0)
housefire_reference_latest_block_height = network_block_heights.get("housefire", 0)

# --- Second pass: assign sync_state and is_up_to_date using the correct reference height ---
output_data = {
    "script_start_time": START_TIME,
    "script_end_time": "",
    "reference_latest_block_height": str(reference_latest_block_height),
    "housefire_reference_latest_block_height": str(housefire_reference_latest_block_height),
    "required_versions": {
        "interface": HEALTH_CONFIG.get("namada", {}).get("interface", {}).get("required_version", "n/a"),
        "indexer": HEALTH_CONFIG.get("namada", {}).get("services", {}).get("indexer", {}).get("required_version", "n/a"),
        "rpc": HEALTH_CONFIG.get("namada", {}).get("services", {}).get("rpc", {}).get("required_version", "n/a"),
        "masp": HEALTH_CONFIG.get("namada", {}).get("services", {}).get("masp", {}).get("required_version", "n/a")
    },
    "housefire_required_versions": {
        "interface": HEALTH_CONFIG.get("housefire", {}).get("interface", {}).get("required_version", "n/a"),
        "indexer": HEALTH_CONFIG.get("housefire", {}).get("services", {}).get("indexer", {}).get("required_version", "n/a"),
        "rpc": HEALTH_CONFIG.get("housefire", {}).get("services", {}).get("rpc", {}).get("required_version", "n/a"),
        "masp": HEALTH_CONFIG.get("housefire", {}).get("services", {}).get("masp", {}).get("required_version", "n/a")
    },
    "networks": []
}

for network, interfaces in network_data.items():
    config_ref = HEALTH_CONFIG.get(network, {})
    ref_block = network_block_heights.get(network, 0)
    for interface in interfaces:
        for s in interface["settings"]:
            try:
                height = int(s.get("latest_block_height", 0))
            except Exception:
                height = 0
            # Use the correct required version for each network/service
            service_conf = config_ref.get("services", {}).get(s["service"], {})
            s["sync_state"] = determine_sync_state(height, ref_block, service_conf)
            s["is_up_to_date"] = compare_versions(s.get("version", "n/a"), service_conf.get("required_version", "n/a"))
        interface["settings"] = sorted(interface["settings"], key=lambda x: x["service"])
    output_data["networks"].append({"network": network, "interface": interfaces})

output_data["script_end_time"] = datetime.now(UTC).isoformat() + "Z"

try:
    with open(OUTPUT_PATH, "w", encoding="utf-8") as json_file:
        json.dump(output_data, json_file, indent=4, sort_keys=False)
except Exception as e:
    print(f"Error writing output file: {e}")
