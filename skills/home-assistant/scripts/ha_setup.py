#!/usr/bin/env python3
"""
Home Assistant skill setup wizard.
Walks the user through connecting their HA instance.
Config saved to ~/.ha_skill_config.json
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

CONFIG_FILE = Path.home() / ".ha_skill_config.json"


def test_connection(url, token):
    """Test HA connection, return (success, version_or_error)."""
    try:
        req = urllib.request.Request(
            url.rstrip("/") + "/api/",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return True, data.get("version", "unknown")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "Authentication failed — token may be invalid or expired."
        return False, f"HTTP error {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"Cannot reach {url} — check the URL and that HA is running. ({e.reason})"
    except Exception as e:
        return False, str(e)


def setup():
    print("\n" + "="*60)
    print("  Home Assistant Skill Setup")
    print("="*60)

    # Check if already configured
    if CONFIG_FILE.exists():
        try:
            existing = json.loads(CONFIG_FILE.read_text())
            print(f"\nExisting config found:")
            print(f"  URL:  {existing.get('url')}")
            print(f"  Token: {'*' * 20} (hidden)")
            print()
            overwrite = input("Reconfigure? (y/N): ").strip().lower()
            if overwrite != "y":
                print("Keeping existing config.")
                # Test existing
                ok, result = test_connection(existing["url"], existing["token"])
                if ok:
                    print(f"✓ Connected to Home Assistant {result}")
                else:
                    print(f"✗ Connection failed: {result}")
                return
        except Exception:
            pass

    print("""
How to get your Home Assistant URL and token:

  1. Open Home Assistant in your browser
  2. Your URL is in the address bar (e.g. http://homeassistant.local:8123)
     Common URLs:
       • http://homeassistant.local:8123
       • http://192.168.1.x:8123
       • https://your-domain.duckdns.org

  3. For the token:
       • Click your user avatar (bottom left)
       • Go to Security tab
       • Scroll to "Long-Lived Access Tokens"
       • Click "Create Token", give it a name like "Claude Skill"
       • Copy the token (shown only once!)
""")

    # Get URL
    while True:
        url = input("Enter your Home Assistant URL: ").strip()
        if not url:
            continue
        if not url.startswith("http"):
            url = "http://" + url
        # Remove trailing slash
        url = url.rstrip("/")
        break

    # Get token
    print()
    token = input("Paste your long-lived access token: ").strip()
    if not token:
        print("Token cannot be empty.")
        sys.exit(1)

    # Test connection
    print(f"\nTesting connection to {url} ...")
    ok, result = test_connection(url, token)

    if ok:
        print(f"✓ Connected! Home Assistant version: {result}")
        # Get entity count for confirmation
        try:
            req = urllib.request.Request(
                url + "/api/states",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                states = json.loads(resp.read())
                print(f"✓ Found {len(states)} entities in your HA instance")
        except Exception:
            pass
    else:
        print(f"✗ Connection failed: {result}")
        retry = input("\nSave anyway? (y/N): ").strip().lower()
        if retry != "y":
            print("Setup cancelled.")
            sys.exit(1)

    # Save config
    config = {"url": url, "token": token}
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    CONFIG_FILE.chmod(0o600)  # Owner read/write only

    print(f"\n✓ Config saved to {CONFIG_FILE}")
    print()
    print("You're all set! Claude can now:")
    print("  • Read your entities, automations, and areas")
    print("  • Write automations using your actual entity IDs")
    print("  • Deploy automations directly to your HA instance")
    print("  • Control devices and call services")
    print()
    print("Try asking: 'What lights do I have?' or 'Write an automation to turn off all lights at midnight'")


if __name__ == "__main__":
    setup()
