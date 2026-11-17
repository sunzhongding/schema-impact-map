import json
from pathlib import Path

import pytest
import yaml

from schema_impact_map import cli
from schema_impact_map.build import build_from_dir
from schema_impact_map.impact import analyze_file
from schema_impact_map.report import counts, failure, summary_line, to_json, to_markdown

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "examples" / "shop"
PLAN = DATA / "plans" / "customer-key.yaml"


@pytest.fixture()
def payload():
    return analyze_file(build_from_dir(DATA), PLAN)


@pytest.fixture()
def additive_payload(tmp_path):
    plan = tmp_path / "add.yaml"
    plan.write_text(
        "name: Add refund status\nchanges:\n  add_columns:\n"
        "    - table: shop.refunds\n      column: status\n",
        encoding="utf-8",
    )
    return analyze_file(build_from_dir(DATA), plan)


def test_markdown_has_the_comment_shape(payload):
    text = to_markdown(payload, version="9.9.9")
    assert text.startswith("### Schema Impact Map · Review customer key")
    assert "**1 changed · 3 affected · 0 collisions · 2 SQL**" in text
    assert "| `crm.customers.id` | changed · analyze · breaking | plan |" in text
    assert "`shop.orders.customer_id` | affected | fk 1.00" in text
    assert "<details><summary>Affected SQL</summary>" in text
    assert "<sub>schema-impact-map 9.9.9</sub>" in text


def test_markdown_lists_collisions_and_caps_rows(payload, additive_payload):
    assert "Naming collisions" in to_markdown(additive_payload)
    capped = to_markdown(payload, limit=1)
    assert "more" in capped


def test_json_is_graph_free_and_carries_the_gate(payload):
    data = to_json(payload, version="9.9.9", fail_on="breaking")
    assert data["tool"] == {"name": "schema-impact-map", "version": "9.9.9"}
    assert data["summary"] == counts(payload) == {
        "changed": 1,
        "affected": 3,
        "collisions": 0,
        "statements": 2,
        "breaking": 1,
    }
    assert data["gate"] == {
        "fail_on": "breaking",
        "failed": True,
        "reason": "1 breaking change(s)",
    }
    assert "graph" not in data
    assert set(data["affected"][0]) == {"column", "evidence"}
    assert json.loads(json.dumps(data))  # serialisable


def test_gate_levels(payload, additive_payload):
    assert failure(payload, "none") == (False, "")
    assert failure(payload, "breaking") == (True, "1 breaking change(s)")
    assert failure(payload, "collision")[0] is True
    assert failure(payload, "affected")[0] is True

    # an add-only plan is informational unless collisions are gated
    assert failure(additive_payload, "breaking")[0] is False
    assert failure(additive_payload, "collision")[0] is True


def test_summary_line(payload):
    assert summary_line(payload) == "1 changed / 3 affected / 0 collisions / 2 SQL"


def test_cli_writes_markdown_and_reports_the_gate(tmp_path, capsys):
    target = tmp_path / "comment.md"
    code = cli.main(
        [
            "impact",
            "--data",
            str(DATA),
            "--plan",
            str(PLAN),
            "--format",
            "md",
            "--fail-on",
            "breaking",
            "--out",
            str(target),
        ]
    )
    assert code == 1
    assert target.read_text(encoding="utf-8").startswith("### Schema Impact Map")
    err = capsys.readouterr().err
    assert "fail-on breaking: 1 breaking change(s)" in err


def test_cli_markdown_goes_to_stdout(capsys):
    assert (
        cli.main(
            ["impact", "--data", str(DATA), "--plan", str(PLAN), "--format", "md"]
        )
        == 0
    )
    assert capsys.readouterr().out.startswith("### Schema Impact Map")


def test_cli_json_and_default_html_output(tmp_path, monkeypatch):
    target = tmp_path / "impact.json"
    assert (
        cli.main(
            [
                "impact",
                "--data",
                str(DATA),
                "--plan",
                str(PLAN),
                "--format",
                "json",
                "--out",
                str(target),
            ]
        )
        == 0
    )
    assert json.loads(target.read_text(encoding="utf-8"))["summary"]["affected"] == 3

    monkeypatch.chdir(tmp_path)
    assert cli.main(["impact", "--data", str(DATA), "--plan", str(PLAN)]) == 0
    assert (tmp_path / "site" / "impact.html").is_file()


def test_action_manifest_is_a_composite_action():
    manifest = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    assert manifest["runs"]["using"] == "composite"
    assert {"data", "plan"} <= set(manifest["inputs"])
    assert manifest["inputs"]["data"]["required"] is True
    step_ids = {step.get("id") for step in manifest["runs"]["steps"]}
    assert {"report", "paths"} <= step_ids
    assert manifest["outputs"]["failed"]["value"] == "${{ steps.report.outputs.failed }}"
