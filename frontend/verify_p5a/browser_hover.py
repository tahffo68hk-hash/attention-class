"""P5-A 真实 Chromium 验收 —— 批次 C：悬停高亮 / 遮挡淡化 / 离开后恢复。"""
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
const btn = (t) => Array.from(document.querySelectorAll('button')).find((b) => b.textContent.trim() === t)
  || Array.from(document.querySelectorAll('button')).find((b) => b.textContent.trim().includes(t));
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
  const c = canvas();
  const cands = [[0, 0]];
  for (let rad = 4; rad <= 20; rad += 4) for (let a = 0; a < 12; a++) cands.push([Math.cos(a * Math.PI / 6) * rad, Math.sin(a * Math.PI / 6) * rad]);
  for (const [dx, dy] of cands) {
    const x = bed.x + dx, y = bed.y + dy;
    const hit = st.pick({ clientX: x, clientY: y });
    if (hit && hit.id === bed.bedId) return { x: Math.round(x), y: Math.round(y) };
  }
  return null;
};
const hover = (pt) => canvas().dispatchEvent(new PointerEvent('pointermove', { bubbles: true, cancelable: true, composed: true, pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 0, clientX: pt.x, clientY: pt.y }));
const leave = () => canvas().dispatchEvent(new PointerEvent('pointerleave', { bubbles: true, cancelable: true, composed: true, pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 0 }));
"""


def js(body):
    return "(() => {\n" + PRELUDE + "\n" + body + "\n})()"


C = {}
C["focus"] = js(r"""
  const f = btn('单层聚焦');
  if (f) f.click();
  const chip = Array.from(document.querySelectorAll('.wm-floor-chips button')).find((x) => x.textContent.trim().startsWith('1F'));
  if (chip) chip.click();
  return JSON.stringify({ ok: !!chip, chip: chip ? chip.textContent.trim() : null });
""")
C["hover_bed"] = js(r"""
  const beds = bedPoints();
  if (!beds.length) return JSON.stringify({ ok: false, why: 'no bed meshes' });
  for (const b of beds) {
    const pt = aimBed(b);
    if (!pt) continue;
    hover(pt);
    return JSON.stringify({ ok: true, bedId: b.bedId, x: pt.x, y: pt.y, total: beds.length });
  }
  return JSON.stringify({ ok: false, why: 'no hittable bed' });
""")
C["read"] = js(r"""
  return JSON.stringify({ tooltip: txt('.wm-tooltip-head'), body: txt('.wm-tooltip'), counts: txt('.wm-counts') || null });
""")
C["leave"] = js(r"""
  leave();
  return JSON.stringify({ ok: true, tooltip: txt('.wm-tooltip') });
""")

for name, code in C.items():
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
    ["eval", C["focus"]],
    ["wait", "1800"],
    ["screenshot", SHOT + "p5a_12_hover_baseline.png"],
    ["eval", C["hover_bed"]],
    ["wait", "700"],
    ["eval", C["read"]],
    ["screenshot", SHOT + "p5a_13_hover_bed.png"],
    ["eval", C["leave"]],
    ["wait", "800"],
    ["screenshot", SHOT + "p5a_14_hover_restored.png"],
    ["eval", C["read"]],
]

out = abtool.batch(cmds, wait=260)
print(out[-6000:])
