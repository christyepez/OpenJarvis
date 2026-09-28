from openjarvis.evals.jarvisbench import JarvisBenchSample, summarize


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
    assert summary.policy_violation_rate == 0.5
    assert summary.average_latency_seconds == 3.0
    assert summary.average_cost_usd == 0.1
    assert summary.average_retries == 1.0


def test_jarvisbench_empty_summary_is_zeroed() -> None:
    summary = summarize([])

    assert summary.samples == 0
    assert summary.task_success_rate == 0.0
