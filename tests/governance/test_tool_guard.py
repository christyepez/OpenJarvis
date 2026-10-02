from openjarvis.core.config import GovernanceConfig, validate_config_key
from openjarvis.governance import (
    CostClass,
    CostPolicy,
    ProviderDescriptor,
    ProviderPolicyGuard,
)


def test_governance_config_is_settable() -> None:
    cfg = GovernanceConfig()
    assert cfg.prefer_local is True
    assert cfg.primary_implementer == "chatgpt:gpt-5.6-sol"
    assert validate_config_key("governance.approved_paid") is str
    assert validate_config_key("governance.primary_implementer") is str


def test_policy_can_be_built_from_config() -> None:
    cfg = GovernanceConfig(approved_paid="codex,commander")
    policy = CostPolicy.from_config(cfg)
    assert policy.approved_paid == frozenset({"codex", "commander"})


def test_guard_blocks_unapproved_paid_provider_until_approved() -> None:
    policy = CostPolicy()
    provider = ProviderDescriptor("paid-x", CostClass.REQUIRES_APPROVAL)
    guard = ProviderPolicyGuard(policy, {"external_tool": provider})

    assert guard("external_tool", {}) is False
    guard.approve_for_request("paid-x")
    assert guard("external_tool", {}) is True

    guard.clear_request_approvals()
    assert guard("external_tool", {}) is False


def test_guard_allows_unknown_tools_and_preapproved_commander() -> None:
    policy = CostPolicy()
    commander = ProviderDescriptor("commander", CostClass.REQUIRES_APPROVAL)
    guard = ProviderPolicyGuard(policy, {"desktop_command": commander})

    assert guard("unknown_tool", {}) is True
    assert guard("desktop_command", {}) is True
