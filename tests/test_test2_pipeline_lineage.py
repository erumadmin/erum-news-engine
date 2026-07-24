"""Prove Test2 editorial modules remain the core path (not keyword-gate substitutes)."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_engine_imports_test2_pipeline_modules():
    engine_src = (ROOT / "engine.py").read_text(encoding="utf-8")
    required = [
        "engine.pipeline.source_gate",
        "engine.pipeline.packet_writer",
        "engine.pipeline.rewrite_validate",
        "engine.pipeline.publish_body",
        "engine.pipeline.editorial_stages",
        "engine.pipeline.nn_packet_writer",
        "engine.pipeline.cb_packet_writer",
        "run_editorial_stages",
        "prepare_ij_publish_body",
        "prepare_nn_publish_body",
        "prepare_cb_publish_body",
        "validate_source_fidelity",
    ]
    for needle in required:
        assert needle in engine_src, f"missing Test2 core reference: {needle}"


def test_engine_does_not_replace_core_with_keyword_only_path():
    engine_src = (ROOT / "engine.py").read_text(encoding="utf-8")
    # body_quality is supplemental AFTER publish_body, not a substitute.
    assert "prepare_ij_publish_body" in engine_src
    assert "evaluate_reader_body" in engine_src
    ij_pos = engine_src.find("prepare_ij_publish_body")
    body_pos = engine_src.find("evaluate_reader_body")
    assert ij_pos > 0 and body_pos > ij_pos


def test_w8_ops_modules_present():
    for rel in [
        "erum_pipeline/publish_limits.py",
        "erum_pipeline/w8_runner_env.py",
        "erum_pipeline/staging_guards.py",
        "erum_pipeline/reporter_roster.py",
        "scripts/w8_run_engine.py",
        "scripts/w8-cron-runner.sh",
    ]:
        assert (ROOT / rel).is_file(), rel
