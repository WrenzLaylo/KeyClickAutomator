from app import AutomatorApp


def test_mix_color_endpoints_and_midpoint():
    assert AutomatorApp._mix_color("#000000", "#FFFFFF", 0.0) == "#000000"
    assert AutomatorApp._mix_color("#000000", "#FFFFFF", 1.0) == "#FFFFFF"
    assert AutomatorApp._mix_color("#000000", "#FFFFFF", 0.5) == "#808080"
