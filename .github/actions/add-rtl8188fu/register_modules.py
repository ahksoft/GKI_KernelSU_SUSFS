#!/usr/bin/env python3
"""Register the NetHunter wireless modules with kleaf.

Kleaf fails a kernel_build when an in-tree module is built but not declared
in module_outs/module_implicit_outs ("built but not copied"). The
define_common_kernels target_configs in common/BUILD.bazel only supports
module_implicit_outs, which is sourced either from get_gki_modules_list()
(_COMMON_GKI_MODULES_LIST in modules.bzl) or written inline in BUILD.bazel.
This script appends the modules this action enables (cfg80211, mac80211,
mac80211_hwsim, rtl8188fu) to whichever form the checked-out kernel uses.

Handled layouts:
  * modules.bzl with _COMMON_GKI_MODULES_LIST (android14-5.15, android14-6.1,
    android15-6.6, android16-6.12, android17-6.18): anchor-insert at the
    same positions as the android14-6.1 list (usbnet.ko, l2tp_ppp.ko,
    tipc.ko), falling back to sorted insertion if an anchor is missing.
  * BUILD.bazel with inline "module_implicit_outs": [...] lists
    (android13-5.15): insert into every such list, keeping it sorted.
  * Neither (android12/13-5.10 legacy build.sh): nothing to do.

Idempotent: safe to run repeatedly.
"""
import os
import re
import sys

ADDS = [
    "drivers/net/wireless/mac80211_hwsim.ko",
    "drivers/net/wireless/realtek/rtl8188fu/rtl8188fu.ko",
    "net/mac80211/mac80211.ko",
    "net/wireless/cfg80211.ko",
]

ANCHORS = [
    (
        '    "drivers/net/usb/usbnet.ko",\n',
        '    "drivers/net/wireless/mac80211_hwsim.ko",\n'
        '    "drivers/net/wireless/realtek/rtl8188fu/rtl8188fu.ko",\n',
    ),
    (
        '    "net/l2tp/l2tp_ppp.ko",\n',
        '    "net/mac80211/mac80211.ko",\n',
    ),
    (
        '    "net/tipc/tipc.ko",\n',
        '    "net/wireless/cfg80211.ko",\n',
    ),
]

MARKER = "rtl8188fu.ko"

_MODULE_LIST_RE = re.compile(
    r'(_COMMON_GKI_MODULES_LIST\s*=\s*\[)(.*?)(\n\])', re.DOTALL
)
_IMPLICIT_OUTS_RE = re.compile(
    r'(module_implicit_outs"\s*:\s*\[)(.*?)(\n\s*\],)', re.DOTALL
)


def _module_paths(text: str) -> list:
    return re.findall(r'"((?:drivers|net|mm|crypto)/[^"]+\.ko)"', text)


def _sorted_insert(text: str) -> str:
    """Insert ADDS at sorted positions inside a "[...]" list body."""
    entries = re.findall(r'\n(\s*)"([^"]+\.ko)",', text)
    existing = {name for _, name in entries}
    merged = sorted(existing | set(ADDS))
    ind = entries[0][0] if entries else "        "
    return "\n" + "\n".join(f'{ind}"{name}",' for name in merged)


def patch_modules_bzl(path: str, s: str) -> bool:
    if MARKER in s:
        print(f"{path}: already patched")
        return True
    ok = True
    for anchor, ins in ANCHORS:
        if anchor not in s:
            print(f"{path}: anchor missing ({anchor.strip()}), using sorted "
                  f"insertion", file=sys.stderr)
            ok = False
            break
        s = s.replace(anchor, anchor + ins, 1)
    if not ok:
        m = _MODULE_LIST_RE.search(s)
        if not m:
            print(f"{path}: no _COMMON_GKI_MODULES_LIST found", file=sys.stderr)
            return False
        s = s[:m.start(1)] + m.group(1) + _sorted_insert(m.group(2)) + m.group(3) + s[m.end(3):]
    open(path, "w").write(s)
    print(f"{path}: registered wireless modules with kleaf (modules.bzl)")
    return True


def patch_build_bazel(path: str, s: str) -> bool:
    if MARKER in s:
        print(f"{path}: already patched")
        return True
    def _repl(m):
        return m.group(1) + _sorted_insert(m.group(2)) + m.group(3)
    s2, n = _IMPLICIT_OUTS_RE.subn(_repl, s)
    if n == 0:
        print(f"{path}: no inline 'module_implicit_outs' list found",
              file=sys.stderr)
        return False
    open(path, "w").write(s2)
    print(f"{path}: registered wireless modules with kleaf ({n} "
          f"module_implicit_outs list(s) updated)")
    return True


def main() -> int:
    target = "."
    if len(sys.argv) == 2:
        target = sys.argv[1]
    if len(sys.argv) > 2:
        print("usage: register_modules.py [<dir-or-file>]", file=sys.stderr)
        return 1
    p = os.path.abspath(target)
    if os.path.isdir(p):
        mods = os.path.join(p, "modules.bzl")
        bazel = os.path.join(p, "BUILD.bazel")
        if os.path.isfile(mods):
            return 0 if patch_modules_bzl(mods, open(mods).read()) else 1
        if os.path.isfile(bazel):
            return 0 if patch_build_bazel(bazel, open(bazel).read()) else 1
        print(f"{p}: no modules.bzl/BUILD.bazel kleaf module list found "
              f"(legacy build.sh?); nothing to register")
        return 0
    if os.path.isfile(p):
        s = open(p).read()
        if "_COMMON_GKI_MODULES_LIST" in s:
            return 0 if patch_modules_bzl(p, s) else 1
        return 0 if patch_build_bazel(p, s) else 1
    print(f"{p}: not found", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
