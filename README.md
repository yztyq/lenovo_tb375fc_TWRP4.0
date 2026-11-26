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
| vendor_boot fragments | **type=1 platform** 25,863,198 B (stock, 222 `.ko`) + **type=2 recovery** ~30.5 MB (TWRP root) |
| `by-name`, logical | `system` / `vendor` are in `super`; never mount them by name |
| patch levels | system `2025-09-05`, vendor `2024-10-05` |

> **2026-11-26 修订**：本仓库原先走「单 lz4 流」方案（`MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT := true` + `TARGET_NO_RECOVERY := true`）。在真机上验证过的那个能进 recovery 的包是**两片**结构，单流方案编出来的 platform 片只有 4 字节、recovery 片退化成 AOSP recovery，刷进去进不了 recovery。现已全部改成两片，并把官方 platform 片作为 `prebuilt/platform_ramdisk.lz4` 入仓，由 `scripts/splice_platform.py` 在打包时拼回去。

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

Locally, with a synced tree, copy this repo to `device/lenovo/tb375fc` and run:

```sh
lunch twrp_tb375fc-aosp_current-eng
mka vendorbootimage      # 产物 out/target/product/tb375fc/vendor_boot.img 不能直接刷

# 必做：把官方 platform 片拼回去（platform type=1 / recovery type=2，重编码 0000+zstd）
python3 device/lenovo/tb375fc/scripts/splice_platform.py \
    --input out/target/product/tb375fc/vendor_boot.img \
    --platform device/lenovo/tb375fc/prebuilt/platform_ramdisk.lz4 \
    --output out/target/product/tb375fc/vendor_boot_TWRP_64MB.img
```

CI 里这一步是 workflow 的 `Splice official platform ramdisk`，artifact 直接给拼好的
`vendor_boot_tb375fc_<UTC>_<sha7>.img`。

### vendor_boot 的两片结构（必须理解）

| # | 分片类型 | 内容 | 来源 |
|---|---|---|---|
| 0 | `type=1` platform | `first_stage_ramdisk/` + `lib/modules/`（222 个 6.1.138 `.ko`） | 官方 vendor_boot，`prebuilt/platform_ramdisk.lz4` |
| 1 | `type=2` recovery | TWRP 根文件系统（`twres`、`sbin`、`system/bin/twrp` …） | 本树 `recovery/root` |

两片相加必须 ≤ 64 MiB（实测可用包 vrs = 56,436,946 B）。分片表在 dtb 之后一个
page 起始处，长度/数量/条目大小写在头 2112 / 2116 / 2120，条目 108 字节、无表头；
bootloader 只按条目里的 `type` 选片，所以 type 位写错等于没做 recovery。

`recovery/root/lib/modules` 是**空**的：模块由 platform 片提供，放进 recovery 片会把它
从约 30 MB 撑到约 45 MB，64 MiB 装不下两片。

## Flashing

Only `vendor_boot` is replaced. The `vbmeta` is **never** touched, and no
verification-disabling vbmeta is produced — the point is for the modified
`vendor_boot` to still pass verification.

> **AVB 备注**：设备实测能进 recovery 的那个包**没有 AVB footer**（末尾没有 `AVBf`），
> `ro.boot.verifiedbootstate=orange` 也说明 bootloader 处于解锁容忍状态。本树现在给
> vendor_boot 加了 AOSP test key 的 footer；如果新包刷进去又退回系统，先把
> `BOARD_AVB_ENABLE` 关掉（去掉 footer）再对比，这是第一优先排查项。

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
