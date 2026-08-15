# AGENTS.md

## What this repo is

A **CI-only** GitHub Actions repo that builds GKI Android kernels (KernelSU-Next + SUSFS + BBG + Networking + DroidSpaces) and publishes AnyKernel3 zips to GitHub Releases. **No kernel source lives in the repo** — everything is cloned at build time. Local development/verification of the actual kernel build is not possible; all work is editing workflow YAML and composite actions.

Fork layout: `origin` = ahksoft fork (tracks `main`), `upstream` = WildKernels. Build dirs (`kernel/`, `kernels/`, `bbr/`, `testing/`, `AIO-REJ/`) are gitignored.

## Build pipeline

Entrypoints are `.github/workflows/`:

- `main.yml` — workflow_dispatch entrypoint. Inputs: `release_type`, `kernel_build_version`, `feature_set`, `ksu_branch`, per-version `susfs_commit`. Dispatches `prepare.yml` once per kernel version, then `rej` (collects rejects), `summary`, and `release` (only when `release_type` is Pre-Release/Release).
- `prepare.yml` — reads the version config JSON, generates the build matrix (`generate-matrix` job), calls `build.yml` per matrix cell.
- `build.yml` — the actual build job (`build-gki`): one job per kernel/sublevel/date/variant cell, ~120min timeout.
- `commit-status.yml` — manual report of latest upstream SUSFS/KernelSU-Next commits.

The real work lives in composite actions under `.github/actions/*`. Each is a bash script; patch files ship in the action's `patches/` dir or come from the `kernel_patches` repo.

## Build matrix config

`.github/config/<version>.json` (e.g. `android16-6.12.json`) defines the matrix: `include[]` entries of `{sublevel, date}`. `date` is the os_patch_level (used as branch suffix `common-<android>-<kernel>-<date>`). Special values:

- `date: "lts"` — build from the **latest** branch; actual sublevel is read from the checked-out `kernel/common/Makefile` (`extract-sublevel-file-name` action).
- `variant` — only `android14-6.1.json` uses it (`"TheWildJames"`); adds a second matrix cell for the same sublevel/date.
- `android17-6.18.json` exists but has **no** job in `main.yml` — not built.

## Feature set gating

`feature_set` input (default `FULL`): `KSUN`, `SUSFS`, `BBG`, `NET` (networking incl. BBRv3/CIFS/Wireguard), `DS` (DroidSpaces). Gating pattern is `contains(inputs.feature_set, 'X') || inputs.feature_set == 'FULL'`.

**Always applied regardless of feature set** (including `NONE`): kernel-fixes, ntsync, ptrace, unicode-fix, misc configs, BTF, device patches, branding, remove-protected-exports, clean-kernel-flags, and the Normal+Bypass build passes.

## Build paths (build-kernel action)

- Legacy `build/build.sh` (build.config.gki.aarch64): `android12-5.10` … `android14-5.15`. Uses ccache via `CC="/usr/bin/ccache clang"`.
- Bazel (kleaf) `tools/bazel build --config=fast --config=stamp //common:kernel_aarch64/Image`: `android14-6.1` … `android16-6.12`.
- Two passes per cell: **Normal** and **Bypass** (patches `bad_version:` return in `kernel/module/version.c` [6.1+] or `kernel/module.c` [≤5.15] → `Bypass-Image` in the AnyKernel3 zip). The bypass is a flash-compat workaround, not a root-hide bypass.

## Runtime dependencies (cloned in setup-build-environment / actions)

- Kernel: `repo init -u https://android.googlesource.com/kernel/manifest -b common-<android>-<kernel>-<date> --depth=1` + `repo sync`. Deprecated branches get `deprecated/` prefix in the manifest.
- `kernel_patches` (WildKernels) — shared patches (incl. SUSFS pershoot 0001/0002, BBRv3).
- `AnyKernel3` (branch `gki-2.0`).
- SUSFS: `gitlab.com/simonpunk/susfs4ksu` branch `gki-<version>` (`susfs-setup` action).
- KernelSU-Next: pershoot fork via `kernel/setup.sh` on `dev-susfs` (`kernelsu` action).

## Key conventions / gotchas

- **`if: false` = intentional soft-disable**, not dead code. Currently disabled: ccache download/save/restore (all cache steps), performance patches, ABI-compare bypass, disk-cleanup action. Don't "clean up" them casually.
- **SUSFS "fake patches"**: `susfs-patches` modifies files so SUSFS's real patch applies cleanly, then `susfs-revert-patches` reverts the fakes. Both are sublevel-guarded; keep the two in sync when touching either.
- **Ignored rejects**: `i2c-nomadik.c.rej` and `common/mm/rmap.c.rej` are filtered out of reject collection (`scan-patch-rejects`, `rej` job) — they're known-harness/benign.
- **Reproducible timestamps**: `SOURCE_DATE_EPOCH`/`KBUILD_BUILD_TIMESTAMP`/`GIT_COMMITTER_DATE` pinned to `<patch-month>-05 04:20:00 UTC` (in build.yml), and branding patches `scripts/setlocalversion` (format differs for android15-6.6/6.12 vs others).
- **KSU version anchoring**: `KSU_VERSION = 30000 + commit count` counted at the **merge-base with official KernelSU-Next `dev`** (sync point), not the fork tip — so kernel version matches the official manager. Do not change the base/anchoring without understanding the release workflow.
- **BTF on android12-5.10** is a heavy special case: extra apt deps, built-from-source pahole 1.31 with a wrapper injecting `--skip_encoding_btf_enum64/decl_tag/type_tag`, host `dd` exposure, `ANDROID_KABI_USE` fix at sublevel 43. Many sub-fixes are commented out with detailed rationale — read before re-enabling.
- `retry()` shell helper (5 attempts, 5s backoff) is redefined inline per step; not shared.
- Release tags auto-increment `r<N>`; `render_release_body.py` fills `{{KSU_VERSION}}`, `{{SUSFS_BRANCHES}}`, etc. from env vars set by the release job.

## Verification

There is no local test/lint/typecheck. Before committing: validate `action.yml`/workflow YAML syntax (e.g. `python3 -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('.github/**/*.yml', recursive=True)]"`), JSON configs, and trace the `if:` gating logic manually. Watch for matching `contains(feature_set,...)` conditions and sublevel guards when editing.

## Local on-device work (differs from the CI repo purpose)

This checkout also contains gitignored local work trees for building the **rtl8188fu.ko** WiFi driver on the
phone itself: `kernel/` (android14-6.1 GKI source with prepared headers) and `rtl8188fu/`. The full
environment/operational rules live in `/AGENTS.md` (container root). Key points:

- The phone **reboots (brownout) under sustained CPU load** and `/tmp` is tmpfs (wiped on reboot). Build
  only with `-j1`, keep work in this repo dir, and don't commit the local `kernel/`/`rtl8188fu/` trees.
- The local kernel `Makefile` is edited to `SUBLEVEL = 145` / `EXTRAVERSION = -android14-Wild` and `.config`
  has `MODVERSIONS=y`, `WERROR` off, `DEBUG_INFO_BTF` off (GCC 15 traps) — headers were produced via
  `make -j1 ARCH=arm64 LOCALVERSION= prepare modules_prepare`.
- rtl8188fu build needs its `Makefile` set to `CONFIG_POWER_SAVING = n` and `CONFIG_WIFI_MONITOR = y` before
  `make -j1 ARCH=arm64 LOCALVERSION= KSRC=./kernel modules`. Driver fork is `kelebek333/rtl8188fu`.

## NetHunter branch (nethunter) — RTL8188FU + NetHunter kernel via CI

The `nethunter` branch builds a full kernel for the phone (`6.1.145-android14-Wild`) with the RTL8188FTV USB
WiFi driver and NetHunter configs, instead of relying on the fragile on-device module build:

- `.github/config/android14-6.1.json` is shrunk to **only sublevel 145 @ 2025-08** (the phone's os_patch_level,
  pinned build timestamp `2025-08-05 04:20:00 UTC`). Select `kernel_build_version: android14-6.1` +
  `feature_set: FULL` on the Actions page of this branch to build just that one kernel (Normal + Bypass).
- `.github/actions/add-rtl8188fu/` clones `kelebek333/rtl8188fu` (pinned to `c8c9570`, power-saving off,
  monitor on), copies it in-tree to `drivers/net/wireless/realtek/rtl8188fu/` and wires it into the realtek
  Kconfig/Makefile. It also flips on via `set-kernel-config` (which patches `common/arch/arm64/configs/gki_defconfig`):
  `CONFIG_WLAN_VENDOR_REALTEK=y` (required: `obj-$(CONFIG_WLAN_VENDOR_REALTEK)` in `drivers/net/wireless/Makefile`
  gates descent into `realtek/`), `CONFIG_RTL8188FU=m`, `CONFIG_CFG80211=m`, `CONFIG_NL80211_TESTMODE=y`,
  `CONFIG_CFG80211_CERTIFICATION_ONUS=y`, `CONFIG_CFG80211_REG_CELLULAR_HINTS=y`, `CONFIG_MAC80211=m`,
  `CONFIG_MAC80211_HWSIM=m`. GKI defconfig already ships most other NetHunter configs (TPROXY, MATCH_MAC,
  VLAN_8021Q, BT_HIDP, UINPUT, UHID).
- The action + module-extraction step are gated to `inputs.version == 'android14-6.1'` only.
- **Bazel/kleaf** is used for android14-6.1 (manifest includes `build/bazel_common_rules` + bazel prebuilts,
  NOT `build/build.sh`). `build-kernel` therefore builds the full `//common:kernel_aarch64` target for
  android14-6.1 (instead of `//common:kernel_aarch64/Image`) so the in-tree modules are exposed as outputs;
  `Image` still lands at `bazel-bin/common/kernel_aarch64/Image`. The extracted `rtl8188fu.ko` is copied into
  the AnyKernel3 zip and uploaded with the build artifacts.
- The phone's running kernel has `CONFIG_CFG80211 is not set` in-tree; its cfg80211/mac80211/bcmdhd modules
  load from the ROM's vendor_boot. The built `rtl8188fu.ko` carries proper modversions CRCs computed against
  the same 6.1.145 source, so it resolves cleanly against the vendor_boot cfg80211 module after flashing.
- Firmware `rtl8188fufw.bin` must exist on the phone at `/lib/firmware/rtlwifi/rtl8188fufw.bin` (already placed).
