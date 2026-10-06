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


class LocationSmoother:
    """
    Wraps get_location_context() to avoid flickering room labels when the
    robot's position sits near a room boundary.

    The raw reading has to repeat N times in a row (including "unknown",
    which is tracked the same way as any real room) before it replaces the
    currently confirmed room. A brief flip to some other reading resets the
    streak, so a doorway blip or a single bad localization update doesn't
    change what gets reported.
    """

    def __init__(self, n: int = 3):
        self.n = n
        self.confirmed = {"room_label": "unknown", "room_type": "unknown"}
        self.candidate_key = None
        self.candidate_count = 0

    def update(self, x: float, y: float) -> dict:
        raw = get_location_context(x, y)
        raw_key = (raw["room_label"], raw["room_type"])
        confirmed_key = (self.confirmed["room_label"], self.confirmed["room_type"])

        if raw_key == confirmed_key:
            # Matches what's already confirmed, nothing is "becoming" new.
            self.candidate_key = None
            self.candidate_count = 0
        else:
            if raw_key == self.candidate_key:
                self.candidate_count += 1
            else:
                # Flipped to a different reading than the one we were
                # counting, so the streak starts over.
                self.candidate_key = raw_key
                self.candidate_count = 1

            if self.candidate_count >= self.n:
                self.confirmed = {
                    "room_label": raw["room_label"],
                    "room_type": raw["room_type"],
                }
                self.candidate_key = None
                self.candidate_count = 0

        confidence = "low" if self.confirmed["room_label"] == "unknown" else "high"
        result = dict(self.confirmed)
        result["confidence"] = confidence
        return result


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

    # --- LocationSmoother checks ---------------------------------------
    print()
    print("LocationSmoother checks (N=3):")

    def check(condition, description):
        print(f"{'PASS' if condition else 'FAIL'}: {description}")

    smoother = LocationSmoother(n=3)
    library_pt = (2.0, 2.0)
    hallway_pt = (7.0, 1.0)
    lab_pt = (7.0, 5.0)
    unknown_pt = (50.0, 50.0)

    # Prime the smoother: 3 consecutive library readings confirm "library".
    for _ in range(3):
        result = smoother.update(*library_pt)
    check(
        result["room_label"] == "library" and result["confidence"] == "high",
        "3 consecutive library readings confirm library (confidence high)",
    )

    # A single reading in a different room should not flip the label yet.
    result = smoother.update(*hallway_pt)
    check(
        result["room_label"] == "library",
        "a single off-room reading does not change the confirmed label",
    )

    # Back to the confirmed room resets the candidate streak.
    smoother.update(*library_pt)

    # N consecutive hallway readings now should change the confirmed room.
    for _ in range(2):
        result = smoother.update(*hallway_pt)
    check(
        result["room_label"] == "library",
        "2 consecutive off-room readings (below N) still do not change the label",
    )
    result = smoother.update(*hallway_pt)
    check(
        result["room_label"] == "hallway" and result["confidence"] == "high",
        "N consecutive readings in the new room does change the label",
    )

    # Brief back-and-forth across a boundary should not flip the label.
    for pt in (lab_pt, hallway_pt, lab_pt, hallway_pt):
        result = smoother.update(*pt)
    check(
        result["room_label"] == "hallway",
        "a brief jump back and forth across a boundary does not flip the label",
    )

    # A single unknown reading should not wipe out a good label.
    result = smoother.update(*unknown_pt)
    check(
        result["room_label"] == "hallway" and result["confidence"] == "high",
        "a single unknown reading does not change a known label",
    )

    # N consecutive unknown readings should change the label to unknown,
    # and confidence should drop to "low".
    for _ in range(2):
        result = smoother.update(*unknown_pt)
    check(
        result["room_label"] == "unknown" and result["confidence"] == "low",
        "N consecutive unknown readings change the label to unknown (confidence low)",
    )