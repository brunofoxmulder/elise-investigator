from __future__ import annotations

from typing import Any, Literal

FactorRole = Literal["cause", "precondition", "guard"]

# Only these fields may cross the Investigator -> language-layer boundary.
# Internal proof identifiers (entity_id, trace path, automation/script ids, raw HA
# trigger/config data, etc.) deliberately stay private to Investigator.
_PUBLIC_FACTOR_KEYS = (
    "kind",
    "role",
    "label",
    "relation",
    "value",
    "threshold",
    "unit",
    "duration",
    "business_label",
)


def structured_factor(
    *,
    kind: str,
    role: FactorRole,
    proven: bool,
    label: str | None = None,
    relation: str | None = None,
    value: Any = None,
    threshold: Any = None,
    unit: str | None = None,
    duration: str | None = None,
    business_label: str | None = None,
    **proof: Any,
) -> dict[str, Any]:
    """Build one causal factor without confusing proof and wording.

    ``role`` is intentionally explicit:
      - ``cause``: necessary functional factor that may be stated to the user;
      - ``precondition``: true context required by the branch but not a reason by
        itself;
      - ``guard``: safety/authorization constraint that must not be promoted to a
        user-facing cause automatically.

    ``business_label`` is optional metadata supplied by an automation author. It
    can name a proven factor in human terms, but it never makes an unproven factor
    true and never changes its role.

    Extra keyword arguments are retained as private proof material. They are
    stored in Investigator but removed from the language-layer payload.
    """

    factor: dict[str, Any] = {
        "kind": str(kind),
        "role": role,
        "proven": bool(proven),
    }
    optional = {
        "label": label,
        "relation": relation,
        "value": value,
        "threshold": threshold,
        "unit": unit,
        "duration": duration,
        "business_label": business_label,
    }
    factor.update({key: value for key, value in optional.items() if value is not None})
    factor.update(proof)
    return factor


def public_causal_factors(factors: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return only proven functional causes safe for a language model.

    The language layer may reformulate established causes but must not decide
    causality. Unproven factors, preconditions and guards are therefore withheld.
    Private proof fields are also stripped even when the factor is exposed.
    """

    public: list[dict[str, Any]] = []
    for raw in factors or []:
        if not isinstance(raw, dict):
            continue
        if raw.get("proven") is not True or raw.get("role") != "cause":
            continue

        item = {key: raw[key] for key in _PUBLIC_FACTOR_KEYS if raw.get(key) is not None}
        if not item.get("kind"):
            continue
        # ``role`` remains visible so the contract is self-describing. At this
        # boundary it is always "cause" by construction.
        item["role"] = "cause"
        public.append(item)
    return public
