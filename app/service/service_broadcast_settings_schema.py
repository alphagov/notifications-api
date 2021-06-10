service_broadcast_settings_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "Set a services broadcast settings",
    "type": "object",
    "title": "Set a services broadcast settings",
    "properties": {
        "broadcast_channel": {"enum": ["operator", "test", "severe", "government"]},
        "service_mode": {"enum": ["training", "live"]},
        "provider_restriction": {"enum": ["three", "o2", "vodafone", "ee", "all"]}
    },
    "required": ["broadcast_channel", "service_mode", "provider_restriction"]
}
