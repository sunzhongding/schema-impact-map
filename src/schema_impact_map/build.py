from __future__ import annotations

from pathlib import Path

from .io import DataError, load_json, load_yaml
from .sql import parse_sql_files

CONFIG_FILE = "schema-impact-map.yaml"


def _column_id(qualified: str) -> str:
    return f"column:{qualified}"


def _table_id(qualified: str) -> str:
    return f"table:{qualified}"


def _database_id(name: str) -> str:
    return f"database:{name}"


def _edge_priority(kind: str) -> int:
    return {"fk": 3, "value_overlap": 2, "join": 1}.get(kind, 0)


class Builder:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.config = load_yaml(data_dir / CONFIG_FILE)
        self.schema = load_json(data_dir / self.config.get("schema", "schema.json"))
        self.entities_cfg = load_yaml(data_dir / self.config.get("entities", "entities.yaml"))
        self.rules = load_yaml(data_dir / self.config.get("rules", "rules.yaml"))
        self.dialect = self.config.get("dialect", "mysql")
        self.default_database = self.config.get(
            "default_database",
            self.schema["databases"][0]["name"],
        )
        self.tables: dict[str, dict] = {}
        self.columns: dict[str, dict] = {}
        self.databases: dict[str, dict] = {}
        self.errors: list[str] = []

    # ---------------------------------------------------------------- load

    def load_schema(self) -> None:
        for database in self.schema.get("databases", []):
            db_name = database["name"]
            self.databases[db_name] = {
                "id": _database_id(db_name),
                "kind": "database",
                "name": db_name,
                "comment": database.get("comment", ""),
            }
            for table in database.get("tables", []):
                qualified = f"{db_name}.{table['name']}"
                columns = []
                for raw in table.get("columns", []):
                    column = {
                        "id": _column_id(f"{qualified}.{raw['name']}"),
                        "kind": "column",
                        "name": raw["name"],
                        "qualified": f"{qualified}.{raw['name']}",
                        "table": qualified,
                        "database": db_name,
                        "type": raw.get("type", ""),
                        "pk": bool(raw.get("pk", False)),
                        "unique": bool(raw.get("unique", False)),
                        "comment": raw.get("comment", ""),
                    }
                    columns.append(column)
                    self.columns[column["qualified"]] = column
                table_entry = {
                    "id": _table_id(qualified),
                    "kind": "table",
                    "name": table["name"],
                    "qualified": qualified,
                    "database": db_name,
                    "comment": table.get("comment", ""),
                    "rows": table.get("rows", 0),
                    "columns": columns,
                }
                self.tables[qualified] = table_entry
                self.databases[db_name].setdefault("tables", []).append(table_entry["id"])

    # ---------------------------------------------------------------- edges

    def _is_key(self, qualified: str) -> bool:
        column = self.columns.get(qualified)
        if not column:
            return False
        # only a single-column PK / single-column UNIQUE key is a parent key;
        # one column of a composite key is not
        table = self.tables.get(column["table"], {})
        if column["pk"] and sum(1 for c in table.get("columns", []) if c["pk"]) == 1:
            return True
        return column["unique"]

    def _orient(self, left: str, right: str) -> tuple[str, str]:
        """Return ``(child, parent)``."""
        left_key, right_key = self._is_key(left), self._is_key(right)
        if right_key and not left_key:
            return left, right
        if left_key and not right_key:
            return right, left
        left_name = left.rsplit(".", 1)[-1]
        right_name = right.rsplit(".", 1)[-1]
        if left_name == "id" and right_name != "id":
            return right, left
        if right_name == "id" and left_name != "id":
            return left, right
        return left, right

    def _add_relation(self, relations: dict, child: str, parent: str, kind: str,
                      confidence: float, method: str, evidence: dict | None) -> None:
        for qualified in (child, parent):
            if qualified not in self.columns:
                self.errors.append(f"relation references unknown column: {qualified}")
                return
        key = (child, parent)
        existing = relations.get(key)
        incoming = {
            "child": child,
            "parent": parent,
            "kind": kind,
            "confidence": confidence,
            "method": method,
            "evidence": evidence,
        }
        if not existing:
            relations[key] = incoming
            return
        # keep the strongest evidence per child->parent and merge the methods
        if _edge_priority(kind) > _edge_priority(existing["kind"]):
            existing.update(incoming)
        elif kind == "fk" and "sql_join" not in existing["method"]:
            existing["method"] = f"{existing['method']}+sql_join"
            existing["confidence"] = 1.0
        elif kind == "join" and existing["kind"] == "fk":
            existing["confidence"] = 1.0
            if "sql_join" not in existing["method"]:
                existing["method"] = f"{existing['method']}+sql_join"
        evidence = existing.get("evidence")
        if evidence and isinstance(evidence, list):
            if incoming["evidence"] and incoming["evidence"] not in evidence:
                evidence.append(incoming["evidence"])
        elif evidence and incoming["evidence"]:
            existing["evidence"] = [evidence, incoming["evidence"]]
        elif incoming["evidence"]:
            existing["evidence"] = incoming["evidence"]

    def build_relations(self, statements: list[dict]) -> list[dict]:
        relations: dict[tuple[str, str], dict] = {}

        for raw in self.schema.get("relations", []):
            self._add_relation(
                relations,
                raw["child"],
                raw["parent"],
                kind="fk" if raw.get("method") == "ddl_fk" else raw.get("kind", "value_overlap"),
                confidence=float(raw.get("confidence", 1.0)),
                method=raw.get("method", "declared"),
                evidence={"file": "schema.json", "snippet": raw.get("note", "")},
            )

        for statement in statements:
            for join in statement.get("joins", []):
                child, parent = self._orient(join["left"], join["right"])
                self._add_relation(
                    relations,
                    child,
                    parent,
                    kind="join",
                    confidence=0.9,
                    method="sql_join",
                    evidence={"file": statement["file"], "snippet": join["snippet"]},
                )

        edges = []
        for relation in relations.values():
            edges.append(
                {
                    "src": _column_id(relation["child"]),
                    "dst": _column_id(relation["parent"]),
                    "kind": relation["kind"],
                    "confidence": relation["confidence"],
                    "method": relation["method"],
                    "evidence": relation["evidence"],
                }
            )
        return edges

    # ---------------------------------------------------------------- entities

    def build_entities(self) -> tuple[list[dict], list[dict]]:
        entities: list[dict] = []
        edges: list[dict] = []
        for name, spec in (self.entities_cfg.get("entities") or {}).items():
            canonical = spec.get("canonical")
            aliases = spec.get("aliases") or []
            keys = spec.get("alternate_keys") or []
            members = []
            for column, role in [
                (canonical, "canonical"),
                *[(item, "alias") for item in aliases],
                *[(item, "key") for item in keys],
            ]:
                if not column:
                    continue
                if column not in self.columns:
                    self.errors.append(f"entity {name} references unknown column: {column}")
                    continue
                members.append({"column": column, "role": role})
                edges.append(
                    {
                        "src": _column_id(column),
                        "dst": f"entity:{name}",
                        "kind": "same_entity",
                        "confidence": 1.0,
                        "method": "human",
                        "evidence": {"file": "entities.yaml", "snippet": f"{role}: {column}"},
                    }
                )
                edges.append(
                    {
                        "src": f"entity:{name}",
                        "dst": _column_id(column),
                        "kind": "represents",
                        "confidence": 1.0,
                        "method": "human",
                        "evidence": {"file": "entities.yaml", "snippet": f"{role}: {column}"},
                    }
                )
            entities.append(
                {
                    "id": f"entity:{name}",
                    "kind": "entity",
                    "name": name,
                    "title": spec.get("title", name),
                    "canonical": canonical,
                    "members": members,
                }
            )
        return entities, edges

    # ---------------------------------------------------------------- check

    def check(self, tables: list[dict], entities: list[dict], edges: list[dict]) -> dict:
        errors = list(self.errors)
        warnings: list[str] = []
        members = {
            member["column"]
            for entity in entities
            for member in entity.get("members", [])
        }
        related = set()
        for edge in edges:
            if edge["kind"] in {"fk", "join", "value_overlap"}:
                related.add(edge["src"].split(":", 1)[-1])
                related.add(edge["dst"].split(":", 1)[-1])

        ignored = set((self.rules.get("ignore_columns") or {}).keys())
        patterns = self.rules.get("relation_patterns") or ["*_id"]
        orphans = []
        for table in tables:
            for column in table["columns"]:
                if not any(
                    column["name"].endswith(pattern.lstrip("*")) if pattern.startswith("*")
                    else column["name"] == pattern
                    for pattern in patterns
                ):
                    continue
                if column["name"] in ignored:
                    continue
                if column["qualified"] in members or column["qualified"] in related:
                    continue
                orphans.append(column["qualified"])

        for qualified in orphans:
            errors.append(f"unresolved relation column: {qualified}")

        return {
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
            "orphans": orphans,
        }

    # ---------------------------------------------------------------- build

    def build(self) -> dict:
        self.load_schema()
        sql_dir = self.data_dir / self.config.get("sql", "sql")
        statements = parse_sql_files(
            sql_dir,
            self.dialect,
            self.tables,
            self.default_database,
        )
        relation_edges = self.build_relations(statements)
        entities, entity_edges = self.build_entities()
        edges = relation_edges + entity_edges

        # node list: database / table / column / entity
        tables = sorted(self.tables.values(), key=lambda table: table["qualified"])
        columns = sorted(self.columns.values(), key=lambda column: column["qualified"])
        check = self.check(tables, entities, edges)
        graph = {
            "version": 1,
            "name": self.config.get("name", self.data_dir.name),
            "instance": self.schema.get("instance", "demo"),
            "databases": sorted(self.databases.values(), key=lambda item: item["name"]),
            "tables": [
                {
                    **table,
                    "columns": sorted(table["columns"], key=lambda c: c["name"]),
                }
                for table in tables
            ],
            "columns": columns,
            "entities": entities,
            "edges": edges,
            "statements": statements,
            "check": check,
            "stats": {
                "databases": len(self.databases),
                "tables": len(tables),
                "columns": len(columns),
                "edges": len(edges),
                "statements": len(statements),
                "entities": len(entities),
            },
        }
        return graph


def build_from_dir(data_dir: Path) -> dict:
    if not data_dir.exists():
        raise DataError(f"data directory not found: {data_dir}")
    return Builder(data_dir).build()
