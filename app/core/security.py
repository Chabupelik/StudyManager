from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, unquote_plus, urlencode

import jwt

from app.core.config import get_settings


def create_access_token(data: dict) -> str:
    settings = get_settings()
    payload = data.copy()
    payload["exp"] = datetime.now(UTC) + timedelta(days=settings.jwt_expire_days)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    settings = get_settings()
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        return None


def validate_tg_init_data(init_data: str) -> dict | None:
    settings = get_settings()
    try:
        parsed = dict(parse_qsl(unquote_plus(init_data)))
        hash_tg = parsed.pop("hash", None)
        if not hash_tg:
            return None

        data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret = hmac.new(
            b"WebAppData", settings.bot_token.encode(), hashlib.sha256
        ).digest()
        expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected, hash_tg):
            return None

        return json.loads(parsed.get("user", "{}"))
    except Exception:
        return None


def validate_vk_sign(query_string: str, protected_key: str) -> dict | None:
    """
    Проверяет query-строку параметров запуска VK Mini App.
    Спецификация: https://dev.vk.com/mini-apps/development/launch-params/sign

    Возвращает словарь vk_* параметров при валидной подписи, None — при невалидной.
    """
    if not protected_key:
        return None
    try:
        parsed = dict(parse_qsl(query_string, keep_blank_values=True))
        client_sign = parsed.get("sign")
        if not client_sign:
            return None

        # Только параметры с префиксом vk_
        vk_params = {k: v for k, v in parsed.items() if k.startswith("vk_")}
        sorted_query = urlencode(sorted(vk_params.items()))

        computed_hash = hmac.new(
            protected_key.encode("utf-8"),
            sorted_query.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        expected_sign = (
            base64.urlsafe_b64encode(computed_hash).decode("utf-8").rstrip("=")
        )

        if hmac.compare_digest(client_sign, expected_sign):
            return vk_params
        return None
    except Exception:
        return None


def create_logs_token() -> str:
    settings = get_settings()
    expires = int(time.time()) + 3600
    payload = str(expires).encode()
    signature = hmac.new(
        settings.logs_secret_key.encode(), payload, hashlib.sha256
    ).hexdigest()
    return f"{expires}.{signature}"


def verify_logs_token(token: str) -> bool:
    settings = get_settings()
    try:
        expires_str, signature = token.split(".")
        expires = int(expires_str)

        if time.time() > expires:
            return False

        expected = hmac.new(
            settings.logs_secret_key.encode(),
            expires_str.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


def verify_password_hash(plain_password: str, stored_hash: str) -> bool:
    incoming = hashlib.sha256(plain_password.encode()).hexdigest()
    return hmac.compare_digest(incoming, stored_hash)
