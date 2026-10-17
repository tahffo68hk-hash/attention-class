"""P5-A 浏览器验收公共驱动。

本机 agent-browser CLI 在动作完成后不退出（会话文件证明动作已完成），
因此这里边读边收，到点终止并保留已拿到的输出。所有命令必须放在同一次
`batch` 里，因为该 CLI **不跨调用保留页面状态**。
"""
import json
import os
import subprocess
import tempfile
import threading
import time

NODE = r"C:/Users/yang/.workbuddy/binaries/node/versions/22.22.2-6/node.exe"
AB = r"D:/OpenClaw/npm-global/node_modules/agent-browser/bin/agent-browser.js"
BASE = "http://127.0.0.1:5173"
SHOT = r"E:/Attention is all you need/docs/screenshots/"


def batch(cmds, wait=240, hard=25):
    args = [NODE, AB, "batch", "--bail"]
    payload = json.dumps(cmds, ensure_ascii=False)
    proc = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        bufsize=1,
    )
    buf = []

    def reader():
        try:
            for line in proc.stdout:
                buf.append(line.rstrip("\n"))
        except Exception:  # noqa: BLE001
            pass

    th = threading.Thread(target=reader, daemon=True)
    th.start()
    try:
        proc.stdin.write(payload)
        proc.stdin.close()
    except Exception:  # noqa: BLE001
        pass
    deadline = time.time() + wait
    while time.time() < deadline and proc.poll() is None:
        time.sleep(0.3)
    exited = proc.poll() is not None
    if not exited:
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass
        t2 = time.time() + hard
        while time.time() < t2 and proc.poll() is None:
            time.sleep(0.2)
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
    th.join(timeout=5)
    return "\n".join(buf) + f"\n<<{'exited' if exited else 'killed'}>>"


def login_cmds():
    return [
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


def check_js(node_js, name, code):
    """用 node --check 预校验页面脚本，避免把语法错误带进浏览器。"""
    path = os.path.join(tempfile.mkdtemp(prefix="p5a_js_"), "%s.js" % name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    r = subprocess.run([node_js, "--check", path], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("JS 语法错误 %s: %s" % (name, r.stderr[:500]))
