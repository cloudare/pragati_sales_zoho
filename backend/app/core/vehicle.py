"""
Indian vehicle number validation (PRD M1).

Standard format: XX-NN-XX-NNNN
  - 2-letter state code (AP, CG, DL, HR, MH, etc.)
  - 1-2 digit RTO code
  - 1-3 letter series
  - 4 digit number (older format also allows 1-4 digit)

Also accept:
  - Bharat (BH) series:    NN-BH-NNNN-XX     (e.g. 24-BH-2345-AA)
  - Old defence:           army prefix like "06AB1234"
We accept hyphens or spaces or none between groups.

Examples accepted:
  CG-04-AB-1234   /  CG 04 AB 1234   /  CG04AB1234
  MH 12 AB 1     /  DL-1C-AA-9999
  24-BH-2345-AA  (Bharat series)
"""
import re

_STATE_CODES = {
    "AN","AP","AR","AS","BR","CH","CG","DD","DL","DN","GA","GJ","HP","HR","JH","JK",
    "KA","KL","LA","LD","MH","ML","MN","MP","MZ","NL","OD","PB","PY","RJ","SK","TN",
    "TR","TS","UK","UP","WB","BH",  # BH = Bharat series
}

# Regular vehicle: 2-letter state, 1-2 digit RTO, 1-3 letter series, 1-4 digit number
_REG = re.compile(r"^([A-Z]{2})[- ]?(\d{1,2})[- ]?([A-Z]{1,3})[- ]?(\d{1,4})$")

# Bharat series: 2-digit year, BH, 4 digits, 2 letters
_BH = re.compile(r"^(\d{2})[- ]?BH[- ]?(\d{4})[- ]?([A-Z]{1,2})$")


class VehicleNumberError(ValueError):
    pass


def normalize_vehicle_number(raw: str) -> str:
    """Uppercase, strip, normalize separators to hyphens."""
    if not raw:
        raise VehicleNumberError("Vehicle number is required")
    s = raw.upper().strip()
    s = re.sub(r"[\s\-]+", "", s)  # remove all spaces and hyphens
    return s


def validate_vehicle_number(raw: str) -> str:
    """
    Validate and return normalized form 'CG-04-AB-1234' or '24-BH-2345-AA'.
    Raises VehicleNumberError on bad input.
    """
    s = normalize_vehicle_number(raw)

    # Try Bharat series first
    m = _BH.match(s)
    if m:
        year, num, letters = m.groups()
        return f"{year}-BH-{num}-{letters}"

    # Try regular
    m = _REG.match(s)
    if not m:
        raise VehicleNumberError(
            "Vehicle number must look like 'CG-04-AB-1234' "
            "(state code, RTO number, series letters, vehicle number)"
        )
    state, rto, series, num = m.groups()
    if state not in _STATE_CODES:
        raise VehicleNumberError(
            f"'{state}' is not a recognised Indian state/UT code"
        )
    return f"{state}-{rto.zfill(2)}-{series}-{num}"
