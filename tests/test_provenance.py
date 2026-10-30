import io

import piexif
from PIL import Image

from app.analysis import provenance


def jpeg_with_exif() -> bytes:
    image = Image.new("RGB", (640, 480), "navy")
    exif = {
        "0th": {
            piexif.ImageIFD.Make: "Test Camera",
            piexif.ImageIFD.Model: "Test Model",
            piexif.ImageIFD.Software: "Test Software",
        },
        "Exif": {piexif.ExifIFD.DateTimeOriginal: "2026:10:30 12:00:00"},
        "GPS": {
            piexif.GPSIFD.GPSLatitude: ((12, 1), (34, 1), (56, 1)),
            piexif.GPSIFD.GPSLongitude: ((77, 1), (12, 1), (3, 1)),
        },
    }
    output = io.BytesIO()
    image.save(output, "JPEG", exif=piexif.dump(exif), quality=60)
    return output.getvalue()


def test_provenance_redacts_gps_coordinates_and_reads_context():
    raw = jpeg_with_exif()
    image = Image.open(io.BytesIO(raw))
    result = provenance(image, raw)
    assert result["camera_make"] == "Test Camera"
    assert result["camera_model"] == "Test Model"
    assert result["location_data_present"] is True
    assert "latitude" not in result
    assert "longitude" not in result
    assert result["jpeg_quality_estimate"] is not None


def test_missing_thumbnail_is_explicit():
    image = Image.new("RGB", (640, 480), "white")
    output = io.BytesIO()
    image.save(output, "JPEG")
    raw = output.getvalue()
    assert provenance(Image.open(io.BytesIO(raw)), raw)["embedded_thumbnail"] == "absent"


def test_low_quality_jpeg_has_quality_estimate():
    image = Image.new("RGB", (640, 480), "white")
    output = io.BytesIO()
    image.save(output, "JPEG", quality=30)
    result = provenance(Image.open(io.BytesIO(output.getvalue())), output.getvalue())
    assert result["jpeg_quality_estimate"] < 60
