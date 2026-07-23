from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import Settings


def _fernet(settings: Settings) -> Fernet:
    return Fernet(settings.secrets_fernet_key.encode("utf-8"))


def encrypt_secret(plaintext: str, settings: Settings) -> str:
    return _fernet(settings).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str, settings: Settings) -> str:
    try:
        return _fernet(settings).decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt secret") from exc


def generate_fernet_key() -> str:
    return Fernet.generate_key().decode("utf-8")
