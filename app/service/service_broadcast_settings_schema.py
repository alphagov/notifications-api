service_broadcast_settings_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "Set a services broadcast settings",
    "type": "object",
    "title": "Set a services broadcast settings",
    "properties": {
        "broadcast_channel": {"enum": ["test", "severe"]}
    },
    "required": ["broadcast_channel"]
}
