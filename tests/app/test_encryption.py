from app.encryption import Encryption

encryption = Encryption()


def test_should_encrypt_content(notify_api):
    encryption.init_app(notify_api)
    assert encryption.encrypt("this") != "this"


def test_should_decrypt_content(notify_api):
    encryption.init_app(notify_api)
    encrypted = encryption.encrypt("this")
    assert encryption.decrypt(encrypted) == "this"


def test_should_encrypt_json(notify_api):
    encryption.init_app(notify_api)
    encrypted = encryption.encrypt({"this": "that"})
    assert encryption.decrypt(encrypted) == {"this": "that"}
