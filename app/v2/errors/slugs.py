class ValidationErrorSlugs:
    # phone numbers validation
    TOO_MANY_DIGITS = "phone_number:too_many_digits"
    NOT_ENOUGH_DIGITS = "phone_number:not_enough_digits"
    NOT_A_UK_MOBILE_NUMBER = "phone_number:not_a_uk_mobile_number"
    NO_LETTERS_OR_SYMBOLS = "phone_number:remove_letters_and_symbols"
    INVALID_COUNTRY_PREFIX = "phone_number:invalid_country_prefix"

    PHONE_NUMBER_REQUIRED = "phone_number:is_required_property"
