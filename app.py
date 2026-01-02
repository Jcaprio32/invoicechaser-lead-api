import os
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from flask_cors import CORS

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


app = Flask(__name__)

# ---- CORS ----
# During testing you can set ALLOW_ORIGIN="*"
# For production, set ALLOW_ORIGIN to your website origin, e.g.:
#   https://getinvoicechaser.com
# If you also use www, set it to:
#   https://www.getinvoicechaser.com
#
# NOTE: You can only set ONE origin with this simple env approach.
# If you need multiple, we can upgrade to a list in the next step.
allowed_origin = os.getenv("ALLOW_ORIGIN", "*")

CORS(
    app,
    resources={r"/api/*": {"origins": allowed_origin}},
    supports_credentials=False,
    methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# ---- ENV ----
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "")         # must be a verified sender in SendGrid
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "")   # where leads should go (e.g., support@getinvoicechaser.com)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_json():
    if not request.is_json:
        return jsonify({"ok": False, "error": "Request must be JSON"}), 400
    return None


def _safe(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _build_email_body(payload: dict) -> str:
    lines = [
        "New InvoiceChaser lead",
        "----------------------",
        f"Submitted at (UTC): {_safe(payload.get('submitted_at')) or _now_iso()}",
        f"Source: {_safe(payload.get('source'))}",
        f"Page URL: {_safe(payload.get('page_url'))}",
        "",
        f"Name: {_safe(payload.get('name'))}",
        f"Company: {_safe(payload.get('company'))}",
        f"Email: {_safe(payload.get('email'))}",
        f"Invoicing system: {_safe(payload.get('system'))}",
        f"Invoice volume/month: {_safe(payload.get('volume'))}",
        "",
        "Message:",
        _safe(payload.get("message")),
        "",
        "User Agent:",
        _safe(payload.get("user_agent")),
    ]
    return "\n".join(lines)


@app.get("/health")
def health():
    return jsonify({"ok": True, "ts": _now_iso()}), 200


@app.route("/api/lead", methods=["POST", "OPTIONS"])
def lead():
    # Explicit OPTIONS handling (preflight)
    if request.method == "OPTIONS":
        return ("", 204)

    # Require JSON
    bad = _require_json()
    if bad:
        return bad

    payload = request.get_json(silent=True) or {}

    # Minimal validation
    name = _safe(payload.get("name"))
    email = _safe(payload.get("email"))
    message = _safe(payload.get("message"))

    if not name or not email or not message:
        return jsonify(
            {
                "ok": False,
                "error": "Missing required fields",
                "required": ["name", "email", "message"],
            }
        ), 400

    # Verify server config
    if not SENDGRID_API_KEY:
        return jsonify({"ok": False, "error": "Server missing SENDGRID_API_KEY"}), 500
    if not FROM_EMAIL:
        return jsonify({"ok": False, "error": "Server missing FROM_EMAIL"}), 500
    if not SUPPORT_EMAIL:
        return jsonify({"ok": False, "error": "Server missing SUPPORT_EMAIL"}), 500

    subject = f"New lead: {name} ({email})"
    body_text = _build_email_body(payload)

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        mail = Mail(
            from_email=FROM_EMAIL,
            to_emails=SUPPORT_EMAIL,
            subject=subject,
            plain_text_content=body_text,
        )
        resp = sg.send(mail)

        # SendGrid commonly returns 202 Accepted on success
        if resp.status_code not in (200, 202):
            return jsonify(
                {
                    "ok": False,
                    "error": "SendGrid send failed",
                    "status_code": resp.status_code,
                }
            ), 502

        return jsonify({"ok": True, "ts": _now_iso()}), 200

    except Exception as e:
        return jsonify({"ok": False, "error": "Exception while sending email", "detail": str(e)}), 500


if __name__ == "__main__":
    # Local dev default port (Render will ignore this and use its own PORT env)
    port = int(os.getenv("PORT", "5055"))
    app.run(host="0.0.0.0", port=port, debug=True)
