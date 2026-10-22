"""Embedded watsonx Orchestrate chat: config + JWT signing for the dashboard.

Env vars (set in Render):
  WXO_PRIVATE_KEY        your RS256 private key (PEM; multi-line, or one line with literal \\n)
  IBM_PUBLIC_KEY         IBM's public key for your instance (PEM)
  WXO_ORCHESTRATION_ID   from `orchestrate channels webchat embed`
  WXO_HOST_URL           "
  WXO_CRN                "
  WXO_AGENT_ID           "
  WXO_AGENT_ENV_ID       "
  WXO_DEPLOYMENT_PLATFORM  optional, defaults to "ibmcloud"
  CHAT_TOKEN_TTL_SECONDS   optional, defaults to 3600
If any of these are missing the dashboard still works; the chat panel just says it isn't configured.
"""
import base64
import json
import os
import time
import uuid

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from flask import Blueprint, jsonify, make_response, request

bp = Blueprint("chat_auth", __name__)

_REQUIRED = ["WXO_PRIVATE_KEY", "IBM_PUBLIC_KEY", "WXO_ORCHESTRATION_ID", "WXO_HOST_URL",
             "WXO_AGENT_ID", "WXO_AGENT_ENV_ID"]
_COOKIE = "ANONYMOUS-USER-ID"


def _pem(name: str) -> bytes:
    return os.environ.get(name, "").replace("\\n", "\n").strip().encode()


def _missing() -> list[str]:
    return [k for k in _REQUIRED if not os.environ.get(k)]


def _encrypt_for_ibm(payload: dict) -> str:
    """RSA-OAEP (SHA-1) encrypt, base64 — same scheme as IBM's node-rsa sample."""
    key = serialization.load_pem_public_key(_pem("IBM_PUBLIC_KEY"))
    data = json.dumps(payload).encode()
    return base64.b64encode(
        key.encrypt(data, padding.OAEP(mgf=padding.MGF1(hashes.SHA1()), algorithm=hashes.SHA1(), label=None))
    ).decode()


@bp.route("/chat/config")
def chat_config():
    missing = _missing()
    if missing:
        return jsonify({"enabled": False, "missing": missing})
    return jsonify({
        "enabled": True,
        "orchestrationID": os.environ["WXO_ORCHESTRATION_ID"],
        "hostURL": os.environ["WXO_HOST_URL"].rstrip("/"),
        "deploymentPlatform": os.environ.get("WXO_DEPLOYMENT_PLATFORM", "ibmcloud"),
        "crn": os.environ.get("WXO_CRN"),
        "agentId": os.environ["WXO_AGENT_ID"],
        "agentEnvironmentId": os.environ["WXO_AGENT_ENV_ID"],
    })


@bp.route("/chat/token")
def chat_token():
    if _missing():
        return make_response("Chat is not configured", 503)
    user_id = request.cookies.get(_COOKIE) or f"anon-{uuid.uuid4()}"
    now = int(time.time())
    try:
        token = jwt.encode(
            {
                "sub": user_id,
                "iat": now,
                "exp": now + int(os.environ.get("CHAT_TOKEN_TTL_SECONDS", "3600")),
                "user_payload": _encrypt_for_ibm({"name": "Dashboard user", "custom_user_id": user_id}),
                # Readable by the browser; keep it non-sensitive. The acting role is NOT put
                # here: it can change mid-session, so the page sends it per message (pre:send).
                # A JWT context value would override that, per the wxO docs.
                "context": {"channel": "dashboard"},
            },
            _pem("WXO_PRIVATE_KEY"),
            algorithm="RS256",
        )
    except Exception as e:  # bad PEM, wrong key type, payload too large for key...
        return make_response(f"Could not create chat token: {e}", 500)

    resp = make_response(token)
    resp.mimetype = "text/plain"
    if not request.cookies.get(_COOKIE):
        resp.set_cookie(_COOKIE, user_id, max_age=45 * 24 * 3600, httponly=True,
                        secure=request.is_secure or request.headers.get("X-Forwarded-Proto") == "https",
                        samesite="Lax")
    return resp
