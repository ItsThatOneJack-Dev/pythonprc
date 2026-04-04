"""
erlc.webhook — Ed25519 signature verification for ER:LC event webhooks.

The game signs every webhook POST with Ed25519.
Your endpoint must verify every request before acting on it.

Usage (aiohttp example)
-----------------------
    from erlc.webhook import verify_signature, WebhookVerificationError

    async def handle_webhook(request: aiohttp.web.Request):
        raw_body = await request.read()
        timestamp = request.headers.get("X-Signature-Timestamp", "")
        sig_hex  = request.headers.get("X-Signature-Ed25519", "")

        try:
            verify_signature(timestamp, sig_hex, raw_body)
        except WebhookVerificationError:
            raise aiohttp.web.HTTPUnauthorized()

        payload = json.loads(raw_body)
        ...

Usage (Flask example)
---------------------
    from erlc.webhook import verify_signature, WebhookVerificationError

    @app.route("/webhook", methods=["POST"])
    def webhook():
        raw_body = request.get_data()
        try:
            verify_signature(
                request.headers["X-Signature-Timestamp"],
                request.headers["X-Signature-Ed25519"],
                raw_body,
            )
        except WebhookVerificationError:
            abort(401)
        ...
"""

from __future__ import annotations

import base64
import binascii


# ERLC's public key in base64 SubjectPublicKeyInfo (SPKI) format
_PUBLIC_KEY_B64 = "MCowBQYDK2VwAyEAjSICb9pp0kHizGQtdG8ySWsDChfGqi+gyFCttigBNOA="


class WebhookVerificationError(Exception):
    """Raised when a webhook signature fails verification."""


def _get_public_key():
    """
    Load the Ed25519 public key, using cryptography if available,
    falling back to PyNaCl.
    """
    try:
        from cryptography.hazmat.primitives.serialization import load_der_public_key # type: ignore
        der = base64.b64decode(_PUBLIC_KEY_B64)
        return ("cryptography", load_der_public_key(der))
    except ImportError:
        pass

    try:
        import nacl.signing  # type: ignore
        # SPKI for Ed25519 is a 12-byte header + 32-byte raw key
        der = base64.b64decode(_PUBLIC_KEY_B64)
        raw_key = der[-32:]
        return ("nacl", nacl.signing.VerifyKey(raw_key))
    except ImportError:
        pass

    raise ImportError(
        "Webhook verification requires either the 'cryptography' or 'PyNaCl' package. "
        "Install one with: pip install cryptography  (or: pip install PyNaCl)"
    )


def verify_signature(timestamp: str, sig_hex: str, raw_body: bytes) -> None:
    """
    Verify an Ed25519 webhook signature from ER:LC.

    Parameters
    ----------
    timestamp:
        The exact string from the X-Signature-Timestamp header.
    sig_hex:
        The hex-encoded signature from the X-Signature-Ed25519 header.
    raw_body:
        The raw, unmodified request body bytes.

    Raises
    ------
    WebhookVerificationError
        If the signature is invalid or headers are missing/malformed.
    """
    if not timestamp or not sig_hex:
        raise WebhookVerificationError("Missing signature headers.")

    try:
        sig_bytes = binascii.unhexlify(sig_hex)
    except (binascii.Error, ValueError) as exc:
        raise WebhookVerificationError(f"Malformed signature hex: {exc}") from exc

    # message = UTF-8 bytes of timestamp + raw body (no separator)
    message = timestamp.encode("utf-8") + raw_body

    backend, key = _get_public_key()

    try:
        if backend == "cryptography":
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey # type: ignore
            from cryptography.exceptions import InvalidSignature # type: ignore
            assert isinstance(key, Ed25519PublicKey)
            try:
                key.verify(sig_bytes, message)
            except InvalidSignature as exc:
                raise WebhookVerificationError("Signature verification failed.") from exc

        elif backend == "nacl":
            import nacl.exceptions  # type: ignore
            try:
                key.verify(message, sig_bytes)
            except nacl.exceptions.BadSignatureError as exc:
                raise WebhookVerificationError("Signature verification failed.") from exc

    except WebhookVerificationError:
        raise
    except Exception as exc:
        raise WebhookVerificationError(f"Unexpected error during verification: {exc}") from exc