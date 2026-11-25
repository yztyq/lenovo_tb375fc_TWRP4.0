# TWRP device tree — Lenovo Xiaoxin Pad Pro 12.7 2025 (TB375FC)

MediaTek MT6897 (Dimensity 8300) tablet running ZUXOS 1.1.04.287 (Android 15 base,
vendor 14). TWRP 4.0 / Android 16 tree.

The layout and build style follow
[`yztyq/android_device_zte_sm88XX-twrp`](https://github.com/yztyq/android_device_zte_sm88XX-twrp)
(RedMagic 11 Pro+), which builds against the **minimal** TWRP manifest
`TWRP-Test/platform_manifest_twrp_aosp@twrp-16.0` — small enough for a hosted
GitHub runner, unlike the ~85 GB full OrangeFox `fox_16.0` tree.

## Why this tree exists

Six self-built TWRP 14.1 `vendor_boot` images were flashed and every one either
black-screened or reboot-looped. A prebuilt OrangeFox R12 image from another
porter did start init (`adb devices` showed recovery) but reboot-looped because
`adb shell` died on `Could not set SELinux context for subprocess`. No
recovery log could ever be pulled, so the loop was never proven by logs.

This tree therefore does three things differently:

1. **Builds against the minimal manifest** so CI actually finishes the sync.
2. **Uses GKI 6.1** (`kernel/prebuilts/6.1/arm64/kernel-6.1`), matching the
   device's 6.1.138 kernel generation, instead of the 6.12 prebuilt used by the
   SM88XX tree (whose vendor modules would not load).
3. **Never fakes a patch level.** `PLATFORM_SECURITY_PATCH` is the ROM's real
   `2025-09-05`. KeyMint binds key blobs to the ROM's own values, so a
   `2099-12-31` placeholder would make FBE decryption fail permanently.

## Device facts (measured over adb, do not guess)

| item | value |
|---|---|
| `ro.boot.hardware` | **mt8792** → the rc must be `init.recovery.mt8792.rc` |
| `ro.board.platform` | mt6897 (Dimensity 8300) |
| `ro.crypto.state` / `type` | `encrypted` / `file` → **FBE only, no FDE** |
| vendor_boot partition | 64 MiB (`0x4000000`), header v4, page 4096 |
| recovery partition | **none** — recovery lives in vendor_boot's second fragment |
| `by-name`, logical | `system` / `vendor` are in `super`; never mount them by name |
| patch levels | system `2025-09-05`, vendor `2024-10-05` |

## Build

The workflow is `Build TWRP TB375FC` (manual dispatch). Defaults:

| input | default |
|---|---|
| `manifest_url` | `https://github.com/TWRP-Test/platform_manifest_twrp_aosp` |
| `manifest_branch` | `twrp-16.0` |
| `device_path` | `lenovo/tb375fc` |
| `lunch_target` | `twrp_tb375fc-aosp_current-eng` |
| `build_partition` | `vendor_boot` |

The artifact is timestamped: `vendor_boot_tb375fc_<UTC>_<sha7>.img`, plus a
`*.build_info.txt` carrying size, md5, sha256, commit and manifest.

Locally, with a synced tree, copy this repo to `device/lenovo/tb375fc` and run
`lunch twrp_tb375fc-aosp_current-eng && mka vendorbootimage`.

## Flashing

Only `vendor_boot` is replaced. The `vbmeta` is **never** touched, and no
verification-disabling vbmeta is produced — the point is for the modified
`vendor_boot` to still pass verification.

```
fastboot flash vendor_boot_a vendor_boot_tb375fc_<...>.img
fastboot reboot recovery
```

Slot is `a` (`current-slot=a`).

## Static check

`bash scripts/validate.sh` — 40+ assertions covering platform names, the kernel
generation, crypto flags, the real patch level, fstab hazards (`by-name/system`,
`by-name/vendor`, mangled `avb_keys` tokens) and artifact naming. Runs in CI on
every push.
