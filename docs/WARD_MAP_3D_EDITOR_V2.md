# Ward Map 3D Editor V2 — incremental candidate (PARTIAL)

## Actual implementation
- A read-only simulation editor panel, reachable through Ward Map's `模拟编辑` toggle. Add a draft bed by selecting a room and free numbered grid slot; select any bed in Three.js to relocate/rotate/remove it from the *simulation only*; undo, redo, reset and leave editor.
- Stable fixed-size room footprint for up to 12 slots without shifting other rooms. Existing bed positions anchored by numbered slots; synthetic bed IDs are negative and cannot be passed to official API.
- Three.js scene accepts editor poses and renders simulated added/moved beds. Editor mode uses local target-room cutaway (occluding meshes within the target neighborhood, while preserving the surrounding building); existing scene raycast/hover/select, floors and status mapping are preserved.
- Editing intercepts scene bed clicks rather than invoking official bed management; detail view for simulation does not fetch patient status audit data.

## Explicitly NOT implemented / NOT VERIFIED
- Free-form drag/drop and animated translucent insertion preview; the current editor is grid slot-based controls, not Minecraft-like dragging.
- Formal DB create/archive/restore APIs, archive timestamp migration, idempotency, locking, audit and real MySQL concurrent tests. None are claimed; formal mode is NOT enabled. Do not try to translate negative synthetic IDs into official bed IDs.
- Persisted drafts, dynamic preview sandbox scoring on added virtual beds, changes to existing `ward_sandbox` API, or authentic clinical workflow writes.
- Full `vue-tsc` / Vite build, live Chromium WebGL or Windows E: repository integration (not accessible here).

## Tests actually executed
- `node frontend/verify_ward_editor.cjs`: 18/18 PASS. Checks add/move/rotation, slot collision, duplicate bed code, existing stable coordinates, undo/redo/removal and Vue script AST syntax.
- `PYTHONPATH=. pytest -q tests_ward_map/test_ward_map.py`: 7 PASS. No backend change in this package.

## Integration
This is based on the archived `Attention_Ward_Map_Spatial_Simulation_V1_Full_Candidate_20261015.zip`, not the live Windows worktree. Compare hashes and merge files semantically, especially WardScene3D.vue and WardMapView.vue; DO NOT blanket replace existing Windows sources. Formal storage is deferred pending real repository + MySQL migration review.
