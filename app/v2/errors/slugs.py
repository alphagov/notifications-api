class ValidationErrorSlugs:
    # phone numbers validation
    TOO_MANY_DIGITS = "phone_number:too_many_digits"
    NOT_ENOUGH_DIGITS = "phone_number:not_enough_digits"
    NOT_A_UK_MOBILE_NUMBER = "phone_number:not_a_uk_mobile_number"
    NO_LETTERS_OR_SYMBOLS = "phone_number:remove_letters_and_symbols"
    INVALID_COUNTRY_PREFIX = "phone_number:invalid_country_prefix"

    # required property 
    REQUIRED_PHONE_NUMBER = "required_property:phone_number"
    REQUIRED_EMAIL_ADDRESS = "required_property:email_address"
    REQUIRED_TEMPLATE_ID = "required_property:template_id"
    REQUIRED_PERSONALISATION = "required_property:personalisation"
    REQUIRED_NOTIFICATION_ID = "required_property:notification_id"
    REQUIRED_REFERENCE = "required_property:reference" # for precompiled letters only
    REQUIRED_CONTENT = "required_property:content"
