"""Hostel: people are located by hostel only, never by live GPS (privacy)."""
import math

from models.errors import ValidationError


class Hostel:
    EARTH_RADIUS_KM = 6371.0088

    def __init__(self, name, latitude, longitude):
        if not str(name).strip():
            raise ValidationError("A hostel needs a name.")
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValidationError("Latitude/longitude out of range.")
        self._name = str(name).strip()
        self._latitude = float(latitude)
        self._longitude = float(longitude)

    @property
    def name(self):
        return self._name

    @property
    def latitude(self):
        return self._latitude

    @property
    def longitude(self):
        return self._longitude

    def distance_to(self, other):
        """Great-circle distance in km (haversine formula)."""
        p1, p2 = math.radians(self._latitude), math.radians(other.latitude)
        dphi = p2 - p1
        dlam = math.radians(other.longitude - self._longitude)
        a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
        return 2 * self.EARTH_RADIUS_KM * math.asin(math.sqrt(a))

    def __eq__(self, other):
        return isinstance(other, Hostel) and other.name == self.name

    def __hash__(self):
        return hash(self._name)

    def __repr__(self):
        return f"Hostel({self._name!r})"
