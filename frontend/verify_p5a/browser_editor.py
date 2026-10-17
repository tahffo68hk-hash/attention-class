"""P5-A 真实 Chromium WebGL 验收 —— 批次 A v4。

改进：
1) 进入「单层聚焦 1F」，避免上层瓦片在正交投影下插到拾取射线上（真实几何遮挡，不是缺陷）；
2) 每次点击前用页面内 `pickSlot()` 反查落点，确保点击命中的就是目标瓦片；
3) 移动流程显式读取 WardMapView.selected，确认「先选源、再点目标」链路。
"""
import subprocess
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import helpers as abtool  # noqa: E402

BASE = abtool.BASE
SHOT = abtool.SHOT
NODE = abtool.NODE

PRELUDE = r"""
const findComp = (name) => {
  const app = document.querySelector('#app').__vue_app__;
  const seen = new Set();
  let hit = null;
  const walk = (v) => {
    if (!v || hit || seen.has(v)) return;
    seen.add(v);
    const n = v.type && (v.type.__name || v.type.name);
    if (n === name && v.component) { hit = v.component; return; }
    if (v.component) walk(v.component.subTree);
    if (Array.isArray(v.children)) for (const c of v.children) if (c && typeof c === 'object') walk(c);
  };
  walk(app._instance.subTree);
  return hit;
};
const unref = (v) => (v && typeof v === 'object' && !v.isScene && !v.isCamera && !v.isObject3D && 'value' in v) ? v.value : v;
const sceneSt = () => findComp('WardScene3D').setupState;
const canvas = () => document.querySelector('.wm-stage canvas');
const btn = (t) => Array.from(document.querySelectorAll('button')).find((b) => b.textContent.trim() === t)
  || Array.from(document.querySelectorAll('button')).find((b) => b.textContent.trim().includes(t));
const tilesOf = () => {
  const st = sceneSt();
  const list = unref(st.slotTargets) || [];
  const cam = unref(st.camera);
  const r = canvas().getBoundingClientRect();
  const V = list.length ? list[0].position.constructor : null;
  if (!V) return [];
  return list.filter((m) => m.visible).map((m) => {
    const p = m.getWorldPosition(new V()).project(cam);
    return { mesh: m, wardId: m.userData.wardId, slot: m.userData.slot, kind: m.userData.kind, bedId: m.userData.bedId,
      x: r.left + ((p.x + 1) / 2) * r.width, y: r.top + ((1 - p.y) / 2) * r.height };
  });
};
const aim = (tile) => {
  const st = sceneSt();
  const cands = [[0, 0]];
  for (let rad = 3; rad <= 21; rad += 3) for (let a = 0; a < 12; a++) cands.push([Math.cos(a * Math.PI / 6) * rad, Math.sin(a * Math.PI / 6) * rad]);
  for (const [dx, dy] of cands) {
    const x = tile.x + dx, y = tile.y + dy;
    const m = st.pickSlot({ clientX: x, clientY: y });
    if (m === tile.mesh) return { x: Math.round(x), y: Math.round(y), off: Math.round(Math.hypot(dx, dy)) };
  }
  return null;
};
const fire = (pt, kind) => {
  const c = canvas();
  const base = { bubbles: true, cancelable: true, composed: true, pointerId: 1, pointerType: 'mouse', isPrimary: true, button: 0, clientX: pt.x, clientY: pt.y };
  if (kind !== 'down') c.dispatchEvent(new PointerEvent('pointermove', Object.assign({}, base, { buttons: 0 })));
  if (kind !== 'up') c.dispatchEvent(new PointerEvent('pointerdown', Object.assign({}, base, { buttons: 1 })));
  if (kind !== 'down') {
    c.dispatchEvent(new PointerEvent('pointerup', Object.assign({}, base, { buttons: 0 })));
    c.dispatchEvent(new MouseEvent('click', Object.assign({}, base)));
  }
};
const clickTile = (tile) => { const pt = aim(tile); if (!pt) return null; fire(pt); return pt; };
const hoverTile = (tile) => {
  const pt = aim(tile);
  if (!pt) return null;
  const c = canvas();
  c.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, cancelable: true, composed: true, pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 0, clientX: pt.x, clientY: pt.y }));
  return pt;
};
const stat = () => (document.querySelector('.slot-stat') || {}).textContent || '';
const err = () => (document.querySelector('.slot-error') || {}).textContent || '';
const notice = () => (document.querySelector('.slot-explain') || {}).textContent || '';
const toolState = () => Array.from(document.querySelectorAll('.slot-toolbar button')).map((b) => b.textContent.trim() + (b.getAttribute('aria-pressed') === 'true' ? '*' : ''));
const panelSlots = () => Array.from(document.querySelectorAll('.slot-tile')).map((b) => b.getAttribute('title') || b.textContent.trim());
const selectedId = () => { const s = unref(findComp('WardMapView').setupState.selected); return s ? s.id : null; };
const snapshotState = () => {
  const slots = panelSlots();
  const dup = slots.length !== new Set(slots.map((s) => (s.split(' · ')[1] || s))).size;
  return { stat: stat(), error: err(), notice: notice(), tools: toolState(), selectedId: selectedId(), slots, duplicateSlots: dup };
};
"""


def js(body):
    return "(() => {\n" + PRELUDE + "\n" + body + "\n})()"


A = {}
A["open_editor"] = js(r"""
  const b = Array.from(document.querySelectorAll('button')).find((x) => x.textContent.includes('模拟编辑'));
  b.click();
  return JSON.stringify({ ok: true });
""")
A["focus_floor"] = js(r"""
  const f = btn('单层聚焦');
  if (f) f.click();
  const chip = Array.from(document.querySelectorAll('.wm-floor-chips button')).find((x) => x.textContent.trim().startsWith('1F'));
  if (chip) chip.click();
  return JSON.stringify({ ok: !!chip, chip: chip ? chip.textContent.trim() : null });
""")
A["report"] = js(r"""
  const stage = document.querySelector('.wm-stage');
  if (stage) stage.scrollIntoView({ block: 'center' });
  const tiles = tilesOf();
  const kinds = {}; tiles.forEach((t) => { kinds[t.kind] = (kinds[t.kind] || 0) + 1; });
  const r = canvas().getBoundingClientRect();
  return JSON.stringify({ state: snapshotState(), rect: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
    sceneTiles: tiles.length, byKind: kinds, wards: [...new Set(tiles.map((t) => t.wardId))] });
""")
A["tool_add"] = js(r"""btn('放置').click(); return JSON.stringify({ tools: toolState() });""")
A["hover_empty"] = js(r"""
  const t = tilesOf().filter((x) => x.kind === 'empty')[0];
  const pt = hoverTile(t);
  if (!pt) return JSON.stringify({ ok: false });
  return JSON.stringify({ ok: true, slot: t.slot, wardId: t.wardId, off: pt.off });
""")
A["place"] = js(r"""
  const t = tilesOf().filter((x) => x.kind === 'empty')[0];
  const pt = clickTile(t);
  return JSON.stringify({ ok: !!pt, slot: t.slot, wardId: t.wardId, off: pt && pt.off });
""")
A["click_draft"] = js(r"""
  const t = tilesOf().filter((x) => x.kind === 'draft')[0];
  if (!t) return JSON.stringify({ ok: false });
  const pt = clickTile(t);
  return JSON.stringify({ ok: !!pt, slot: t.slot, off: pt && pt.off });
""")
A["tool_move"] = js(r"""btn('移动').click(); return JSON.stringify({ tools: toolState() });""")
A["select_draft"] = js(r"""
  const t = tilesOf().filter((x) => x.kind === 'draft')[0];
  const pt = clickTile(t);
  return JSON.stringify({ ok: !!pt, slot: t.slot, selectedId: selectedId(), off: pt && pt.off });
""")
A["move_to"] = js(r"""
  const tiles = tilesOf();
  const draft = tiles.filter((x) => x.kind === 'draft')[0];
  const t = tiles.filter((x) => x.kind === 'empty' && x.wardId === draft.wardId)[0];
  const pt = clickTile(t);
  return JSON.stringify({ ok: !!pt, from: draft.slot, to: t.slot, off: pt && pt.off });
""")
A["tool_remove"] = js(r"""btn('移除').click(); return JSON.stringify({ tools: toolState() });""")
A["remove_real"] = js(r"""
  const t = tilesOf().filter((x) => x.kind === 'real')[0];
  const pt = clickTile(t);
  return JSON.stringify({ ok: !!pt, slot: t.slot, bedId: t.bedId, off: pt && pt.off });
""")
A["remove_draft"] = js(r"""
  const t = tilesOf().filter((x) => x.kind === 'draft')[0];
  if (!t) return JSON.stringify({ ok: false });
  const pt = clickTile(t);
  return JSON.stringify({ ok: !!pt, slot: t.slot, off: pt && pt.off });
""")
A["undo"] = js(r"""btn('撤销').click(); return JSON.stringify({ state: snapshotState() });""")
A["redo"] = js(r"""btn('重做').click(); return JSON.stringify({ state: snapshotState() });""")
A["state"] = js(r"""return JSON.stringify({ state: snapshotState() });""")
A["right_click"] = js(r"""
  const c = canvas();
  const r = c.getBoundingClientRect();
  c.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 }));
  return JSON.stringify({ tools: toolState() });
""")

for name, code in A.items():
    abtool.check_js(NODE, name, code)

cmds = [
    ["open", BASE + "/login"],
    ["set", "viewport", "1440", "960"],
    ["wait", "1200"],
    ["fill", "#username", "admin"],
    ["fill", "input[type=password]", "admin123"],
    ["click", "button.btn--primary"],
    ["wait", "2500"],
    ["open", BASE + "/ward-map"],
    ["wait", "4500"],
    ["eval", A["open_editor"]],
    ["wait", "1500"],
    ["eval", A["focus_floor"]],
    ["wait", "1600"],
    ["eval", A["report"]],
    ["screenshot", SHOT + "p5a_02_editor_slots.png"],
    ["eval", A["tool_add"]],
    ["wait", "300"],
    ["eval", A["hover_empty"]],
    ["wait", "600"],
    ["screenshot", SHOT + "p5a_03_ghost_green.png"],
    ["eval", A["place"]],
    ["wait", "900"],
    ["eval", A["state"]],
    ["screenshot", SHOT + "p5a_04_placed.png"],
    ["eval", A["click_draft"]],
    ["wait", "600"],
    ["eval", A["state"]],
    ["screenshot", SHOT + "p5a_05_overlap_rejected.png"],
    ["eval", A["tool_move"]],
    ["wait", "300"],
    ["eval", A["select_draft"]],
    ["wait", "500"],
    ["eval", A["state"]],
    ["eval", A["move_to"]],
    ["wait", "900"],
    ["eval", A["state"]],
    ["screenshot", SHOT + "p5a_06_moved.png"],
    ["eval", A["tool_remove"]],
    ["wait", "300"],
    ["eval", A["remove_real"]],
    ["wait", "700"],
    ["eval", A["state"]],
    ["screenshot", SHOT + "p5a_07_remove_real_rejected.png"],
    ["eval", A["remove_draft"]],
    ["wait", "800"],
    ["eval", A["state"]],
    ["eval", A["undo"]],
    ["wait", "600"],
    ["eval", A["state"]],
    ["screenshot", SHOT + "p5a_08_undo_restored.png"],
    ["eval", A["redo"]],
    ["wait", "600"],
    ["eval", A["state"]],
    ["eval", A["tool_add"]],
    ["wait", "300"],
    ["press", "Escape"],
    ["wait", "400"],
    ["eval", A["state"]],
    ["screenshot", SHOT + "p5a_09_esc_cancel.png"],
    ["eval", A["tool_remove"]],
    ["wait", "300"],
    ["eval", A["right_click"]],
    ["wait", "300"],
    ["eval", A["state"]],
]

out = abtool.batch(cmds, wait=320)
print(out[-16000:])
