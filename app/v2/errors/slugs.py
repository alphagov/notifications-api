class ValidationErrorSlugs:
    # phone number validation
    TOO_MANY_DIGITS = "phone_number:too_many_digits"
    NOT_ENOUGH_DIGITS = "phone_number:not_enough_digits"
    NOT_A_UK_MOBILE_NUMBER = "phone_number:not_a_uk_mobile_number"
    NO_LETTERS_OR_SYMBOLS = "phone_number:remove_letters_and_symbols"
    INVALID_COUNTRY_PREFIX = "phone_number:invalid_country_prefix"
    PHONE_NUMBER_REQUIRED = "phone_number:required_property"

    # email address validation
    EMAIL_ADDRESS_REQUIRED = "email_address:required_property"

    # template id validation
    TEMPLATE_ID_REQUIRED = "template_id:required_property"
    TEMPLATE_ID_INVALID = "template_id:invalid"

    PERSONALISATION_REQUIRED = "personalisation:required_property"

    NOTIFICATION_ID_REQUIRED = "notification_id:required_property"

    # reference validation
    REFERENCE_REQUIRED = "reference:required_property"  # for precompiled letters only
    REFERENCE_TOO_LONG = "reference:too_long"

    CONTENT_REQUIRED = "content:required_property"

    """
    QUESTIONS / DISCUSSION POINTS
    1. For this test: test_get_complaint_with_invalid_data_returns_400_status_code, the error message is
    'start_date month must be in 1..12'. It comes from e.path + e.cause. How exact we want to get wit our slugs
    - do we want a separate slug for day, month, and year in the date, like `start_date:month_must_be_in_1..1`,
    or do we want to be a bit more vague, for example `start_date:format`? How much resolution do we want?

    """
    @classmethod
    def get_error_slug(cls, error) -> str:
        slug = ""
        if error.path:
            slug += f"{error.path}:"
        else:
            "see what we do for the messages"
        if error.cause:
            slug += str(error.cause).replace(" ", "_")
        else:
            slug += error.message.replace(" ", "_")

        return slug