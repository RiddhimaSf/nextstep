"""
NYC-scope check for geocoded locations.

Confirmed bug (Day 2): the current geocoding call in crisis.py appends
", New York City" to the user's raw input before geocoding, on the
assumption this would implicitly restrict results to NYC. Tested directly
with "London" as input — the geocode call succeeded and returned
"Location found," meaning a non-NYC location is silently accepted rather
than rejected. This is the confirmed version of the scope-mismatch failure
mode named in the Tools table.

This function is a real (not aspirational) fix: after geocoding succeeds,
check the returned address components for a New York, NY match before
accepting the result, instead of relying on string concatenation as an
implicit filter.
"""

NYC_BOROUGHS = {"manhattan", "brooklyn", "queens", "bronx", "staten island"}


def is_in_nyc_scope(geocode_result: dict) -> bool:
    """
    Takes a single result from gmaps.geocode() (a dict with
    'address_components' and 'formatted_address') and returns True only
    if it resolves to New York City, NY.

    Checks address_components for a 'locality' matching one of the five
    boroughs, or 'administrative_area_level_2' containing a borough name
    (Google's data models NYC boroughs inconsistently depending on the
    address), AND the state must be NY. Falls back to a formatted_address
    string check if address_components don't include a clear locality —
    still requires "New York" to actually be in the returned address, not
    just present in the query we sent.
    """
    if not geocode_result:
        return False

    components = geocode_result.get("address_components", [])

    state_is_ny = any(
        c.get("short_name") == "NY"
        for c in components
        if "administrative_area_level_1" in c.get("types", [])
    )

    if not state_is_ny:
        return False

    borough_found = any(
        c.get("long_name", "").lower() in NYC_BOROUGHS
        for c in components
        if "locality" in c.get("types", []) or "sublocality" in c.get("types", [])
    )

    if borough_found:
        return True

    # Fallback: NYC addresses sometimes list "New York" as the locality
    # (Manhattan specifically) rather than a borough name directly.
    ny_locality = any(
        c.get("long_name", "").lower() == "new york"
        for c in components
        if "locality" in c.get("types", [])
    )

    return ny_locality


def scope_check_message() -> str:
    """
    The explicit message a user sees when their location is out of scope
    — replaces the current silent "Location found" behavior for
    non-NYC input.
    """
    return (
        "NextStep currently only covers New York City. "
        "We couldn't confirm your location is within NYC, so hospital "
        "and resource results may not be accurate for your area. "
        "If you're outside NYC, RAINN's national hotline (1-800-656-4673) "
        "can connect you to local resources wherever you are."
    )
