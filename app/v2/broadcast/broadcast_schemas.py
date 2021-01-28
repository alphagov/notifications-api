post_broadcast_schema = {
    "$schema": "http://json-schema.org/draft-07/schema",
    "type": "object",
    "required": [
        "reference",
        "category",
        "content",
        "areas",
    ],
    "additionalProperties": False,
    "properties": {
        "reference": {
            "type": [
                "string",
                "null",
            ],
        },
        "category": {
            "type": "string",
            "enum": [
                "Geo",
                "Met",
                "Safety",
                "Security",
                "Rescue",
                "Fire",
                "Health",
                "Env",
                "Transport",
                "Infra",
                "CBRNE",
                "Other",
            ],
        },
        "expires": {
            "type": "string",
            "format": "date-time",
        },
        "content": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1395,
        },
        "web": {
            "type": "string",
            "format": "uri",
        },
        "areas": {
            "type": "array",
            "minItems": 1,
            "items": {
                "$ref": "#/definitions/area",
            },
        },
    },
    "definitions": {
        "area": {
            "type": "object",
            "required": [
                "name",
                "polygons",
            ],
            "additionalProperties": False,
            "properties": {
                "name": {
                    "type": "string",
                },
                "polygons": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "oneOf": [
                            {
                                "$ref": "#/definitions/polygon",
                            },
                        ],
                    },
                },
            },
        },
        "polygon": {
            "type": "array",
            "minItems": 4,
            "items": {
                "$ref": "#/definitions/coordinatePair",
            },
        },
        "coordinatePair": {
            "type": "array",
            "items": {
                "type": "number"
            },
            "minItems": 2,
            "maxItems": 2,
        },
    },
}
