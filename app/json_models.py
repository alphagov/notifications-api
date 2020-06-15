class JSONModel():

    ALLOWED_PROPERTIES = set()

    def __init__(self, _dict):
        # in the case of a bad request _dict may be `None`
        self._dict = _dict or {}

    def __bool__(self):
        return self._dict != {}

    def __hash__(self):
        return hash(self.id)

    def __dir__(self):
        return super().__dir__() + list(sorted(self.ALLOWED_PROPERTIES))

    def __eq__(self, other):
        return self.id == other.id

    def __getattribute__(self, attr):

        try:
            return super().__getattribute__(attr)
        except AttributeError as e:
            # Re-raise any `AttributeError`s that are not directly on
            # this object because they indicate an underlying exception
            # that we don’t want to swallow
            if str(e) != "'{}' object has no attribute '{}'".format(
                self.__class__.__name__, attr
            ):
                raise e

        if attr in super().__getattribute__('ALLOWED_PROPERTIES'):
            return super().__getattribute__('_dict')[attr]

        raise AttributeError((
            "'{}' object has no attribute '{}' and '{}' is not a field "
            "in the underlying JSON"
        ).format(
            self.__class__.__name__, attr, attr
        ))


class TemplateJSONModel(JSONModel):
    ALLOWED_PROPERTIES = {
        'archived',
        'id',
        'postage',
        'process_type',
        'reply_to_text',
        'template_type',
        'version',
    }
