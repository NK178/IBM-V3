"""Embedded watsonx Orchestrate chat: config + JWT signing for the dashboard.

Env vars (set in Render):
  WXO_PRIVATE_KEY        your RS256 private key (PEM; multi-line, or one line with literal \\n)
  IBM_PUBLIC_KEY         optional — IBM's public key; only needed to pass an SSO token (user_payload)
  WXO_ORCHESTRATION_ID   from `orchestrate channels webchat embed`
  WXO_HOST_URL           "
  WXO_CRN                "
  WXO_AGENT_ID           "
  WXO_AGENT_ENV_ID       optional — only if your snippet has chatOptions.agentEnvironmentId
  WXO_DEPLOYMENT_PLATFORM  optional, defaults to "ibmcloud"
  CHAT_TOKEN_TTL_SECONDS   optional, defaults to 3600
If any of these are missing the dashboard still works; the chat panel just says it isn't configured.
"""
import base64
import json
import os
import re
import time
import uuid

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from flask import Blueprint, current_app, jsonify, make_response, request

bp = Blueprint("chat_auth", __name__)

_REQUIRED = ["WXO_PRIVATE_KEY", "WXO_ORCHESTRATION_ID", "WXO_HOST_URL",
             "WXO_AGENT_ID"]
_COOKIE = "ANONYMOUS-USER-ID"


def _pem(name: str) -> bytes:
    """Read a PEM key from the environment, forgiving common copy/paste mistakes.

    Accepts real newlines or literal \\n, Windows line endings, surrounding quotes,
    and a key pasted with its line breaks turned into spaces.
    """
    v = os.environ.get(name, "").strip().strip('"').strip("'").strip()
    v = v.replace("\\\\n", "\n").replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    m = re.match(r"^(-----BEGIN [A-Z ]+-----)\s*(.*?)\s*(-----END [A-Z ]+-----)$", v, re.S)
    if m:  # rebuild the body: drop stray spaces/newlines, re-wrap at 64 chars
        body = re.sub(r"\s+", "", m.group(2))
        v = m.group(1) + "\n" + "\n".join(body[i:i + 64] for i in range(0, len(body), 64)) + "\n" + m.group(3)
    return (v + "\n").encode() if v else b""


def _private_key_problem() -> str | None:
    """A plain-English reason WXO_PRIVATE_KEY can't be used, or None if it looks fine."""
    raw = _pem("WXO_PRIVATE_KEY").decode()
    if "PUBLIC KEY" in raw:
        return ("WXO_PRIVATE_KEY contains a PUBLIC key. Paste private.pem there instead; "
                "public.pem goes in watsonx Orchestrate's Embed Security tab")
    if "PRIVATE KEY" not in raw:
        return "WXO_PRIVATE_KEY is missing its '-----BEGIN PRIVATE KEY-----' / '-----END PRIVATE KEY-----' lines"
    try:
        serialization.load_pem_private_key(raw.encode(), password=None)
    except Exception as e:
        return f"WXO_PRIVATE_KEY could not be read ({e.__class__.__name__}); re-copy the whole private.pem"
    return None


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
        # Newer embed snippets omit this; only send it when it's set.
        "agentEnvironmentId": os.environ.get("WXO_AGENT_ENV_ID") or None,
    })


@bp.route("/chat/token")
def chat_token():
    if _missing():
        return make_response("Chat is not configured", 503)
    user_id = request.cookies.get(_COOKIE) or f"anon-{uuid.uuid4()}"
    now = int(time.time())
    try:
        claims = {
            "sub": user_id,
            "iat": now,
            "exp": now + int(os.environ.get("CHAT_TOKEN_TTL_SECONDS", "3600")),
            # Readable by the browser; keep it non-sensitive. The acting role is NOT put
            # here: it can change mid-session, so the page sends it per message (pre:send).
            # A JWT context value would override that, per the wxO docs.
            "context": {"channel": "dashboard"},
        }
        # user_payload (encrypted with IBM's public key) is only used to pass an SSO token for
        # on-behalf-of flows. We don't need that, so it's sent only if an IBM key is configured.
        if os.environ.get("IBM_PUBLIC_KEY"):
            try:
                claims["user_payload"] = _encrypt_for_ibm({"name": "Dashboard user", "custom_user_id": user_id})
            except Exception as e:  # a bad optional key must not block the chat
                current_app.logger.warning("IBM_PUBLIC_KEY is set but unusable (%s); sending token without "
                                           "user_payload. Remove or fix IBM_PUBLIC_KEY in Render.", e)
        token = jwt.encode(claims, _pem("WXO_PRIVATE_KEY"), algorithm="RS256")
    except Exception as e:  # bad PEM, wrong key type...
        reason = _private_key_problem() or str(e)
        current_app.logger.error("Chat token failed: %s", reason)
        return make_response(f"Could not create chat token: {reason}", 500)

    resp = make_response(token)
    resp.mimetype = "text/plain"
    if not request.cookies.get(_COOKIE):
        resp.set_cookie(_COOKIE, user_id, max_age=45 * 24 * 3600, httponly=True,
                        secure=request.is_secure or request.headers.get("X-Forwarded-Proto") == "https",
                        samesite="Lax")
    return resp
