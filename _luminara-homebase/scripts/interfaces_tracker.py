#!/usr/bin/env python3

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

# POSIX paths for GitHub Actions/Ubuntu
BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERFACE_STATUS_PATH = os.path.join(BASE_PATH, "interface-status.json")
STATE_PATH = os.path.join(BASE_PATH, "state.json")
CHANGES_JSON_PATH = os.path.join(BASE_PATH, "changes.json")
CHANGES_SQL_PATH = os.path.join(BASE_PATH, "changes.sql")

def load_json_file(path: str) -> dict:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_json_file(data: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def append_to_file(content: str, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(content)

def get_change_info(path_parts: List[str], current_state: dict = None) -> Tuple[Optional[str], Optional[str], str]:
    team = None
    service = None
    field = path_parts[-1]
    if path_parts[0] == "required_versions":
        service = path_parts[1] if len(path_parts) > 1 else None
        field = path_parts[-1]
    elif path_parts[0] == "networks":
        try:
            if "team" in path_parts:
                team_idx = path_parts.index("team")
                if team_idx + 1 < len(path_parts):
                    team = path_parts[team_idx + 1]
                    if "service" in path_parts[team_idx:]:
                        service_idx = path_parts.index("service", team_idx)
                        if service_idx + 1 < len(path_parts):
                            service = path_parts[service_idx + 1]
                    else:
                        service = "interface"
            if team is None and current_state and "networks" in current_state:
                for i, part in enumerate(path_parts):
                    if part == "interface" and i + 1 < len(path_parts) and path_parts[i + 1].isdigit():
                        interface_idx = int(path_parts[i + 1])
                        interface_data = current_state["networks"][0]["interface"][interface_idx]
                        team = interface_data["team"]
                        if "settings" in path_parts:
                            settings_idx = path_parts.index("settings")
                            if settings_idx + 1 < len(path_parts) and path_parts[settings_idx + 1].isdigit():
                                service_idx = int(path_parts[settings_idx + 1])
                                if service_idx < len(interface_data["settings"]):
                                    service = interface_data["settings"][service_idx]["service"]
                        else:
                            service = "interface"
        except (KeyError, IndexError, ValueError):
            pass
    return team, service, field

def build_readable_path(path_parts: List[str], operator: Optional[str], service: Optional[str]) -> str:
    if path_parts[0] == "required_versions":
        return ".".join(path_parts)
    if not operator:
        return ".".join(path_parts)
    if service == "interface":
        return f"namada.operator.{operator}.interface.{path_parts[-1]}"
    elif service:
        return f"namada.operator.{operator}.service.{service}.{path_parts[-1]}"
    else:
        return f"namada.operator.{operator}.{'.'.join(path_parts)}"

def create_change_record(path_parts: List[str], change_type: str, old_value: Any, new_value: Any, state: dict = None) -> dict:
    team, service, field = get_change_info(path_parts, state)
    full_path = build_readable_path(path_parts, team, service)
    return {
        "team": team,
        "service": service,
        "field": field,
        "full_path": full_path,
        "type": change_type,
        "old_value": old_value,
        "new_value": new_value
    }

def detect_changes(old_state: dict, new_state: dict, path: List[str] = None, root_state: dict = None) -> List[dict]:
    if path is None:
        path = []
        root_state = new_state
    changes = []
    if isinstance(new_state, dict):
        old_keys = set(old_state.keys() if isinstance(old_state, dict) else [])
        new_keys = set(new_state.keys())
        for key in new_keys - old_keys:
            current_path = path + [key]
            if (len(path) >= 2 and path[0] == "networks" and
                ((path[-1] == "interface" and isinstance(new_state[key], dict) and "team" in new_state[key]) or
                 (path[-1] == "settings" and isinstance(new_state[key], dict) and "service" in new_state[key]))):
                for field, value in new_state[key].items():
                    field_path = current_path + [field]
                    if field == "latest_block_height":
                        continue
                    changes.append(create_change_record(
                        field_path,
                        "added",
                        None,
                        value,
                        root_state
                    ))
            else:
                if key == "latest_block_height":
                    continue
                changes.append(create_change_record(
                    current_path,
                    "added",
                    None,
                    new_state[key],
                    root_state
                ))
        for key in old_keys - new_keys:
            current_path = path + [key]
            if (len(path) >= 2 and path[0] == "networks" and
                ((path[-1] == "interface" and isinstance(old_state[key], dict) and "team" in old_state[key]) or
                 (path[-1] == "settings" and isinstance(old_state[key], dict) and "service" in old_state[key]))):
                for field, value in old_state[key].items():
                    field_path = current_path + [field]
                    if field == "latest_block_height":
                        continue
                    changes.append(create_change_record(
                        field_path,
                        "removed",
                        value,
                        None,
                        root_state
                    ))
            else:
                if key == "latest_block_height":
                    continue
                changes.append(create_change_record(
                    current_path,
                    "removed",
                    old_state[key],
                    None,
                    root_state
                ))
        for key in old_keys & new_keys:
            current_path = path + [key]
            if isinstance(new_state[key], (dict, list)):
                changes.extend(detect_changes(
                    old_state.get(key, {}),
                    new_state[key],
                    current_path,
                    root_state
                ))
            elif old_state.get(key) != new_state[key]:
                if key == "latest_block_height":
                    continue
                changes.append(create_change_record(
                    current_path,
                    "modified",
                    old_state.get(key),
                    new_state[key],
                    root_state
                ))
    elif isinstance(new_state, list):
        if len(path) >= 2 and path[0] == "networks" and path[-1] == "interface":
            old_teams = {item.get("team"): item for item in old_state} if isinstance(old_state, list) else {}
            new_teams = {item.get("team"): item for item in new_state} if isinstance(new_state, list) else {}
            for team_name, team_data in old_teams.items():
                if team_name not in new_teams:
                    for field, value in team_data.items():
                        if field == "settings":
                            for service in value:
                                service_name = service.get("service")
                                for service_field, service_value in service.items():
                                    if service_field == "latest_block_height":
                                        continue
                                    field_path = path + ["team", team_name, "service", service_name, service_field]
                                    changes.append(create_change_record(
                                        field_path,
                                        "removed",
                                        service_value,
                                        None,
                                        root_state
                                    ))
                        else:
                            if field == "latest_block_height":
                                continue
                            field_path = path + ["team", team_name, field]
                            changes.append(create_change_record(
                                field_path,
                                "removed",
                                value,
                                None,
                                root_state
                            ))
            for team_name, team_data in new_teams.items():
                if team_name not in old_teams:
                    for field, value in team_data.items():
                        if field == "settings":
                            for service in value:
                                service_name = service.get("service")
                                for service_field, service_value in service.items():
                                    if service_field == "latest_block_height":
                                        continue
                                    field_path = path + ["team", team_name, "service", service_name, service_field]
                                    changes.append(create_change_record(
                                        field_path,
                                        "added",
                                        None,
                                        service_value,
                                        root_state
                                    ))
                        else:
                            if field == "latest_block_height":
                                continue
                            field_path = path + ["team", team_name, field]
                            changes.append(create_change_record(
                                field_path,
                                "added",
                                None,
                                value,
                                root_state
                            ))
            for team_name in old_teams.keys() & new_teams.keys():
                old_team = old_teams[team_name]
                new_team = new_teams[team_name]
                changes.extend(detect_changes(
                    old_team,
                    new_team,
                    path + ["team", team_name],
                    root_state
                ))
        elif len(path) >= 2 and path[0] == "networks" and path[-1] == "settings":
            old_services = {item.get("service"): item for item in old_state} if isinstance(old_state, list) else {}
            new_services = {item.get("service"): item for item in new_state} if isinstance(new_state, list) else {}
            for service_name, service_data in old_services.items():
                if service_name not in new_services:
                    for field, value in service_data.items():
                        if field == "latest_block_height":
                            continue
                        field_path = path + ["service", service_name, field]
                        changes.append(create_change_record(
                            field_path,
                            "removed",
                            value,
                            None,
                            root_state
                        ))
            for service_name, service_data in new_services.items():
                if service_name not in old_services:
                    for field, value in service_data.items():
                        if field == "latest_block_height":
                            continue
                        field_path = path + ["service", service_name, field]
                        changes.append(create_change_record(
                            field_path,
                            "added",
                            None,
                            value,
                            root_state
                        ))
            for service_name in old_services.keys() & new_services.keys():
                old_service = old_services[service_name]
                new_service = new_services[service_name]
                sync_state_changed = old_service.get("sync_state") != new_service.get("sync_state")
                for field in set(old_service.keys()) | set(new_service.keys()):
                    old_value = old_service.get(field)
                    new_value = new_service.get(field)
                    if old_value != new_value:
                        if field == "latest_block_height" and not sync_state_changed:
                            continue  # Only log block height if sync_state also changed
                        field_path = path + ["service", service_name, field]
                        changes.append(create_change_record(
                            field_path,
                            "modified",
                            old_value,
                            new_value,
                            root_state
                        ))
        else:
            old_list = old_state if isinstance(old_state, list) else []
            for i, new_item in enumerate(new_state):
                old_item = old_list[i] if i < len(old_list) else {}
                changes.extend(detect_changes(
                    old_item,
                    new_item,
                    path + [str(i)],
                    root_state
                ))
            if isinstance(old_state, list):
                for i in range(len(new_state), len(old_state)):
                    current_path = path + [str(i)]
                    changes.append(create_change_record(
                        current_path,
                        "removed",
                        old_state[i],
                        None,
                        root_state
                    ))
    return changes

def generate_sql_statement(change: dict, timestamp: str) -> str:
    team_value = "'{}'".format(change['team']) if change['team'] else 'null'
    service_value = "'{}'".format(change['service']) if change['service'] else 'null'
    return (
        "INSERT INTO interface_changes "
        "(timestamp, team, service, field, full_path, change_type, old_value, new_value) "
        "VALUES ('{}', {}, {}, '{}', '{}', '{}', '{}', '{}');\n"
    ).format(
        timestamp,
        team_value,
        service_value,
        change['field'],
        change['full_path'],
        change['type'],
        json.dumps(change['old_value']),
        json.dumps(change['new_value'])
    )

def main():
    print("Starting interface tracker...")
    print("Reading from: {}".format(INTERFACE_STATUS_PATH))
    timestamp = datetime.now(timezone.utc).isoformat() + "Z"
    current_state = load_json_file(INTERFACE_STATUS_PATH)
    if not current_state:
        print("Error: Could not load interface status")
        return
    previous_state = load_json_file(STATE_PATH)
    is_initial = not previous_state
    if is_initial:
        print("Initial run detected - recording complete state")
        changes = [{
            "timestamp": timestamp,
            "type": "initial",
            "state": current_state
        }]
    else:
        detected_changes = detect_changes(previous_state, current_state)
        if detected_changes:
            changes = [{
                "timestamp": timestamp,
                "changes": detected_changes
            }]
        else:
            changes = []
    if changes:
        existing_changes = load_json_file(CHANGES_JSON_PATH)
        if not isinstance(existing_changes, list):
            existing_changes = []
        existing_changes.extend(changes)
        save_json_file(existing_changes, CHANGES_JSON_PATH)
        print("Updated {}".format(CHANGES_JSON_PATH))
        sql_statements = []
        if is_initial:
            sql_statements.append(
                "INSERT INTO interface_changes "
                "(timestamp, team, service, field, full_path, change_type, old_value, new_value) "
                "VALUES ('{}', null, null, 'root', 'root', 'initial', 'null', '{}');\n".format(
                    timestamp,
                    json.dumps(current_state)
                )
            )
        else:
            for change in detected_changes:
                sql_statements.append(generate_sql_statement(change, timestamp))
        append_to_file("".join(sql_statements), CHANGES_SQL_PATH)
        print("Updated {}".format(CHANGES_SQL_PATH))
        change_count = len(detected_changes) if not is_initial else 1
        print("Recorded {} changes at {}".format(change_count, timestamp))
    else:
        print("No changes detected at {}".format(timestamp))
    save_json_file(current_state, STATE_PATH)
    print("Updated {}".format(STATE_PATH))
    print("Done!")

if __name__ == "__main__":
    main()
