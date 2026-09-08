from bumblehive.tools import ToolApprovalDecision


def test_approval_decision_factories() -> None:
    assert ToolApprovalDecision.approve() == ToolApprovalDecision(approved=True)
    assert ToolApprovalDecision.reject("not allowed") == ToolApprovalDecision(
        approved=False,
        reason="not allowed",
    )
