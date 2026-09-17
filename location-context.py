"""
Location context for robot conversation initiation.

Takes the robot's live x, y position and matches it against a map of
labeled rooms to produce the "location" block of the context JSON:
{
  "room_label": "library",
  "room_type": "quiet_zone"
}
"""

# Each room is defined by a rectangle: x_min, x_max, y_min, y_max, in
# the same map frame the robot's localization system reports. Replace
# these fake values with your building's real coordinates once you
# have them.
ROOMS = [
    {
        "room_label": "library",
        "room_type": "quiet_zone",
        "x_min": 0.0,
        "x_max": 5.0,
        "y_min": 0.0,
        "y_max": 5.0,
    },
    {
        "room_label": "hallway",
        "room_type": "transit_space",
        "x_min": 5.0,
        "x_max": 10.0,
        "y_min": 0.0,
        "y_max": 2.0,
    },
    {
        "room_label": "lab",
        "room_type": "work_space",
        "x_min": 5.0,
        "x_max": 10.0,
        "y_min": 2.0,
        "y_max": 8.0,
    },
    {
        "room_label": "kitchen",
        "room_type": "social_space",
        "x_min": 0.0,
        "x_max": 5.0,
        "y_min": 5.0,
        "y_max": 8.0,
    },
]


def get_location_context(x: float, y: float) -> dict:
    """
    Match an (x, y) position to a room.

    x, y: the robot's current position in the map frame
    Returns a dict with room_label and room_type. If no room matches,
    returns "unknown" for both, so the caller always gets a usable dict.
    """
    for room in ROOMS:
        if room["x_min"] <= x <= room["x_max"] and room["y_min"] <= y <= room["y_max"]:
            return {
                "room_label": room["room_label"],
                "room_type": room["room_type"],
            }

    return {"room_label": "unknown", "room_type": "unknown"}


if __name__ == "__main__":
    # quick manual test with fake positions
    test_points = [
        (2.0, 2.0),   # should land in library
        (7.0, 1.0),   # should land in hallway
        (7.0, 5.0),   # should land in lab
        (2.0, 6.0),   # should land in kitchen
        (50.0, 50.0), # should land in unknown, outside every room
    ]

    for x, y in test_points:
        result = get_location_context(x, y)
        print(f"({x}, {y}) -> {result}")