#!/usr/bin/env python3
"""
Home Assistant REST API client for the HA skill.
Usage: ha_client.py <command> [options]
Config stored in ~/.ha_skill_config.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

CONFIG_FILE = Path.home() / ".ha_skill_config.json"


def load_config():
    if not CONFIG_FILE.exists():
        return None
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def get_headers(config):
    return {
        "Authorization": f"Bearer {config['token']}",
        "Content-Type": "application/json",
    }


def api_get(config, path):
    try:
        import urllib.request
        url = config["url"].rstrip("/") + "/api" + path
        req = urllib.request.Request(url, headers=get_headers(config))
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


def api_post(config, path, data=None):
    try:
        import urllib.request
        url = config["url"].rstrip("/") + "/api" + path
        body = json.dumps(data or {}).encode()
        req = urllib.request.Request(url, data=body, headers=get_headers(config), method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


def cmd_status(config, args):
    if not config:
        print(json.dumps({"connected": False, "message": "Not configured. Run ha_setup.py first."}))
        return
    result = api_get(config, "/")
    if "version" in result:
        print(json.dumps({
            "connected": True,
            "url": config["url"],
            "ha_version": result.get("version"),
            "message": f"Connected to Home Assistant {result.get('version')} at {config['url']}"
        }))
    else:
        print(json.dumps({"connected": False, "error": result}))


def cmd_get_states(config, args):
    states = api_get(config, "/states")
    # Filter and summarize for readability
    if args.domain:
        states = [s for s in states if s["entity_id"].startswith(args.domain + ".")]
    if args.area:
        # Filter by area label in attributes if available
        states = [s for s in states if args.area.lower() in str(s.get("attributes", {})).lower()]

    # Summarize: entity_id, state, friendly_name, last_changed
    summary = []
    for s in states:
        summary.append({
            "entity_id": s["entity_id"],
            "state": s["state"],
            "friendly_name": s.get("attributes", {}).get("friendly_name", ""),
            "last_changed": s.get("last_changed", ""),
            "attributes": s.get("attributes", {})
        })

    print(json.dumps(summary, indent=2))


def cmd_get_entity(config, args):
    if not args.entity_id:
        print(json.dumps({"error": "entity_id required"}))
        sys.exit(1)
    state = api_get(config, f"/states/{args.entity_id}")
    print(json.dumps(state, indent=2))


def cmd_get_automations(config, args):
    states = api_get(config, "/states")
    automations = [s for s in states if s["entity_id"].startswith("automation.")]
    summary = []
    for a in automations:
        summary.append({
            "entity_id": a["entity_id"],
            "state": a["state"],  # on/off
            "friendly_name": a.get("attributes", {}).get("friendly_name", ""),
            "last_triggered": a.get("attributes", {}).get("last_triggered", "never"),
        })
    print(json.dumps(summary, indent=2))


def cmd_get_areas(config, args):
    # Use config/area_registry
    try:
        result = api_get(config, "/template")
        # Use template to get areas
    except Exception:
        pass

    # Fallback: get areas from states attributes
    states = api_get(config, "/states")
    areas = set()
    for s in states:
        area = s.get("attributes", {}).get("area_id")
        if area:
            areas.add(area)

    # Try the areas endpoint (HA 2022.4+)
    try:
        result = api_post(config, "/template", {"template": "{{ areas() | list }}"})
        if isinstance(result, str):
            # Template returned a string representation of the list
            print(json.dumps({"areas": result, "note": "area IDs from HA template engine"}))
            return
    except Exception:
        pass

    print(json.dumps({"areas": list(areas), "note": "area_ids found in entity attributes"}))


def cmd_get_devices(config, args):
    # Devices via states grouped by device_id attribute
    states = api_get(config, "/states")
    devices = {}
    for s in states:
        attrs = s.get("attributes", {})
        device_id = attrs.get("device_id")
        if device_id:
            if device_id not in devices:
                devices[device_id] = {"device_id": device_id, "entities": []}
            devices[device_id]["entities"].append(s["entity_id"])
            if not devices[device_id].get("manufacturer"):
                devices[device_id]["manufacturer"] = attrs.get("manufacturer", "")
            if not devices[device_id].get("model"):
                devices[device_id]["model"] = attrs.get("model", "")
            if not devices[device_id].get("friendly_name"):
                devices[device_id]["friendly_name"] = attrs.get("friendly_name", "")
    print(json.dumps(list(devices.values()), indent=2))


def cmd_get_services(config, args):
    services = api_get(config, "/services")
    if args.domain:
        services = [s for s in services if s.get("domain") == args.domain]
    # Summarize: domain and service names
    summary = {}
    for svc in services:
        domain = svc.get("domain", "")
        summary[domain] = list(svc.get("services", {}).keys())
    print(json.dumps(summary, indent=2))


def cmd_get_config(config, args):
    result = api_get(config, "/config")
    print(json.dumps(result, indent=2))


def cmd_call_service(config, args):
    if not args.domain or not args.service:
        print(json.dumps({"error": "--domain and --service required"}))
        sys.exit(1)
    data = {}
    if args.entity_id:
        data["entity_id"] = args.entity_id
    if args.data:
        try:
            extra = json.loads(args.data)
            data.update(extra)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"Invalid JSON in --data: {e}"}))
            sys.exit(1)
    result = api_post(config, f"/services/{args.domain}/{args.service}", data)
    print(json.dumps(result, indent=2))


def cmd_create_automation(config, args):
    """Create a new automation via HA REST API."""
    if not args.yaml_file:
        print(json.dumps({"error": "--yaml-file required. Write YAML to a temp file first."}))
        sys.exit(1)

    try:
        import yaml as pyyaml
        with open(args.yaml_file) as f:
            automation_data = pyyaml.safe_load(f)
    except ImportError:
        # Fallback: read as raw text and use the config/automations REST endpoint
        print(json.dumps({"error": "PyYAML not available. Install with: pip3 install pyyaml --break-system-packages"}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"Failed to read YAML file: {e}"}))
        sys.exit(1)

    # Use the automation REST API
    result = api_post(config, "/config/automation/config/" + (args.name or "new_automation").replace(" ", "_").lower(), automation_data)
    print(json.dumps(result, indent=2))


def cmd_get_logbook(config, args):
    """Get recent logbook entries for an entity."""
    path = "/logbook"
    if args.entity_id:
        path += f"?entity={args.entity_id}"
    result = api_get(config, path)
    # Show last N entries
    n = int(args.limit) if args.limit else 20
    print(json.dumps(result[-n:] if isinstance(result, list) else result, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Home Assistant API Client")
    parser.add_argument("command", choices=[
        "status", "get-states", "get-entity", "get-automations",
        "get-areas", "get-devices", "get-services", "get-config",
        "call-service", "create-automation", "get-logbook"
    ])

    # Shared options
    parser.add_argument("--entity-id", help="Entity ID")
    parser.add_argument("--domain", help="Domain filter (e.g. light, switch)")
    parser.add_argument("--service", help="Service name")
    parser.add_argument("--data", help="JSON data for service call")
    parser.add_argument("--area", help="Filter by area name")
    parser.add_argument("--yaml-file", help="Path to YAML file for create-automation")
    parser.add_argument("--name", help="Name for create-automation")
    parser.add_argument("--limit", help="Limit results (for get-logbook)", default="20")

    args = parser.parse_args()

    config = load_config()

    if args.command != "status" and not config:
        print(json.dumps({
            "error": "Not configured. Run ha_setup.py first.",
            "fix": "python3 ~/.claude/skills/home-assistant/scripts/ha_setup.py"
        }))
        sys.exit(1)

    commands = {
        "status": cmd_status,
        "get-states": cmd_get_states,
        "get-entity": cmd_get_entity,
        "get-automations": cmd_get_automations,
        "get-areas": cmd_get_areas,
        "get-devices": cmd_get_devices,
        "get-services": cmd_get_services,
        "get-config": cmd_get_config,
        "call-service": cmd_call_service,
        "create-automation": cmd_create_automation,
        "get-logbook": cmd_get_logbook,
    }

    commands[args.command](config, args)


if __name__ == "__main__":
    main()
