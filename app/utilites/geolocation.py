# app/utilites/geolocation.py
from math import radians, sin, cos, sqrt, atan2
from typing import Optional

def haversine_distance(lat1: Optional[float], lon1: Optional[float],
                       lat2: Optional[float], lon2: Optional[float]) -> Optional[float]:
    """
    Return distance in kilometers between two lat/lon points using the Haversine formula.
    Returns None if any coordinate is missing.
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None

    R = 6371.0  # Earth radius in km

    # Convert to radians
    lat1_r = radians(lat1)
    lon1_r = radians(lon1)
    lat2_r = radians(lat2)
    lon2_r = radians(lon2)

    # Differences
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r

    a = sin(dlat / 2)** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2)** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance = R * c
    return distance  # in kilometers