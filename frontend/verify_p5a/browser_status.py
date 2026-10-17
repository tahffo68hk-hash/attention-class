"""P5-A 真实 Chromium 验收 —— 批次 D：五种床位状态在 3D 中的实际绑定"""
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
  const seen = new Set(); let hit = null;
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
const txt = (sel) => { const e = document.querySelector(sel); return e ? e.textContent.replace(/\s+/g, ' ').trim() : null; };
const bedPoints = () => {
  const st = sceneSt();
  const list = unref(st.pickTargets) || [];
  const cam = unref(st.camera);
  const r = canvas().getBoundingClientRect();
  const V = list.length ? list[0].position.constructor : null;
  if (!V) return [];
  return list.filter((m) => m.visible).map((m) => {
    const p = m.getWorldPosition(new V()).project(cam);
    return { bedId: m.userData.bedId, x: r.left + ((p.x + 1) / 2) * r.width, y: r.top + ((1 - p.y) / 2) * r.height };
  });
};
const aimBed = (bed) => {
  const st = sceneSt();
  const cands = [[0, 0]];
  for (let rad = 4; rad <= 20; rad += 4) for (let a = 0; a < 12; a++) cands.push([Math.cos(a * Math.PI / 6) * rad, Math.sin(a * Math.PI / 6) * rad]);
  for (const [dx, dy] of cands) {
    const x = bed.x + dx, y = bed.y + dy;
    const hit = st.pick({ clientX: x, clientY: y });
    if (hit && hit.id === bed.bedId) return { x: Math.round(x), y: Math.round(y) };
  }
  return null;
};
const snapshotBeds = () => { const snap = unref(findComp('WardMapView').setupState.snapshot); return (snap && snap.beds) || []; };
const hoverStatus = (status) => {
  const beds = snapshotBeds().filter((b) => b.status === status);
  if (!beds.length) return { ok: false, why: 'no bed with status' };
  const pts = bedPoints();
  for (const bed of beds) {
    const p = pts.find((x) => x.bedId === bed.id);
    if (!p) continue;
    const pt = aimBed(p);
    if (!pt) continue;
    canvas().dispatchEvent(new PointerEvent('pointermove', { bubbles: true, cancelable: true, composed: true, pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 0, clientX: pt.x, clientY: pt.y }));
    return { ok: true, code: bed.code, bedId: bed.id };
  }
  return { ok: false, why: 'no hittable bed for status' };
};
"""


def js(body):
    return "(() => {\n" + PRELUDE + "\n" + body + "\n})()"


STATUSES = ["AVAILABLE", "RESERVED", "OCCUPIED", "CLEANING", "MAINTENANCE"]
ACT = {}
for s in STATUSES:
    ACT[s] = js("return JSON.stringify(hoverStatus('%s'));" % s)
ACT["read"] = js("return JSON.stringify({ tooltip: txt('.wm-tooltip-head'), full: txt('.wm-tooltip') });")

for name, code in ACT.items():
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
]
for s in STATUSES:
    cmds += [["eval", ACT[s]], ["wait", "500"], ["eval", ACT["read"]]]
cmds += [["screenshot", SHOT + "p5a_15_status_hover.png"]]

out = abtool.batch(cmds, wait=260)
print(out[-5000:])
