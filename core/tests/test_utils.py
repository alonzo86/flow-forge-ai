import json

from flow_forge_ai.utils.toml import remove_none_values

def test_toml():
    test_toml = {
        "instrumentors": [
            {"name": "instrumentor1", "enabled": True, "options": {"key1": "value1"}},
            {"name": "instrumentor2", "enabled": False, "options": None},
        ],
        "sinks": [
            {"name": "sink1", "enabled": True, "options": {"key2": None}},
            {"name": "sink2", "enabled": False, "options": {"key3": "value3"}},
        ],
        "runtime": {
            "source_sink": None,
            "listener_options": {"option1": None, "option2": "value2"},
        },
    }
    expected = {
        "instrumentors": [
            {"name": "instrumentor1", "enabled": True, "options": {"key1": "value1"}},
            {"name": "instrumentor2", "enabled": False},
        ],
        "sinks": [
            {"name": "sink1", "enabled": True, "options": {}},
            {"name": "sink2", "enabled": False, "options": {"key3": "value3"}},
        ],
        "runtime": {
            "listener_options": {"option2": "value2"},
        },
    }
    assert remove_none_values(test_toml) == expected