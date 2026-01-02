import os
import re
import json
from datetime import datetime, timezone

from flask import Flask, request, jsonify
import sendgrid
from sendgrid.helpers.mail import Mail

app = Flask(__name__)

# -------------------------
# Config (ENV VARS REQUIRED)
# -------------------------
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@getinvoicechaser.com")
FROM_EMAIL = os.getenv("FROM_EMAIL", "support@getinvoicechaser.com")  # must be verified in SendGrid
ALLOW_ORIGIN = os.getenv("ALLOW_ORIGIN", "*")  # set to your github pages domain in production
LOG_PATH = os.getenv("LEAD_LOG_PATH", os.path.join(os.path.dirname(__file__), "leads.log"))

if not SENDGRID_API_KEY:
    print("[WARN] SENDGRID_API_KEY is not set. /api/lead will fail until set.")


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": ALLOW_ORIGIN,
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
    }


def _is_valid_email(email: str) -> bool:
    if not email:
        return False
    # simple sanity check
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()) is not None


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "ts": datetime.now(timezone.utc).isoformat()}), 200


@app.route("/api/lead", methods=["OPTIONS"])
def lead_options():
    return ("", 204, _cors_headers())


@app.route("/api/lead", methods=["POST"])
def lead():
    try:
        data = request.get_json(force=True, silent=False)
    except Exception:
        return (jsonify({"ok": False, "error": "Invalid JSON"}), 400, _cors_headers())

    name = (data.get("name") or "").strip()
    company = (data.get("company") or "").strip()
    work_email = (data.get("work_email") or "").strip()
    invoicing_system = (data.get("invoicing_system") or "").strip()
    invoice_volume = (data.get("invoice_volume") or "").strip()
    headache = (data.get("headache") or "").strip()

    # Basic validation
    if not name or not work_email:
        return (jsonify({"ok": False, "error": "Missing required fields: name, work_email"}), 400, _cors_headers())
    if not _is_valid_email(work_email):
        return (jsonify({"ok": False, "error": "Invalid email format"}), 400, _cors_headers())

    payload = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "name": name,
        "company": company,
        "work_email": work_email,
        "invoicing_system": invoicing_system,
        "invoice_volume": invoice_volume,
        "headache": headache,
        "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
        "user_agent": request.headers.get("User-Agent", ""),
    }

    # Always log locally too (helps debugging + evidence)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception as e:
        print(f"[WARN] Failed to write lead log: {e}")

    # Send email to support
    try:
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)

        subject = f"[InvoiceChaser Lead] {name}" + (f" @ {company}" if company else "")
        body_lines = [
            "New lead submission from website:",
            "",
            f"Name: {name}",
            f"Company: {company or '(blank)'}",
            f"Work Email: {work_email}",
            f"Current Invoicing System: {invoicing_system or '(blank)'}",
            f"Approx. Invoices / Month: {invoice_volume or '(blank)'}",
            "",
            "Biggest headache:",
            headache or "(blank)",
            "",
            f"Timestamp (UTC): {payload['ts_utc']}",
            f"IP: {payload['ip']}",
        ]
        content = "\n".join(body_lines)

        message = Mail(
            from_email=FROM_EMAIL,
            to_emails=SUPPORT_EMAIL,
            subject=subject,
            plain_text_content=content,
        )

        sg.send(message)

    except Exception as e:
        return (jsonify({"ok": False, "error": f"Send failed: {str(e)}"}), 500, _cors_headers())

    return (jsonify({"ok": True, "message": "Submitted successfully"}), 200, _cors_headers())


if __name__ == "__main__":
    # Local dev
    app.run(host="127.0.0.1", port=5055, debug=True)
