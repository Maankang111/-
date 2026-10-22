#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把这个学习系统初始化成独立的 git 仓库，并推到自己的仓库。
不影响机器上已有的公司 git 配置。

用法：
    python setup_personal_git.py                      交互式，会问你要地址
    python setup_personal_git.py <仓库地址>            直接指定
    python setup_personal_git.py <仓库地址> --ssh      顺便生成 SSH 密钥

仓库地址两种都支持：
    https://github.com/你的用户名/pa-study.git
    git@github.com:你的用户名/pa-study.git
    https://gitee.com/你的用户名/pa-study.git
"""

import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
GITIGNORE = """__pycache__/
*.pyc
*.tmp
.workbuddy/
"""


def run(args, show=False):
    r = subprocess.run(args, cwd=BASE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if show:
        print((r.stdout or "") + (r.stderr or ""))
    return r


def out(*a):
    print(*a, flush=True)


def has_git_dir():
    return os.path.isdir(os.path.join(BASE, ".git"))


def git(*args, show=False):
    return run(["git"] + list(args), show=show)


def main():
    argv = [a for a in sys.argv[1:]]
    want_ssh = "--ssh" in argv
    argv = [a for a in argv if not a.startswith("--")]
    url = argv[0] if argv else ""

    out("")
    out("检查项目目录")
    if not os.path.exists(os.path.join(BASE, "pa_server.py")):
        out("  这个脚本要和 pa_server.py 放在同一个文件夹里")
        return 1
    out("  目录  " + BASE)

    r = git("--version")
    if r.returncode != 0:
        out("  没装 git，先去 https://git-scm.com 装一个")
        return 1
    out("  git   " + (r.stdout or "").strip())

    # 现有身份只读，不改全局
    gname = (git("config", "--global", "user.name").stdout or "").strip()
    gmail = (git("config", "--global", "user.email").stdout or "").strip()
    out("  全局身份  " + gname + "  " + gmail + "  （只读，不改动）")

    if not url:
        out("")
        out("先在你的 git 网站上建一个空仓库，私有公开都行，不要勾选自动生成 README。")
        out("然后把仓库地址粘贴到这里，回车确认：")
        out("  例如  https://github.com/你的名字/pa-study.git")
        try:
            url = input("  地址：").strip()
        except EOFError:
            out("  没有输入地址，退出。")
            return 1
    if not url:
        out("地址是空的，退出。")
        return 1
    if not (url.startswith("https://") or url.startswith("http://") or url.startswith("git@")):
        out("地址看起来不对，要以 https:// 或 git@ 开头")
        return 1

    # 1. 初始化仓库
    out("")
    if has_git_dir():
        out("1. 已经是 git 仓库，跳过初始化")
    else:
        r = git("init")
        if r.returncode != 0:
            out("1. 初始化失败：" + (r.stderr or ""))
            return 1
        out("1. 已初始化空仓库")

    # 2. 仓库级身份，不动全局
    name = gname or "pa-study"
    mail = gmail or "none@example.com"
    git("config", "--local", "user.name", name)
    git("config", "--local", "user.email", mail)
    out("2. 本仓库身份已设为 " + name + "  " + mail + "（只对这个仓库生效）")

    # 3. .gitignore
    gi = os.path.join(BASE, ".gitignore")
    if not os.path.exists(gi):
        with open(gi, "w", encoding="utf-8") as f:
            f.write(GITIGNORE)
        out("3. 已写 .gitignore，忽略缓存和临时文件")
    else:
        out("3. .gitignore 已存在，保持不变")

    # 4. 首次提交
    git("add", "-A")
    r = git("commit", "-m", "初始化：价格行为学习系统")
    if r.returncode == 0:
        out("4. 已完成首次提交")
    else:
        txt = ((r.stdout or "") + (r.stderr or "")).strip()
        if "nothing to commit" in txt.lower() or "无文件要提交" in txt:
            out("4. 没有新内容要提交")
        else:
            out("4. 提交失败：" + txt[:200])

    # 5. 远程地址
    cur = (git("remote", "get-url", "origin").stdout or "").strip()
    if cur:
        if cur != url:
            git("remote", "set-url", "origin", url)
            out("5. 远程地址已更新为 " + url)
        else:
            out("5. 远程地址没变")
    else:
        git("remote", "add", "origin", url)
        out("5. 远程地址已设为 " + url)

    # 6. SSH 密钥（可选）
    ssh_dir = os.path.join(os.path.expanduser("~"), ".ssh")
    key = os.path.join(ssh_dir, "id_ed25519_personal")
    if url.startswith("git@") or want_ssh:
        out("")
        out("6. 检查 SSH 密钥")
        if os.path.exists(key):
            out("   已有密钥 " + key)
        else:
            os.makedirs(ssh_dir, exist_ok=True)
            r = subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-C", mail, "-f", key, "-N", ""],
                capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            if r.returncode == 0:
                out("   已生成新密钥 " + key)
            else:
                out("   生成失败：" + ((r.stderr or "") + (r.stdout or ""))[:200])
                out("   可以手动执行：ssh-keygen -t ed25519 -C \"" + mail + "\"")
        pub = key + ".pub"
        if os.path.exists(pub):
            with open(pub, encoding="utf-8") as f:
                pubkey = f.read().strip()
            out("")
            out("   把这个公钥整段复制，加到你的 git 网站 SSH Keys 里：")
            out("   --------------------------------------------------")
            out("   " + pubkey)
            out("   --------------------------------------------------")
            out("   GitHub 位置：Settings 里找 SSH and GPG keys")
            out("   Gitee  位置：设置 里找 SSH 公钥")

            cfg = os.path.join(ssh_dir, "config")
            host = ""
            m = re.match(r"git@([^:]+):", url)
            if m:
                host = m.group(1)
            if host:
                block = ("Host " + host + "\n"
                         "  HostName " + host + "\n"
                         "  User git\n"
                         "  IdentityFile ~/.ssh/id_ed25519_personal\n")
                exist = ""
                if os.path.exists(cfg):
                    with open(cfg, encoding="utf-8") as f:
                        exist = f.read()
                if "id_ed25519_personal" not in exist:
                    with open(cfg, "a", encoding="utf-8") as f:
                        if exist and not exist.endswith("\n"):
                            f.write("\n")
                        f.write("\n" + block)
                    out("")
                    out("   已把 " + host + " 指向这个密钥，写在 " + cfg)
                else:
                    out("")
                    out("   ssh config 里已经有这个密钥的配置，没重复写")

    out("")
    out("本地都弄好了，剩最后一步推送：")
    out("")
    out("   cd \"" + BASE + "\"")
    out("   git push -u origin master")
    out("")
    out("如果分支叫 main 而不是 master，用 git push -u origin main")
    out("想先看当前分支名：git branch --show-current")
    out("")
    if url.startswith("http"):
        out("用 https 地址时，第一次推送会弹窗要账号。GitHub 已经不能用登录密码，")
        out("要去 Settings 里生成 Personal Access Token 当密码用，权限勾 repo。")
        out("Gitee 可以用账号密码，或者用私人令牌。")
    else:
        out("用 SSH 地址时不需要输密码，但公钥要先去网站加上，否则会提示 Permission denied。")
    out("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
