"""P5-A 真实 Chromium 验收 —— 批次 B：编辑器草稿 → 调度沙盘重新计算（Greedy / 精确流）。"""
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
const btn = (t) => Array.from(document.querySelectorAll('button')).find((b) => b.textContent.trim() === t)
  || Array.from(document.querySelectorAll('button')).find((b) => b.textContent.trim().includes(t));
const setSelect = (labelText, optionText) => {
  const label = Array.from(document.querySelectorAll('.wm-sandbox-form label')).find((l) => l.textContent.trim().startsWith(labelText));
  if (!label) return null;
  const sel = label.querySelector('select');
  const opt = Array.from(sel.options).find((o) => o.textContent.trim().includes(optionText));
  if (!opt) return null;
  sel.selectedIndex = opt.index;
  sel.dispatchEvent(new Event('change', { bubbles: true }));
  return opt.textContent.trim();
};
const txt = (sel) => { const e = document.querySelector(sel); return e ? e.textContent.replace(/\s+/g, ' ').trim() : null; };
"""


def js(body):
    return "(() => {\n" + PRELUDE + "\n" + body + "\n})()"


B = {}
B["open_editor"] = js(r"""
  btn('模拟编辑').click();
  return JSON.stringify({ ok: true });
""")
B["draft_via_panel"] = js(r"""
  const tiles = Array.from(document.querySelectorAll('.slot-tile'));
  const empty = tiles.find((t) => (t.getAttribute('title') || '').includes('空槽'));
  if (!empty) return JSON.stringify({ ok: false });
  btn('放置').click();
  empty.click();
  return JSON.stringify({ ok: true, title: empty.getAttribute('title'), stat: txt('.slot-stat') });
""")
B["open_sandbox"] = js(r"""
  const b = btn('用当前编辑草稿重新计算调度');
  if (!b) return JSON.stringify({ ok: false, why: 'no draft sandbox button' });
  b.click();
  return JSON.stringify({ ok: true });
""")
B["setup_request"] = js(r"""
  const dept = setSelect('模拟科室', '');
  const chips = Array.from(document.querySelectorAll('.wm-sandbox-form select option')).map((o) => o.textContent.trim());
  return JSON.stringify({ dept, chips });
""")
B["pick_dept"] = js(r"""
  const label = Array.from(document.querySelectorAll('.wm-sandbox-form label')).find((l) => l.textContent.trim().startsWith('模拟科室'));
  const sel = label && label.querySelector('select');
  if (!sel) return JSON.stringify({ ok: false });
  const opt = Array.from(sel.options).find((o) => o.index > 0);
  sel.selectedIndex = opt.index;
  sel.dispatchEvent(new Event('change', { bubbles: true }));
  return JSON.stringify({ ok: true, chosen: opt.textContent.trim(), value: opt.value });
""")
B["add_patient"] = js(r"""
  const b = btn('+ 添加虚构申请');
  if (!b) return JSON.stringify({ ok: false });
  if (b.disabled) return JSON.stringify({ ok: false, why: 'disabled', deptText: txt('.wm-sandbox-form') });
  b.click();
  return JSON.stringify({ ok: true, patients: txt('.wm-sandbox-patients') });
""")
B["run"] = js(r"""
  const b = btn('重新计算模拟方案');
  if (!b) return JSON.stringify({ ok: false, why: 'no run button' });
  if (b.disabled) return JSON.stringify({ ok: false, why: 'disabled' });
  b.click();
  return JSON.stringify({ ok: true, label: b.textContent.trim() });
""")
B["result"] = js(r"""
  return JSON.stringify({
    supplyNote: txt('.wm-sandbox-note'),
    metrics: txt('.wm-sandbox-metrics'),
    methodNote: Array.from(document.querySelectorAll('.wm-sandbox-note')).map((e) => e.textContent.replace(/\s+/g, ' ').trim()),
    pairs: Array.from(document.querySelectorAll('.wm-sandbox-pairs button')).map((b) => b.textContent.replace(/\s+/g, ' ').trim()),
    error: txt('.wm-error'),
    resultsVisible: !!document.querySelector('.wm-sandbox-results'),
  });
""")
B["scroll_results"] = js(r"""
  const r = document.querySelector('.wm-sandbox-results');
  if (r) r.scrollIntoView({ block: 'center' });
  return JSON.stringify({ ok: !!r });
""")
B["greedy"] = js(r"""
  const b = Array.from(document.querySelectorAll('.wm-view-switch button')).find((x) => x.textContent.trim() === 'Greedy');
  if (!b) return JSON.stringify({ ok: false });
  b.click();
  return JSON.stringify({ ok: true });
""")

for name, code in B.items():
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
    ["eval", B["open_editor"]],
    ["wait", "1400"],
    ["eval", B["draft_via_panel"]],
    ["wait", "800"],
    ["eval", B["open_sandbox"]],
    ["wait", "900"],
    ["eval", B["pick_dept"]],
    ["wait", "300"],
    ["eval", B["add_patient"]],
    ["wait", "500"],
    ["eval", B["run"]],
    ["wait", "4000"],
    ["eval", B["result"]],
    ["eval", B["scroll_results"]],
    ["wait", "600"],
    ["screenshot", SHOT + "p5a_10_sandbox_recompute.png"],
    ["eval", B["greedy"]],
    ["wait", "700"],
    ["eval", B["result"]],
    ["eval", B["scroll_results"]],
    ["wait", "600"],
    ["screenshot", SHOT + "p5a_11_sandbox_greedy.png"],
]

out = abtool.batch(cmds, wait=280)
print(out[-9000:])
