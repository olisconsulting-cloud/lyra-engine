"""Tests fuer engine/sequence_runner.py — Composable Sequences."""
from engine.sequence_runner import SequenceContext, SequenceRunner
from engine.event_bus import EventBus, Events


class TestSequenceContext:
    def test_defaults(self):
        ctx = SequenceContext(seq_num=1)
        assert ctx.seq_num == 1
        assert ctx.tool_calls == 0
        assert ctx.errors == 0
        assert ctx.files_written == 0
        assert ctx.finished is False
        assert ctx.task_type == "standard"
        assert ctx.step_budget == 40

    def test_efficiency_ratio_zero_steps(self):
        ctx = SequenceContext(seq_num=1)
        assert ctx.efficiency_ratio() == 0.0

    def test_efficiency_ratio_normal(self):
        ctx = SequenceContext(seq_num=1, files_written=3, tools_built=1, step_count=10)
        assert ctx.efficiency_ratio() == 0.4  # (3+1)/10

    def test_to_metrics_dict(self):
        ctx = SequenceContext(
            seq_num=1, tool_calls=5, errors=1, files_written=2,
            tools_built=0, step_count=8, input_tokens=5000, output_tokens=2000,
        )
        m = ctx.to_metrics_dict()
        assert m["tool_calls"] == 5
        assert m["errors"] == 1
        assert m["files_written"] == 2
        assert m["step_count"] == 8
        assert m["input_tokens"] == 5000
        assert m["efficiency_ratio"] == 0.25  # 2/8

    def test_mutable_lists(self):
        """Listen sind pro-Instanz (kein shared default)."""
        ctx1 = SequenceContext(seq_num=1)
        ctx2 = SequenceContext(seq_num=2)
        ctx1.written_paths.append("test.py")
        assert len(ctx2.written_paths) == 0


class TestSequenceRunner:
    def test_create_context(self):
        bus = EventBus()
        runner = SequenceRunner(event_bus=bus)
        ctx = runner.create_context(seq_num=42)
        assert ctx.seq_num == 42

    def test_events_emitted(self):
        bus = EventBus()
        runner = SequenceRunner(event_bus=bus)

        events_received = []
        bus.subscribe(Events.SEQUENCE_STARTED, lambda e: events_received.append(e.type))
        bus.subscribe(Events.SEQUENCE_FINISHED, lambda e: events_received.append(e.type))

        # Mock-Engine die die Phase-Methoden nicht braucht
        class MockEngine:
            sequences_total = 5
            def _build_perception(self): return "test"
            class rhythm:
                @staticmethod
                def get_mode(): return {"mode": "execution"}
            def _classify_task(self, p): return "standard"
            def _get_step_budget(self, t): return 20
            def _get_base_tiers(self, m, t): return {1}

        runner.run(MockEngine())
        assert Events.SEQUENCE_STARTED in events_received
        assert Events.SEQUENCE_FINISHED in events_received
