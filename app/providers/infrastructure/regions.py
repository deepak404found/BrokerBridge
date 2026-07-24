"""Common Vultr-style region codes and typo aliases for infra config."""

from __future__ import annotations

# Lab + frequent Vultr metro codes (not exhaustive of Vultr's catalog).
COMMON_REGIONS: frozenset[str] = frozenset(
    {
        "ewr",
        "ord",
        "dfw",
        "sea",
        "lax",
        "atl",
        "mia",
        "sjc",
        "ams",
        "lhr",
        "fra",
        "nrt",
        "syd",
        "sgp",
        "icn",
        "yto",
        "mex",
        "sao",
        "mad",
        "waw",
        "sto",
    }
)

# Common typos / legacy names → preferred code.
REGION_ALIASES: dict[str, str] = {
    "eur": "ewr",  # typo for Newark (ewr), not a Vultr region
    "nyc": "ewr",  # legacy / colloquial New York → Newark
    "ny": "ewr",
    "newyork": "ewr",
    "chicago": "ord",
    "london": "lhr",
    "amsterdam": "ams",
    "frankfurt": "fra",
}

_EXAMPLES = "ewr, ord, lax, ams, fra, lhr, sjc"


def normalize_region(raw: str | None) -> tuple[str | None, str | None]:
    """Return (normalized_region, error_message).

    Empty / None → (None, None). Known alias → remapped code.
    Unknown → (None, clear validation message).
    """
    if raw is None:
        return None, None
    region = str(raw).strip().lower()
    if not region:
        return None, None
    if region in REGION_ALIASES:
        return REGION_ALIASES[region], None
    if region in COMMON_REGIONS:
        return region, None
    hint = ""
    if region.startswith("eu") or region in {"europe", "eu"}:
        hint = " Did you mean 'ewr' (Newark)?"
    return (
        None,
        f"Unknown region '{raw}'. Use a Vultr-style code such as {_EXAMPLES}.{hint}",
    )
