"""Tests fuer engine/tool_registry.py — Zentrale Tool-Verwaltung."""
import pytest
from engine.event_bus import EventBus, Events
from engine.tool_registry import ToolRegistry, ToolDefinition, ToolResult


def _make_schema(required: list[str] = None, **props) -> dict:
    """Hilfs-Funktion: Erstellt ein einfaches JSON-Schema."""
    schema = {
        "type": "object",
        "properties": {k: {"type": v, "description": f"{k} param"} for k, v in props.items()},
    }
    if required:
        schema["required"] = required
    return schema


class TestRegistration:
    """Tool-Registrierung."""

    def test_register_tool(self):
        reg = ToolRegistry()
        td = ToolDefinition(
            name="write_file",
            description="Schreibt eine Datei",
            input_schema=_make_schema(path="string", content="string", required=["path", "content"]),
            handler=lambda inp: f"OK: {inp['path']}",
            tier=1,
            required_fields=["path", "content"],
        )
        reg.register(td)
        assert reg.has_tool("write_file")
        assert reg.tool_count() == 1

    def test_register_from_api_def(self):
        """Registrierung aus bestehender TOOLS-Liste."""
        reg = ToolRegistry()
        api_def = {
            "name": "read_file",
            "description": "Liest eine Datei",
            "input_schema": _make_schema(path="string", required=["path"]),
        }
        reg.register_from_api_def(api_def, tier=1, required_fields=["path"])
        assert reg.has_tool("read_file")
        assert reg.get_tier("read_file") == 1
        assert reg.get_required_fields("read_file") == ["path"]

    def test_overwrite_tool(self):
        """Erneute Registrierung ueberschreibt."""
        reg = ToolRegistry()
        td1 = ToolDefinition(name="x", description="v1", input_schema={}, tier=1)
        td2 = ToolDefinition(name="x", description="v2", input_schema={}, tier=2)
        reg.register(td1)
        reg.register(td2)
        assert reg.get_tier("x") == 2

    def test_set_handler(self):
        """Handler nachtraeglich setzen."""
        reg = ToolRegistry()
        td = ToolDefinition(name="x", description="test", input_schema={})
        reg.register(td)
        reg.set_handler("x", lambda inp: "OK")
        result = reg.execute("x", {})
        assert result.success

    def test_set_handler_unknown_tool(self):
        """Handler fuer unbekanntes Tool wirft KeyError."""
        reg = ToolRegistry()
        with pytest.raises(KeyError):
            reg.set_handler("unknown", lambda inp: "OK")


class TestSchemaGeneration:
    """API-Schema Generierung."""

    def test_get_full_schemas(self):
        """Volle Schemas mit Descriptions."""
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            name="write_file", description="Schreibt eine Datei",
            input_schema=_make_schema(path="string"), tier=1,
        ))
        reg.register(ToolDefinition(
            name="web_search", description="Web-Suche",
            input_schema=_make_schema(query="string"), tier=4,
        ))

        # Nur Tier 1
        schemas = reg.get_api_schemas({1}, compact=False)
        assert len(schemas) == 1
        assert schemas[0]["name"] == "write_file"
        assert schemas[0]["description"] == "Schreibt eine Datei"

    def test_get_compact_schemas(self):
        """Kompakte Schemas ohne Property-Descriptions."""
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            name="write_file", description="Schreibt eine Datei",
            input_schema=_make_schema(path="string", content="string", required=["path"]),
            tier=1,
        ))

        schemas = reg.get_api_schemas({1}, compact=True)
        assert len(schemas) == 1
        schema = schemas[0]
        assert schema["description"] == "write file"  # name.replace("_", " ")
        # Properties haben keine description mehr
        props = schema["input_schema"]["properties"]
        assert "description" not in props["path"]
        assert props["path"] == {"type": "string"}
        # Required bleibt erhalten
        assert schema["input_schema"]["required"] == ["path"]

    def test_multi_tier_selection(self):
        """Mehrere Tiers gleichzeitig."""
        reg = ToolRegistry()
        reg.register(ToolDefinition(name="a", description="", input_schema={}, tier=1))
        reg.register(ToolDefinition(name="b", description="", input_schema={}, tier=2))
        reg.register(ToolDefinition(name="c", description="", input_schema={}, tier=3))
        reg.register(ToolDefinition(name="d", description="", input_schema={}, tier=4))

        schemas = reg.get_api_schemas({1, 2})
        names = [s["name"] for s in schemas]
        assert "a" in names
        assert "b" in names
        assert "c" not in names


class TestExecution:
    """Tool-Ausfuehrung."""

    def test_execute_success(self):
        """Erfolgreiche Ausfuehrung."""
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            name="read_file", description="", input_schema={},
            handler=lambda inp: f"Inhalt von {inp['path']}",
        ))
        result = reg.execute("read_file", {"path": "test.py"})
        assert result.success
        assert "test.py" in result.output

    def test_execute_failure(self):
        """Handler gibt FEHLER zurueck."""
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            name="read_file", description="", input_schema={},
            handler=lambda inp: "FEHLER: Datei nicht gefunden",
        ))
        result = reg.execute("read_file", {"path": "x"})
        assert not result.success
        assert "FEHLER" in result.output

    def test_execute_unknown_tool(self):
        """Unbekanntes Tool gibt Fehler zurueck."""
        reg = ToolRegistry()
        result = reg.execute("unknown_tool", {})
        assert not result.success
        assert "Unbekanntes Tool" in result.output

    def test_execute_no_handler(self):
        """Tool ohne Handler gibt Fehler zurueck."""
        reg = ToolRegistry()
        reg.register(ToolDefinition(name="x", description="", input_schema={}))
        result = reg.execute("x", {})
        assert not result.success
        assert "Kein Handler" in result.output

    def test_execute_missing_required_fields(self):
        """Fehlende Pflichtfelder werden erkannt."""
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            name="write_file", description="", input_schema={},
            handler=lambda inp: "OK",
            required_fields=["path", "content"],
        ))
        result = reg.execute("write_file", {"path": "test.py"})
        assert not result.success
        assert "content" in result.output

    def test_execute_handler_exception(self):
        """Handler-Exception wird gefangen."""
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            name="crash", description="", input_schema={},
            handler=lambda inp: (_ for _ in ()).throw(RuntimeError("Boom")),
        ))
        result = reg.execute("crash", {})
        assert not result.success
        assert "FEHLER" in result.output


class TestHooks:
    """Pre/Post-Hooks."""

    def test_global_pre_hook(self):
        """Pre-Hook wird vor Handler aufgerufen."""
        reg = ToolRegistry()
        calls = []
        reg.add_global_pre_hook(lambda name, inp: calls.append(("pre", name)))
        reg.register(ToolDefinition(
            name="x", description="", input_schema={},
            handler=lambda inp: (calls.append(("handler",)), "OK")[-1],
        ))
        reg.execute("x", {})
        assert calls == [("pre", "x"), ("handler",)]

    def test_global_post_hook(self):
        """Post-Hook wird nach Handler aufgerufen."""
        reg = ToolRegistry()
        results = []
        reg.add_global_post_hook(
            lambda name, inp, res: results.append((name, res.success))
        )
        reg.register(ToolDefinition(
            name="x", description="", input_schema={},
            handler=lambda inp: "OK",
        ))
        reg.execute("x", {})
        assert results == [("x", True)]

    def test_pre_hook_error_does_not_block(self):
        """Fehlerhafter Pre-Hook blockiert nicht die Ausfuehrung."""
        reg = ToolRegistry()
        reg.add_global_pre_hook(lambda name, inp: (_ for _ in ()).throw(ValueError("!")))
        reg.register(ToolDefinition(
            name="x", description="", input_schema={},
            handler=lambda inp: "OK",
        ))
        result = reg.execute("x", {})
        assert result.success  # Handler laeuft trotzdem

    def test_post_hook_error_does_not_break_result(self):
        """Fehlerhafter Post-Hook aendert das Ergebnis nicht."""
        reg = ToolRegistry()
        reg.add_global_post_hook(lambda n, i, r: (_ for _ in ()).throw(ValueError("!")))
        reg.register(ToolDefinition(
            name="x", description="", input_schema={},
            handler=lambda inp: "OK",
        ))
        result = reg.execute("x", {})
        assert result.success


class TestQueries:
    """Abfrage-Methoden."""

    def test_tier_counts(self):
        """Tier-Statistiken."""
        reg = ToolRegistry()
        reg.register(ToolDefinition(name="a", description="", input_schema={}, tier=1))
        reg.register(ToolDefinition(name="b", description="", input_schema={}, tier=1))
        reg.register(ToolDefinition(name="c", description="", input_schema={}, tier=3))

        counts = reg.tier_counts()
        assert counts[1] == 2
        assert counts[3] == 1
        assert 2 not in counts

    def test_needs_approval(self):
        """Genehmigungspflicht abfragen."""
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            name="pip_install", description="", input_schema={},
            requires_approval=True,
        ))
        reg.register(ToolDefinition(name="read_file", description="", input_schema={}))

        assert reg.needs_approval("pip_install") is True
        assert reg.needs_approval("read_file") is False
        assert reg.needs_approval("unknown") is False

    def test_get_tool_names(self):
        """Alle Tool-Namen abrufen."""
        reg = ToolRegistry()
        reg.register(ToolDefinition(name="a", description="", input_schema={}))
        reg.register(ToolDefinition(name="b", description="", input_schema={}))
        assert sorted(reg.get_tool_names()) == ["a", "b"]
