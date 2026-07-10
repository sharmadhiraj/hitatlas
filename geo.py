import geoip2.database
import geoip2.errors


def geolocate(reader: geoip2.database.Reader, ip: str) -> dict[str, object] | None:
    try:
        city = reader.city(ip)
    except geoip2.errors.AddressNotFoundError:
        return None

    if city.location.latitude is None or city.location.longitude is None:
        return None

    return {
        "ip": ip,
        "lat": city.location.latitude,
        "lng": city.location.longitude,
        "city": city.city.name,
        "country": city.country.iso_code,
    }
