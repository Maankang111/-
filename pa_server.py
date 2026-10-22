#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
价格行为学习系统 · 本地服务
作用：把页面里每天填写的内容写成本地文件，方便用 git 管理。
用法：python pa_server.py        （默认端口 8765，被占用会自动往后找）
      跑起来后会自己打开浏览器，按 Ctrl+C 停止。
"""

import http.server
import json
import os
import re
import socketserver
import subprocess
import sys
import threading
import time
import webbrowser
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
IMG_DIR = os.path.join(DATA_DIR, "img")
DATA_FILE = os.path.join(DATA_DIR, "records.json")
PAGE_NAME = "PA学习系统.html"
PAGE_FILE = os.path.join(BASE_DIR, PAGE_NAME)
MAX_BODY = 24 * 1024 * 1024


def empty_data():
    return {
        "startDate": time.strftime("%Y-%m-%d"),
        "records": {},
        "wrongPool": [],
        "weeks": [],
    }


def read_data():
    if not os.path.exists(DATA_FILE):
        return empty_data()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def write_data(d):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def git(*args, timeout=60):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(
        ["git"] + list(args),
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )


def git_push():
    """把本地提交推到远程，返回 (ok, message)。"""
    if "origin" not in (git("remote").stdout or ""):
        return False, "还没配远程地址，先运行 setup_personal_git.py"
    try:
        r = git("push", "origin", "HEAD", timeout=90)
    except subprocess.TimeoutExpired:
        return False, "推送超时，可能是网络问题或凭据过期，试着手动 git push"
    text = ((r.stdout or "") + (r.stderr or "")).strip()
    low = text.lower()
    if r.returncode == 0:
        if "everything up-to-date" in low or "已是最新" in text:
            return True, "远程已经是最新"
        lines = [l for l in text.splitlines() if l.strip()]
        return True, (lines[-1].strip() if lines else "已推送")
    if "authentication failed" in low or "could not read username" in low or "permission denied" in low:
        return False, "认证失败，在命令行执行一次 git push 重新登录"
    if "rejected" in low or "non-fast-forward" in low:
        return False, "远程有本地没有的提交，先 git pull --rebase 再推"
    return False, text[:300] or "推送失败，原因不明"


def git_commit(msg):
    if not os.path.isdir(os.path.join(BASE_DIR, ".git")):
        r = git("init")
        if r.returncode != 0:
            return False, "git init 失败：" + ((r.stderr or r.stdout) or "").strip()[:200]
    git("add", "-A")
    r = git("commit", "-m", msg)
    if r.returncode != 0:
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        low = out.lower()
        if "nothing to commit" in low or "无文件要提交" in out or "没有要提交" in out:
            return True, "没有变化，不用提交"
        if "user.email" in out or "user.name" in out or "请告诉我你是谁" in out:
            return False, "git 还没配置用户名邮箱，先执行：git config --global user.name 你的名字 和 git config --global user.email 你的邮箱"
        return False, out[:300]
    lines = [l for l in (r.stdout or "").splitlines() if l.strip()]
    return True, lines[0] if lines else "已提交"


class Handler(http.server.SimpleHTTPRequestHandler):
    server_version = "PAStudy/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            raw = body.encode("utf-8")
        else:
            raw = body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except BrokenPipeError:
            pass

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/data":
            try:
                self._send(200, read_data())
            except Exception as e:
                self._send(500, {"error": str(e)})
            return

        if path == "/api/status":
            self._send(200, {
                "mode": "file",
                "file": DATA_FILE,
                "git": os.path.isdir(os.path.join(BASE_DIR, ".git")),
                "base": BASE_DIR,
            })
            return

        if path in ("/", "/index.html"):
            if not os.path.exists(PAGE_FILE):
                self._send(404, "找不到 " + PAGE_NAME, "text/plain; charset=utf-8")
                return
            with open(PAGE_FILE, "rb") as f:
                raw = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(raw)
            except BrokenPipeError:
                pass
            return

        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            n = 0
        if n > MAX_BODY:
            self._send(413, {"ok": False, "error": "图片或数据太大，单次上限 24MB"})
            return
        raw = self.rfile.read(n) if n else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send(400, {"ok": False, "error": "请求体不是合法 JSON"})
            return

        if path == "/api/upload":
            self._handle_upload(body)
            return

        if path == "/api/openfolder":
            self._handle_openfolder(body)
            return

        if path == "/api/data":
            if not isinstance(body, dict) or "records" not in body:
                self._send(400, {"ok": False, "error": "数据结构不对，缺 records"})
                return
            try:
                write_data(body)
                self._send(200, {"ok": True, "file": DATA_FILE})
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/commit":
            msg = body.get("msg") or ("学习记录 " + time.strftime("%Y-%m-%d %H:%M"))
            ok, info = git_commit(msg)
            self._send(200 if ok else 500, {"ok": ok, "message": info})
            return

        if path == "/api/push":
            ok, info = git_push()
            self._send(200 if ok else 500, {"ok": ok, "message": info})
            return

        self._send(404, {"ok": False, "error": "没有这个接口"})

    def _handle_upload(self, body):
        """接收 base64 图片，按日期分目录落盘，返回相对路径。"""
        data_url = body.get("dataUrl") or ""
        m = re.match(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", data_url, re.S)
        if not m:
            self._send(400, {"ok": False, "error": "图片格式不认识，需要 image/png 或 image/jpeg 的 dataURL"})
            return
        mime, b64 = m.group(1), m.group(2)
        ext_map = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}
        ext = ext_map.get(mime, ".png")
        try:
            import base64
            raw = base64.b64decode(b64, validate=False)
        except Exception as e:
            self._send(400, {"ok": False, "error": "base64 解不开：" + str(e)})
            return
        if not raw:
            self._send(400, {"ok": False, "error": "图片内容是空的，base64 解出来 0 字节"})
            return
        if len(raw) > 16 * 1024 * 1024:
            self._send(413, {"ok": False, "error": "单张图片超过 16MB"})
            return

        # 日期目录，只认 YYYY-MM-DD，不合法就用今天
        date_str = str(body.get("date") or "").strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            date_str = time.strftime("%Y-%m-%d")

        # 标签取当天状态，清掉文件名非法字符，最多四个字
        tag = str(body.get("tag") or "").strip()
        tag = re.sub(r'[\\/:*?"<>|\s]+', "", tag)[:4] or "未分类"

        try:
            day_dir = os.path.join(IMG_DIR, date_str)
            os.makedirs(day_dir, exist_ok=True)
            hm = time.strftime("%H%M")
            ms = "%03d" % (int(time.time() * 1000) % 1000)
            fn = "%s_%s_%s_%s%s" % (date_str, hm, tag, ms, ext)
            full = os.path.join(day_dir, fn)
            if os.path.exists(full):
                fn = "%s_%s_%s_%s_1%s" % (date_str, hm, tag, ms, ext)
                full = os.path.join(day_dir, fn)
            with open(full, "wb") as f:
                f.write(raw)
            rel = "data/img/" + date_str + "/" + fn
            self._send(200, {"ok": True, "file": rel, "dir": "data/img/" + date_str, "size": len(raw)})
        except Exception as e:
            self._send(500, {"ok": False, "error": "写图片失败：" + str(e)})

    def _handle_openfolder(self, body):
        """在资源管理器里打开 data 下的目录，方便直接看图。"""
        rel = str(body.get("dir") or "data/img")
        target = os.path.abspath(os.path.join(BASE_DIR, rel))
        root = os.path.abspath(DATA_DIR)
        if not (target == root or target.startswith(root + os.sep)):
            self._send(403, {"ok": False, "error": "只允许打开 data 目录里的文件夹"})
            return
        if not os.path.isdir(target):
            self._send(404, {"ok": False, "error": "这个文件夹还没有，先传一张图", "path": target})
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(target)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
            self._send(200, {"ok": True, "path": target})
        except Exception as e:
            self._send(500, {"ok": False, "error": str(e), "path": target})


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def out(*args):
    """统一输出并强制刷新，重定向或后台运行时也能看到日志。"""
    print(*args, flush=True)


def main():
    out("")
    out("正在检查运行环境")
    out("  Python    " + sys.version.split()[0] + "   " + sys.executable)
    out("  工作目录  " + os.getcwd())
    out("  脚本目录  " + BASE_DIR)
    if os.path.abspath(os.getcwd()) != BASE_DIR:
        out("  提示：你不是在脚本目录里运行的，没关系，下面所有路径都按脚本目录算")

    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        probe = os.path.join(DATA_DIR, ".write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
    except Exception as e:
        out("")
        out("启动失败：数据目录不可写")
        out("  目录  " + DATA_DIR)
        out("  原因  " + str(e))
        out("  处理  把这个文件夹换到有写权限的位置")
        return 1

    if not os.path.exists(PAGE_FILE):
        out("")
        out("启动失败：同目录下找不到 " + PAGE_NAME)
        out("  期望位置  " + PAGE_FILE)
        out("  处理  确认 html 和 pa_server.py 在同一个文件夹里")
        return 1

    start = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    httpd = None
    port = start
    for cand in range(start, start + 30):
        try:
            httpd = Server(("127.0.0.1", cand), Handler)
            port = cand
            break
        except OSError:
            continue

    if httpd is None:
        out("")
        out("启动失败：端口 %d 到 %d 都被占用" % (start, start + 29))
        out("  处理  指定别的端口，例如：python pa_server.py 9000")
        return 1

    url = "http://127.0.0.1:%d/" % port
    out("")
    out("已启动，可以用了")
    out("  页面地址  " + url)
    out("  数据文件  " + DATA_FILE)
    if not os.path.isdir(os.path.join(BASE_DIR, ".git")):
        out("  git 状态  还不是仓库，第一次点「提交到 git」会自动初始化")
    out("")
    out("浏览器应该已经自动打开，没打开就把上面的地址复制到浏览器。")
    out("这个窗口别关，关掉服务就停了。按 Ctrl+C 结束。")
    out("")

    if os.environ.get("PA_NO_BROWSER") != "1":
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        out("")
        out("已停止，数据都已经写进文件了。")
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
