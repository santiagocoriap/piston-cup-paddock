import pytest

from apps.catalog.game_facts import car_facts, fill_empty, layout_facts
from apps.catalog.models import Car

# The real formats of the installed mods differ a lot. Each case comes from a real ui_car.json.
CAR_SPECS = [
    (
        {"bhp": "584 whp", "torque": "505 Nm*", "weight": "1030kg", "topspeed": "215 mp/h"},
        (584, 505, 1030, 346),
    ),
    (
        {"bhp": "600+ bhp", "torque": "--Nm", "weight": "1,240 kg*", "topspeed": "320+km/h"},
        (600, None, 1240, 320),
    ),
    (
        {"bhp": "NaN bhp", "torque": "700 NM", "weight": "70kg", "topspeed": "--km/h"},
        (None, 700, 70, None),
    ),
    (
        {"bhp": "450_bhp", "torque": "_nm*", "weight": "xxx kg", "topspeed": "~305km/h"},
        (450, None, None, 305),
    ),
]


@pytest.mark.parametrize(("specs", "expected"), CAR_SPECS)
def test_the_car_numbers_come_from_many_text_formats(specs, expected):
    facts = car_facts({"specs": specs})
    assert (
        facts["power_hp"],
        facts["torque_nm"],
        facts["weight_kg"],
        facts["top_speed_kmh"],
    ) == expected
    # The original texts stay, for a value that the reader cannot use.
    assert facts["specs_text"]["bhp"] == specs["bhp"]


def test_a_car_gives_its_class_year_tags_curves_and_a_plain_description():
    facts = car_facts(
        {
            "brand": "Acura",
            "class": "LMDh",
            "country": "Japan",
            "year": 2023,
            "description": "Line one<br>Line <b>two</b> &amp; more",
            "tags": ["GTP", "", 3, "IMSA"],
            "url": "javascript:alert(1)",
            "specs": {"acceleration": "--s 0-100", "pwratio": "0.62 kg/hp"},
            "torqueCurve": [[0, 0], [1000, 400.123], ["x", 1], [2000]],
        }
    )
    assert (facts["brand"], facts["game_class"], facts["country"], facts["year"]) == (
        "Acura",
        "LMDh",
        "Japan",
        2023,
    )
    assert facts["description"] == "Line one\nLine two & more"
    assert facts["tags"] == ["GTP", "IMSA"]
    assert facts["url"] == ""  # Only a web address is kept.
    assert (facts["acceleration"], facts["power_to_weight"]) == ("", "0.62 kg/hp")
    assert facts["torque_curve"] == [[0.0, 0.0], [1000.0, 400.12]]


def test_a_layout_gives_its_size_place_direction_and_position():
    facts = layout_facts(
        {
            "length": "5.200 km",
            "width": "12",
            "pitboxes": "30",
            "run": "Counter Clockwise",
            "city": "Monza",
            "geotags": ["45.6156 N", "9.2811 E"],
            "year": "1922",
        }
    )
    assert (facts["length_m"], facts["width_m"], facts["pit_boxes"]) == (5200, 12, 30)
    assert (facts["direction"], facts["city"], facts["year"]) == ("anticlockwise", "Monza", 1922)
    assert (facts["latitude"], facts["longitude"]) == (45.6156, 9.2811)
    west = layout_facts({"geotags": ["51.5 N", "1.25 W"], "run": "clockwise"})
    assert (west["longitude"], west["direction"]) == (-1.25, "clockwise")
    assert layout_facts({"geotags": ["lat", "lon"]})["latitude"] is None


@pytest.mark.django_db
def test_the_game_files_fill_only_empty_fields():
    car = Car.objects.create(key="acura", name="Acura", brand="Honda", power_hp=None)
    changed = fill_empty(car, car_facts({"brand": "Acura", "specs": {"bhp": "584 whp"}}))
    assert changed == ["power_hp", "specs_text"]
    assert (car.brand, car.power_hp) == ("Honda", 584)


def test_an_admin_edits_the_facts_and_a_null_clears_one(api, champ_admin, layout, car):
    client = api(champ_admin).client
    response = client.patch(
        f"/api/catalog/cars/{car.id}",
        {"power_hp": 520, "brand": " Acura ", "tags": ["LMDh"], "url": "https://acura.com"},
        content_type="application/json",
    )
    assert response.status_code == 200, response.json()
    data = response.json()
    assert (data["name"], data["power_hp"], data["brand"], data["tags"]) == (
        "Acura ARX-06",
        520,
        "Acura",
        ["LMDh"],
    )
    cleared = client.patch(
        f"/api/catalog/cars/{car.id}", {"power_hp": None}, content_type="application/json"
    )
    assert cleared.json()["power_hp"] is None

    bad = client.patch(
        f"/api/catalog/cars/{car.id}", {"url": "javascript:x"}, content_type="application/json"
    )
    assert bad.status_code == 422
    layout_response = client.patch(
        f"/api/catalog/layouts/{layout.id}",
        {"direction": "anticlockwise", "width_m": 12, "latitude": 56.0},
        content_type="application/json",
    )
    assert layout_response.json()["direction"] == "anticlockwise"
    assert layout_response.json()["name"] == "Long"
