"""Determininistic simulated room/bed geometry; never use scoring coordinates as physical floorplan."""
from __future__ import annotations
from collections import defaultdict
from app.schemas.ward_map import Position


def simulated_positions(rooms_and_beds: list[tuple[int, int, str, str, int, str]]) -> tuple[dict[int, Position], dict[int, Position]]:
    """Input: (bed_id, ward_id, building, ward_code, floor, bed_code).

    Scene geometry is stable for a full building/floor and independent of API filters.
    Each ward gets a 10×8 unit room, in three columns; beds inside are in rows of 4.
    Large rooms extend vertically to avoid overlapping neighboring rooms.
    """
    by_floor: dict[tuple[str, int], dict[int, list[tuple[int, str]]]] = defaultdict(lambda: defaultdict(list))
    ward_codes: dict[int, str] = {}
    for bed_id, ward_id, building, ward_code, floor, bed_code in rooms_and_beds:
        by_floor[(building, floor)][ward_id].append((bed_id, bed_code))
        ward_codes[ward_id] = ward_code
    room_positions: dict[int, Position] = {}
    bed_positions: dict[int, Position] = {}
    floor_offset_z = 0.0
    for key, wards in sorted(by_floor.items()):
        ids = sorted(wards, key=lambda w: (ward_codes[w], w))
        # 3 columns. Vertical pitch depends on max bed count to fit crowded wards.
        row_pitch = max(11.0, 3.25 * max((len(items) + 3) // 4 for items in wards.values()) + 5.5)
        for idx, wid in enumerate(ids):
            base_x, base_z = (idx % 3) * 12.5, floor_offset_z + (idx // 3) * row_pitch
            room_positions[wid] = Position(x=base_x, z=base_z)
            for bidx, (bid, _) in enumerate(sorted(wards[wid], key=lambda p: (p[1], p[0]))):
                # Relative to top-left corner of a room of width 10 and height row_pitch-2
                bed_positions[bid] = Position(x=base_x + 1.15 + (bidx % 4) * 2.35,
                                              z=base_z + 1.65 + (bidx // 4) * 3.25)
        floor_offset_z += ((len(ids) + 2) // 3) * row_pitch + 5.0
    return room_positions, bed_positions
