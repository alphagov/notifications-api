from typing import ClassVar, Literal, Union

from pydantic import BaseModel, Field, ValidationError


class NotifyValidationError(Exception):
    def __init__(self, override_message=None, original_error=None, *args, **kwargs):
        self.override_message = override_message
        self.original_error = original_error
        super().__init__(*args, **kwargs)


class CustomErrorBaseModel(BaseModel):
    override_errors: ClassVar = {}

    def __init__(self, **kwargs):
        try:
            super().__init__(**kwargs)
        except ValidationError as e:
            for error in e.errors():
                if override := self.override_errors.get((error["type"], error["loc"])):
                    raise NotifyValidationError(override_message=override) from e
            raise NotifyValidationError(original_error=e) from e


class UnauthorizedResponse(BaseModel):
    result: Literal["error"] = Field()
    message: Union[dict, str] = Field()
