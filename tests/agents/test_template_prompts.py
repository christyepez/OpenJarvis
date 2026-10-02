"""Tests for system_prompt_template expansion in agent creation."""

from __future__ import annotations

from openjarvis.agents.manager import AgentManager


def test_create_from_template_expands_system_prompt(tmp_path):
    """system_prompt_template should be expanded with the instruction."""
    mgr = AgentManager(db_path=str(tmp_path / "test.db"))
    agent = mgr.create_from_template(
        "research_monitor",
        "Test Agent",
        overrides={"instruction": "Monitor AI safety papers"},
    )
    config = agent["config"]
    # system_prompt should contain the expanded instruction
    assert "Monitor AI safety papers" in config.get("system_prompt", "")
    # system_prompt_template should NOT be in the stored config
    assert "system_prompt_template" not in config
    mgr.close()


def test_create_from_template_without_instruction(tmp_path):
    """Template with no instruction should still have a system_prompt."""
    mgr = AgentManager(db_path=str(tmp_path / "test.db"))
    agent = mgr.create_from_template("research_monitor", "Test Agent")
    config = agent["config"]
    assert "system_prompt" in config
    assert len(config["system_prompt"]) > 100  # non-trivial prompt
    mgr.close()


def test_create_from_template_preserves_icon(tmp_path):
    """Template icon field should be preserved in config."""
    mgr = AgentManager(db_path=str(tmp_path / "test.db"))
    agent = mgr.create_from_template("research_monitor", "Test Agent")
    config = agent["config"]
    assert config.get("icon") == "🔬"
    mgr.close()


def test_common_agent_templates_expose_capability_hints(tmp_path):
    mgr = AgentManager(db_path=str(tmp_path / "test.db"))
    templates = {item["id"]: item for item in mgr.list_templates()}

    assert templates["project_orchestrator"]["capability"] == "general"
    assert templates["qwen_mm_reviewer"]["capability"] == "multimodal"
    assert templates["anti_slop_reviewer"]["capability"] == "coding"
    assert templates["thermos_reviewer"]["capability"] == "coding"
    mgr.close()


def test_create_qwen_mm_template_preserves_multimodal_capability(tmp_path):
    mgr = AgentManager(db_path=str(tmp_path / "test.db"))
    agent = mgr.create_from_template(
        "qwen_mm_reviewer",
        "Visual QA",
        overrides={"instruction": "Review the dashboard screenshot"},
    )

    assert agent["config"]["capability"] == "multimodal"
    assert "dashboard screenshot" in agent["config"]["system_prompt"]
    mgr.close()


def test_project_orchestrator_uses_safe_project_advance_protocol(tmp_path):
    mgr = AgentManager(db_path=str(tmp_path / "test.db"))
    templates = {item["id"]: item for item in mgr.list_templates()}
    template = templates["project_orchestrator"]

    assert "project_status" in template["tools"]
    assert "project_advance" in template["tools"]
    agent = mgr.create_from_template(
        "project_orchestrator",
        "Project Coordinator",
        overrides={"instruction": "Implement the project safely"},
    )
    prompt = agent["config"]["system_prompt"]
    assert agent["config"]["max_advertised_tools"] == 12
    assert "prefer project_advance for routine progress" in prompt
    assert "dispatches only READY streams" in prompt
    assert "never mark a stream DONE without concrete evidence" in prompt
    mgr.close()


def test_domain_orchestrator_can_reuse_non_project_handoffs(tmp_path):
    mgr = AgentManager(db_path=str(tmp_path / "test.db"))
    try:
        templates = {item["id"]: item for item in mgr.list_templates()}
        template = templates["domain_orchestrator"]

        assert "task_dispatch" in template["tools"]
        assert "task_status" in template["tools"]

        agent = mgr.create_from_template(
            "domain_orchestrator",
            "General Coordinator",
            overrides={"instruction": "Coordinate bounded domain work"},
        )
        prompt = agent["config"]["system_prompt"]
        assert agent["config"]["max_advertised_tools"] == 12
        assert "Use task_status" in prompt
        assert "instead of spawning duplicate work" in prompt
        assert "Do not turn ordinary non-project work into a software project" in prompt
    finally:
        mgr.close()
