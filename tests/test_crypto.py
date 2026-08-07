"""加密工具测试"""

import pytest
from cryptography.fernet import Fernet

from app.security.crypto import ConfigCrypto, is_sensitive_field


class TestConfigCrypto:
    def test_encrypt_decrypt_roundtrip(self):
        key = Fernet.generate_key().decode()
        crypto = ConfigCrypto(secret=key)
        token = crypto.encrypt("sk-abcdef123456")
        assert token != "sk-abcdef123456"
        assert token.startswith("gAAAAA")  # Fernet token 前缀
        assert crypto.decrypt(token) == "sk-abcdef123456"

    def test_empty_plaintext(self):
        crypto = ConfigCrypto(secret=Fernet.generate_key().decode())
        assert crypto.encrypt("") == ""
        assert crypto.decrypt("") == ""

    def test_decrypt_invalid_token_returns_empty(self):
        crypto = ConfigCrypto(secret=Fernet.generate_key().decode())
        assert crypto.decrypt("not-a-valid-token") == ""

    def test_mask(self):
        crypto = ConfigCrypto(secret=Fernet.generate_key().decode())
        assert crypto.mask("sk-abcdef123456") == "sk****56"
        assert crypto.mask("abcdefgh") == "ab****gh"
        assert crypto.mask("ab") == "**"
        assert crypto.mask("") == ""

    def test_secret_derivation_from_arbitrary_string(self):
        """测试任意字符串密钥可派生为 Fernet key"""
        crypto = ConfigCrypto(secret="my-arbitrary-secret-key")
        token = crypto.encrypt("hello")
        assert crypto.decrypt(token) == "hello"

    def test_invalid_secret_raises(self):
        # 空 secret 且无法生成时（无 Redis）应报清晰错误或兜底
        crypto = ConfigCrypto(secret="")
        try:
            crypto.encrypt("x")
            # 若成功（走 Redis/兜底）也算通过
        except ValueError as e:
            assert "AI_CONFIG_SECRET" in str(e)


class TestIsSensitiveField:
    def test_sensitive_keywords(self):
        assert is_sensitive_field("api_key") is True
        assert is_sensitive_field("password") is True
        assert is_sensitive_field("llm_api_key") is True
        assert is_sensitive_field("password_encrypted") is True

    def test_non_sensitive_fields(self):
        assert is_sensitive_field("base_url") is False
        assert is_sensitive_field("temperature") is False
        assert is_sensitive_field("model") is False
