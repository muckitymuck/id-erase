"""CCPA and GDPR deletion request letter templates.

Templates use Python string.Template syntax ($variable or ${variable}).
All PII fields are injected at render time from the decrypted profile.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from string import Template
from typing import Any

CCPA_DELETION_TEMPLATE = Template("""\
$full_name
$address_line
$city_state_zip

$date

$broker_name
$broker_address

Re: Request to Delete Personal Information Under the California Consumer Privacy Act (CCPA)

Dear $broker_name Privacy Team,

I am writing to exercise my rights under the California Consumer Privacy Act \
(Cal. Civ. Code § 1798.100 et seq.) to request the deletion of any and all \
personal information your organization has collected, stored, or sold about me.

My identifying information:
- Full Name: $full_name
$aliases_line\
$dob_line\
- Email: $email
$phone_line\
$address_block

I request that you:
1. Delete all personal information you have collected about me.
2. Direct any service providers with whom you have shared my personal \
information to delete my data as well.
3. Confirm the completion of this deletion within 45 days, as required by the CCPA.

If you are unable to verify my identity, please contact me at the email \
address provided above, and I will provide additional verification as needed.

Please note that under the CCPA, you may not discriminate against me for \
exercising my privacy rights.

Sincerely,

$full_name
$email
""")

GDPR_ERASURE_TEMPLATE = Template("""\
$full_name
$address_line
$city_state_zip

$date

$broker_name
$broker_address

Re: Request for Erasure of Personal Data Under Article 17 of the General Data \
Protection Regulation (GDPR)

Dear Data Protection Officer,

I am writing to request the erasure of my personal data that your organisation \
holds, pursuant to Article 17 of the General Data Protection Regulation (EU) \
2016/679.

My identifying information:
- Full Name: $full_name
$aliases_line\
$dob_line\
- Email: $email
$phone_line\
$address_block

I request that you erase all personal data relating to me without undue delay. \
Under Article 17(1), you are required to do so where one of the following \
grounds applies:

(a) the personal data are no longer necessary in relation to the purposes for \
which they were collected or otherwise processed;
(b) I withdraw my consent on which the processing is based;
(d) the personal data have been unlawfully processed;
(f) the personal data have to be erased for compliance with a legal obligation.

If you have made my personal data public, I also request that you take \
reasonable steps, including technical measures, to inform other controllers \
processing the data that I have requested the erasure of any links to, or \
copies or replications of, that data (Article 17(2)).

Please respond to this request within one month, as required by Article 12(3). \
If you do not comply, I reserve the right to lodge a complaint with the \
relevant supervisory authority.

Yours faithfully,

$full_name
$email
""")

AVAILABLE_TEMPLATES: dict[str, Template] = {
    "ccpa_deletion": CCPA_DELETION_TEMPLATE,
    "gdpr_erasure": GDPR_ERASURE_TEMPLATE,
}


@dataclass
class RenderedLetter:
    template_id: str
    subject: str
    body: str
    recipient_name: str
    recipient_address: str


def _format_address_block(addresses: list[dict[str, Any]]) -> str:
    """Build a multi-line address block from profile addresses."""
    if not addresses:
        return ""
    lines = []
    for addr in addresses:
        if not isinstance(addr, dict):
            continue
        parts = []
        if addr.get("street"):
            parts.append(str(addr["street"]))
        city_state = []
        if addr.get("city"):
            city_state.append(str(addr["city"]))
        if addr.get("state"):
            city_state.append(str(addr["state"]))
        if city_state:
            cs = ", ".join(city_state)
            if addr.get("zip"):
                cs += f" {addr['zip']}"
            parts.append(cs)
        if parts:
            lines.append("; ".join(parts))
    if not lines:
        return ""
    header = "- Address(es):\n"
    return header + "\n".join(f"  - {line}" for line in lines) + "\n"


def render_letter(
    template_id: str,
    profile_data: dict[str, Any],
    broker_name: str,
    broker_address: str = "",
) -> RenderedLetter:
    """Render a legal letter template with profile data.

    Args:
        template_id: One of 'ccpa_deletion' or 'gdpr_erasure'.
        profile_data: Decrypted PII profile dict.
        broker_name: The data broker's name.
        broker_address: The broker's mailing/legal address.

    Returns:
        RenderedLetter with the filled template.
    """
    template = AVAILABLE_TEMPLATES.get(template_id)
    if template is None:
        raise ValueError(f"Unknown template: {template_id}. Available: {list(AVAILABLE_TEMPLATES.keys())}")

    full_name = profile_data.get("full_name", "")
    addresses = profile_data.get("addresses") or []
    current = [a for a in addresses if isinstance(a, dict) and a.get("current")]
    primary = current[0] if current else (addresses[0] if addresses else {})

    address_line = primary.get("street", "") if isinstance(primary, dict) else ""
    city_parts = []
    if isinstance(primary, dict):
        if primary.get("city"):
            city_parts.append(str(primary["city"]))
        if primary.get("state"):
            city_parts.append(str(primary["state"]))
    city_state = ", ".join(city_parts)
    zip_code = primary.get("zip", "") if isinstance(primary, dict) else ""
    city_state_zip = f"{city_state} {zip_code}".strip() if city_state else ""

    aliases = profile_data.get("aliases") or []
    aliases_line = f"- Also known as: {', '.join(aliases)}\n" if aliases else ""

    dob = profile_data.get("date_of_birth")
    dob_line = f"- Date of Birth: {dob}\n" if dob else ""

    emails = profile_data.get("email_addresses") or []
    email = emails[0] if emails else ""

    phones = profile_data.get("phone_numbers") or []
    phone_numbers = [p.get("number", str(p)) if isinstance(p, dict) else str(p) for p in phones]
    phone_line = f"- Phone: {', '.join(phone_numbers)}\n" if phone_numbers else ""

    address_block = _format_address_block(addresses)

    subject_map = {
        "ccpa_deletion": f"CCPA Deletion Request — {full_name}",
        "gdpr_erasure": f"GDPR Erasure Request — {full_name}",
    }

    body = template.safe_substitute(
        full_name=full_name,
        address_line=address_line,
        city_state_zip=city_state_zip,
        date=date.today().isoformat(),
        broker_name=broker_name,
        broker_address=broker_address or "[Address Not Available]",
        aliases_line=aliases_line,
        dob_line=dob_line,
        email=email,
        phone_line=phone_line,
        address_block=address_block,
    )

    return RenderedLetter(
        template_id=template_id,
        subject=subject_map.get(template_id, f"Data Deletion Request — {full_name}"),
        body=body,
        recipient_name=broker_name,
        recipient_address=broker_address,
    )
