#!/usr/bin/env python3
"""Register the NetHunter wireless modules with kleaf.

Kleaf fails a kernel_build when an in-tree module is built but not declared
in module_outs/module_implicit_outs ("built but not copied"). The
define_common_kernels target_configs in common/BUILD.bazel only supports
module_implicit_outs via get_gki_modules_list(), which reads the
_COMMON_GKI_MODULES_LIST in modules.bzl. Append the modules this action
enables (cfg80211, mac80211, mac80211_hwsim, rtl8188fu) to that list,
inserted at their sorted positions.

Idempotent: safe to run repeatedly.
"""
import os
import sys

ADDS = [
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


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: register_modules.py <modules.bzl>", file=sys.stderr)
        return 1
    p = os.path.abspath(sys.argv[1])
    s = open(p).read()
    if MARKER in s:
        print(f"{p}: already patched")
        return 0
    for anchor, ins in ADDS:
        if anchor not in s:
            print(f"error: anchor not found in {p}: {anchor.strip()}", file=sys.stderr)
            return 1
        s = s.replace(anchor, anchor + ins, 1)
    open(p, "w").write(s)
    print(f"{p}: registered wireless modules with kleaf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
