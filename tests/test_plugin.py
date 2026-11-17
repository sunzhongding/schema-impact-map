import json
from pathlib import Path

import yaml

from schema_impact_map import __version__

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "schema-impact-map"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_marketplace_points_at_the_plugin():
    market = load(ROOT / ".claude-plugin" / "marketplace.json")
    entry = market["plugins"][0]
    assert entry["name"] == "schema-impact-map"
    assert entry["source"] == "./plugins/schema-impact-map"
    assert (ROOT / entry["source"] / ".claude-plugin" / "plugin.json").is_file()
    assert entry["version"] == __version__


def test_plugin_manifest_matches_the_package_version():
    plugin = load(PLUGIN / ".claude-plugin" / "plugin.json")
    assert plugin["name"] == "schema-impact-map"
    assert plugin["version"] == __version__
    assert plugin["skills"] == "skills"
    assert plugin["commands"] == "commands"
    assert (PLUGIN / plugin["mcpServers"]).is_file()


def test_skill_has_trigger_frontmatter():
    text = (PLUGIN / "skills" / "schema-impact-map" / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    front, body = text[4:].split("\n---\n", 1)
    meta = yaml.safe_load(front)
    assert meta["name"] == "schema-impact-map"
    assert len(meta["description"]) > 40
    assert meta["metadata"]["version"] == __version__
    assert "## When to use" in body
    assert "read-only" in body.lower()


def test_mcp_json_declares_a_stdio_server():
    config = load(PLUGIN / ".mcp.json")
    server = config["mcpServers"]["schema-impact-map"]
    assert server["command"] == "uvx"
    assert server["args"][-1] == "mcp"
    assert any("schema-impact-map[mcp]" == arg for arg in server["args"])
