from openjarvis.evals.jarvisbench import (
    JarvisBenchRoutingCase,
    JarvisBenchSample,
    evaluate_routing_cases,
    summarize,
)
from openjarvis.intelligence.model_catalog import BUILTIN_MODELS


def test_jarvisbench_summarizes_governed_execution() -> None:
    summary = summarize(
        [
            JarvisBenchSample(
                task_id="1",
                success=True,
                expected_model="local-a",
                selected_model="local-a",
                expected_tools=frozenset({"git_status", "file_read"}),
                selected_tools=frozenset({"git_status", "file_read"}),
                latency_seconds=2.0,
                retries=0,
            ),
            JarvisBenchSample(
                task_id="2",
                success=False,
                expected_model="local-a",
                selected_model="cloud-b",
                expected_tools=frozenset({"calculator"}),
                selected_tools=frozenset(),
                policy_violations=1,
                latency_seconds=4.0,
                cost_usd=0.2,
                retries=2,
            ),
        ]
    )

    assert summary.samples == 2
    assert summary.task_success_rate == 0.5
    assert summary.model_routing_accuracy == 0.5
    assert summary.tool_selection_accuracy == 0.5
    assert summary.domain_routing_accuracy == 0.0
    assert summary.capability_routing_accuracy == 0.0
    assert summary.policy_violation_rate == 0.5
    assert summary.average_latency_seconds == 3.0
    assert summary.average_cost_usd == 0.1
    assert summary.average_retries == 1.0


def test_jarvisbench_empty_summary_is_zeroed() -> None:
    summary = summarize([])

    assert summary.samples == 0
    assert summary.task_success_rate == 0.0


def test_jarvisbench_evaluates_multidomain_local_routing() -> None:
    cases = [
        JarvisBenchRoutingCase(
            task_id="finance-general",
            query="Review my bank budget and expenses for this month",
            expected_domain="finance",
            expected_capability="general",
            expected_model="qwen3.5:4b",
        ),
        JarvisBenchRoutingCase(
            task_id="project-code",
            query="Refactor the Python code in this repository and commit the fix",
            expected_domain="project",
            expected_capability="coding",
            expected_model="granite-code:3b",
        ),
        JarvisBenchRoutingCase(
            task_id="knowledge-visual",
            query="Review this document diagram screenshot as a reference",
            expected_domain="knowledge",
            expected_capability="multimodal",
            expected_model="qwen3.5:4b",
        ),
        JarvisBenchRoutingCase(
            task_id="communication-general",
            query="Draft a reply to this email message before the meeting",
            expected_domain="communication",
            expected_capability="general",
            expected_model="qwen3.5:4b",
        ),
    ]

    samples = evaluate_routing_cases(
        cases,
        runtime_model_ids=["qwen3.5:4b", "granite-code:3b"],
        catalog=BUILTIN_MODELS,
        preferred_models=("qwen3.5:4b", "granite-code:3b"),
    )
    summary = summarize(samples)

    assert summary.samples == 4
    assert summary.task_success_rate == 1.0
    assert summary.domain_routing_accuracy == 1.0
    assert summary.capability_routing_accuracy == 1.0
    assert summary.model_routing_accuracy == 1.0
    assert summary.policy_violation_rate == 0.0
    assert summary.average_cost_usd == 0.0
