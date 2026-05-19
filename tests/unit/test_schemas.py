from __future__ import annotations

from lucid.llm.schemas import ActionBlock, ComputerUseBlock


def test_action_block_from_tool_use_merges_coordinate() -> None:
    block = ComputerUseBlock(
        id="t1",
        action="left_click",
        coordinate=(100, 200),
        raw={"name": "computer", "input": {"action": "left_click"}},
    )
    action = ActionBlock.from_tool_use(block)
    assert action.id == "t1"
    assert action.action == "left_click"
    assert action.params["coordinate"] == [100, 200]


def test_action_block_preserves_raw_input() -> None:
    block = ComputerUseBlock(
        id="t2",
        action="type",
        raw={"name": "computer", "input": {"action": "type", "text": "hello"}},
    )
    action = ActionBlock.from_tool_use(block)
    assert action.action == "type"
    assert action.params["text"] == "hello"
