import pytest
from pydantic import ValidationError

from robot_agent.agent.action_validator import validate_action


# 测试1：合法地点
def test_valid_location():
    result = validate_action(
        "navigate_to_location",
        {"target": "kitchen"}
    )
    assert result.target == "kitchen"


# 测试2：非法地点
def test_invalid_location():
    with pytest.raises(ValidationError):
        validate_action(
            "navigate_to_location",
            {"target": "mars"}
        )


# 测试3：非法工具名称
def test_invalid_tool():
    with pytest.raises(ValueError):
        validate_action(
            "delete_map",
            {"target": "kitchen"}
        )


# 测试4：不允许额外参数
def test_extra_argument():
    with pytest.raises(ValidationError):
        validate_action(
            "navigate_to_location",
            {"target": "room", "speed": 100}
        )
