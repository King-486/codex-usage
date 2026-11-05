"""仅传递短期访问凭据；与完整会话使用不同密钥和加密域。"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from fetch_usage import JsonObject, JsonValue, QuotaRequestError


def access_key() -> bytes:
    key: bytes = base64.b64decode(os.environ["NOX_ACCESS_KEY"], validate=True)
    if len(key) != 32:
        raise QuotaRequestError("configuration", 0, "Access snapshot key must contain 32 bytes")
    return key


def validate_access(value: JsonValue) -> JsonObject:
    expected: set[str] = {"status", "access_token", "account_id", "expires_at", "generated_at"}
    if not isinstance(value, dict) or set(value) != expected:
        raise QuotaRequestError("configuration", 0, "Access snapshot has unexpected fields")
    if value["status"] not in ("ready", "reauthorization_required"):
        raise QuotaRequestError("configuration", 0, "Access snapshot status is invalid")
    if not isinstance(value["access_token"], str) or not isinstance(value["account_id"], str):
        raise QuotaRequestError("configuration", 0, "Access snapshot token/account is invalid")
    if type(value["expires_at"]) is not int or type(value["generated_at"]) is not int:
        raise QuotaRequestError("configuration", 0, "Access snapshot timestamps are invalid")
    return value


def write_access(path: Path, value: JsonObject, key: bytes) -> None:
    payload: bytes = json.dumps(validate_access(value), sort_keys=True).encode("utf-8")
    nonce: bytes = os.urandom(12)
    ciphertext: bytes = AESGCM(key).encrypt(nonce, payload, b"nox-access-only-v1")
    path.write_text(json.dumps({"schema": 1, "nonce": base64.b64encode(nonce).decode("ascii"),
                               "ciphertext": base64.b64encode(ciphertext).decode("ascii")}, indent=2) + "\n", encoding="utf-8")


def read_access(path: Path, key: bytes) -> JsonObject:
    envelope: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(envelope, dict) or envelope.get("schema") != 1:
        raise QuotaRequestError("configuration", 0, "Invalid access snapshot envelope")
    nonce: JsonValue = envelope.get("nonce")
    ciphertext: JsonValue = envelope.get("ciphertext")
    if not isinstance(nonce, str) or not isinstance(ciphertext, str):
        raise QuotaRequestError("configuration", 0, "Invalid access snapshot encoding")
    payload: bytes = AESGCM(key).decrypt(base64.b64decode(nonce, validate=True), base64.b64decode(ciphertext, validate=True), b"nox-access-only-v1")
    return validate_access(json.loads(payload))
