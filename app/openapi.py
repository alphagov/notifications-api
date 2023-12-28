from typing import ClassVar, Literal, Union

from pydantic import BaseModel, Field, ValidationError


class NotifyValidationError(Exception):
    def __init__(self, override_message=None, original_error=None, *args, **kwargs):
        self.override_message = override_message
        self.original_error = original_error
        super().__init__(*args, **kwargs)

    def serialize(self):
        if self.override_message:
            return {"errors": [{"error": "ValidationError", "message": self.override_message}], "status_code": 400}

        from flask import current_app

        for error in self.original_error.errors():
            current_app.logger.error(
                "Pydantic validation error has not been overridden - possible leak of implementation details: "
                "%(error_type)s, %(error_loc)s, %(error_msg)s",
                dict(error_type=error["type"], error_loc=error["loc"], error_msg=error["msg"]),
            )

        # fixme: handle this better
        return {"errors": [{"error": "ValidationError", "message": "Contact GOV.UK Notify"}], "status_code": 400}


class CustomErrorBaseModel(BaseModel):
    override_errors: ClassVar = {}  # fixme: probably frozen dict

    def __init__(self, **kwargs):
        try:
            super().__init__(**kwargs)
        except ValidationError as e:
            for error in e.errors():
                if override := self.override_errors.get((error["type"], error["loc"])):
                    raise NotifyValidationError(override_message=override, original_error=e) from e
            raise NotifyValidationError(original_error=e) from e


class UnauthorizedResponse(BaseModel):
    result: Literal["error"] = Field()
    message: Union[dict, str] = Field()
