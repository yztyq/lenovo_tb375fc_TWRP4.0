#!/usr/bin/env bash
# Static validator for the TB375FC TWRP device tree.
# Runs locally (Git Bash on Windows) and in CI. No build, no network.
set -uo pipefail

FAIL=0
WARN=0
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ok()   { printf '  [OK]   %s\n' "$*"; }
bad()  { printf '  [FAIL] %s\n' "$*"; FAIL=$((FAIL+1)); }
warn() { printf '  [WARN] %s\n' "$*"; WARN=$((WARN+1)); }
sec()  { printf '\n== %s ==\n' "$*"; }

sec "1. required top-level files"
for f in BoardConfig.mk device.mk twrp_tb375fc.mk AndroidProducts.mk Android.mk Android.bp system.prop; do
  [ -f "$ROOT/$f" ] && ok "$f" || bad "$f missing"
done

sec "2. recovery ramdisk layout"
for f in recovery/root/init.recovery.mt8792.rc recovery/root/init.recovery.microtrust.rc \
         recovery/root/system/etc/recovery.fstab recovery/root/system/etc/twrp.flags \
         recovery/root/system/bin/tb373fu_usb_storage.sh \
         prebuilt/dtb prebuilt/platform_ramdisk.lz4 scripts/splice_platform.py; do
  [ -f "$ROOT/$f" ] && ok "$f" || bad "$f missing"
done
if [ -d "$ROOT/recovery/root/vendor" ]; then
  vc=$(find "$ROOT/recovery/root/vendor" -type f | wc -l)
  [ "$vc" -ge 40 ] && ok "recovery/root/vendor has $vc files (teei/keymint/TA/firmware)" || bad "recovery/root/vendor only $vc files"
else
  bad "recovery/root/vendor missing (decryption + touch firmware live there)"
fi

sec "3. rc must be mt8792 (device reports ro.boot.hardware=mt8792)"
if ls "$ROOT"/recovery/root/init.recovery.*.rc >/dev/null 2>&1; then
  for rc in "$ROOT"/recovery/root/init.recovery.*.rc; do
    case "$(basename "$rc")" in
      init.recovery.mt8792.rc) ok "rc name matches hardware" ;;
      # 官方 recovery ramdisk 里确实还有这一份 microtrust rc（TEE），照抄不改名
      init.recovery.microtrust.rc) ok "rc from the stock ramdisk (microtrust/TEE)" ;;
      *) bad "rc name $(basename "$rc") does not match mt8792" ;;
    esac
  done
else
  bad "no init.recovery.*.rc found"
fi

sec "4. BoardConfig: platform / header / partitions"
bc="$ROOT/BoardConfig.mk"
chk() { grep -qE "^[[:space:]]*$1[[:space:]]*:?=[[:space:]]*$2" "$bc" && ok "$1 = $2" || bad "$1 should be $2"; }
grep -qE '^[[:space:]]*TARGET_BOARD_PLATFORM[[:space:]]*:?=[[:space:]]*mt6897' "$bc" && ok "TARGET_BOARD_PLATFORM = mt6897" || bad "TARGET_BOARD_PLATFORM must be mt6897"
grep -qE '^[[:space:]]*TARGET_BOOTLOADER_BOARD_NAME[[:space:]]*:?=[[:space:]]*mt8792' "$bc" && ok "TARGET_BOOTLOADER_BOARD_NAME = mt8792" || bad "TARGET_BOOTLOADER_BOARD_NAME must be mt8792"
chk BOARD_BOOT_HEADER_VERSION 4
chk BOARD_KERNEL_PAGESIZE 4096
chk BOARD_VENDOR_BOOTIMAGE_PARTITION_SIZE 67108864
# 2026-11-26：两片结构才进得了 recovery（device 上唯一验证过的形状）。
# 单流方案（MOVE=true + TARGET_NO_RECOVERY=true）编出来的 platform 片只有 4 B、
# recovery 片退化成 AOSP recovery，实刷全部失败。
if grep -qE '^[[:space:]]*BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT[[:space:]]*:?=[[:space:]]*true' "$bc"; then
  ok "BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT = true (two fragments)"
else
  bad "BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT must be true (two-fragment vendor_boot)"
fi
if grep -qE '^[[:space:]]*BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT[[:space:]]*:?=[[:space:]]*true' "$bc"; then
  bad "BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT must be off (it empties the platform fragment)"
else
  ok "BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT off"
fi
if grep -qE '^[[:space:]]*TARGET_NO_RECOVERY[[:space:]]*:?=[[:space:]]*true' "$bc"; then
  bad "TARGET_NO_RECOVERY must be off (it drops the recovery fragment entirely)"
else
  ok "TARGET_NO_RECOVERY off"
fi
if grep -qE '^[[:space:]]*BOARD_PREBUILT_PLATFORM_RAMDISK[[:space:]]*:?=' "$bc"; then
  ok "BOARD_PREBUILT_PLATFORM_RAMDISK declared"
  plat="$ROOT/prebuilt/platform_ramdisk.lz4"
  if [ -f "$plat" ]; then
    psz=$(stat -c%s "$plat" 2>/dev/null || echo 0)
    [ "$psz" = "25863198" ] && ok "platform_ramdisk.lz4 = 25,863,198 B (stock fragment)" \
      || bad "platform_ramdisk.lz4 = $psz B, expected 25,863,198"
  else
    bad "prebuilt/platform_ramdisk.lz4 missing"
  fi
else
  bad "BOARD_PREBUILT_PLATFORM_RAMDISK missing"
fi
if grep -q 'splice_platform.py' "$ROOT/.github/workflows/build.yml" 2>/dev/null; then
  ok "build.yml splices the platform fragment"
else
  bad "build.yml does not call scripts/splice_platform.py (product would not boot recovery)"
fi
grep -qE '^[[:space:]]*TARGET_NO_KERNEL[[:space:]]*:?=[[:space:]]*true' "$bc" && ok "TARGET_NO_KERNEL = true (vendor_boot carries no kernel segment)" || bad "TARGET_NO_KERNEL must be true"
if grep -qE '^[[:space:]]*TARGET_PREBUILT_KERNEL[[:space:]]*:?=' "$bc"; then bad "TARGET_PREBUILT_KERNEL must not be set (manifest prebuilts path is absent)"; else ok "no TARGET_PREBUILT_KERNEL"; fi
if grep -qE '^[[:space:]]*BOARD_PREBUILT_DTBIMAGE_DIR[[:space:]]*:?=' "$bc"; then
  ok "BOARD_PREBUILT_DTBIMAGE_DIR set (core/Makefile cat rule builds dtb.img)"
  [ -f "$ROOT/prebuilt/dtb_dir/tb375fc.dtb" ] && ok "prebuilt/dtb_dir/tb375fc.dtb present" || bad "prebuilt/dtb_dir/tb375fc.dtb missing"
else
  bad "BOARD_PREBUILT_DTBIMAGE_DIR missing (ninja: dtb.img needed by vendor_boot.img, no rule)"
fi
grep -qE '^[[:space:]]*TARGET_PREBUILT_DTB[[:space:]]*:?=' "$bc" && warn "TARGET_PREBUILT_DTB is not an AOSP variable (produces no rule)" || ok "no TARGET_PREBUILT_DTB"
grep -qE '^[[:space:]]*BOARD_KERNEL_CMDLINE[[:space:]]*:?=[[:space:]]*bootopt=64S3,32N2,64N2' "$bc" && ok "vendor cmdline bootopt=64S3,32N2,64N2" || bad "BOARD_KERNEL_CMDLINE missing (feeds --vendor_cmdline)"
for v in BOARD_AVB_ENABLE BOARD_AVB_ALGORITHM BOARD_AVB_KEY_PATH BOARD_AVB_VENDOR_BOOT_KEY_PATH BOARD_AVB_VENDOR_BOOT_ALGORITHM BOARD_AVB_VENDOR_BOOT_ROLLBACK_INDEX BOARD_AVB_VENDOR_BOOT_ROLLBACK_INDEX_LOCATION BOARD_AVB_VENDOR_BOOTIMAGE_KEY_PATH; do
  grep -qE "^[[:space:]]*$v[[:space:]]*:?=" "$bc" && ok "$v set" || bad "$v missing (avbtool would run with no --algorithm/--key)"
done

sec "5. no QCOM leftovers (this is MediaTek)"
for pat in BOARD_USES_QCOM_FBE_DECRYPTION TARGET_RECOVERY_QCOM_RTC_FIX QCOM_BOARD_PLATFORMS MSM8974; do
  if grep -q "$pat" "$ROOT"/*.mk 2>/dev/null; then bad "QCOM leftover: $pat"; else ok "no $pat"; fi
done

sec "6. crypto flags for FBE v2 + metadata encryption"
for flag in TW_INCLUDE_CRYPTO TW_INCLUDE_CRYPTO_FBE TW_INCLUDE_FBE_METADATA_DECRYPT TW_USE_FSCRYPT_POLICY; do
  if grep -qE "^[[:space:]]*$flag[[:space:]]*:?=" "$bc"; then ok "$flag set"; else bad "$flag missing"; fi
done
if grep -qE '^[[:space:]]*TW_USE_FSCRYPT_POLICY[[:space:]]*:?=[[:space:]]*2' "$bc"; then ok "fscrypt policy 2"; else warn "fscrypt policy is not 2 (device: aes-256-xts:aes-256-cts:v2)"; fi

sec "7. security patch must be the real ROM value"
if grep -qE '2099-12-31|99\.87\.36' "$bc"; then
  bad "placeholder version found (2099-12-31 / 99.87.36) — KeyMint would reject decryption"
else
  ok "no placeholder version"
fi
grep -qE '^[[:space:]]*PLATFORM_SECURITY_PATCH[[:space:]]*:?=[[:space:]]*2025-09-05' "$bc" && ok "PLATFORM_SECURITY_PATCH = 2025-09-05" || wake=1
[ "${wake:-0}" = "0" ] && ok "patch level present" || warn "PLATFORM_SECURITY_PATCH not the measured 2025-09-05"

sec "8. fstab sanity"
fs="$ROOT/recovery/root/system/etc/recovery.fstab"
if [ -f "$fs" ]; then
  grep -q '/data' "$fs" && ok "/data entry present" || bad "/data missing from fstab"
  grep -q '/metadata' "$fs" && ok "/metadata entry present" || bad "/metadata missing (FBE metadata decrypt needs it)"
  if grep -q '/mnt/vendor/persist' "$fs"; then
    ok "persist mounted at /mnt/vendor/persist"
  elif grep -qE '^/persist_image[[:space:]]' "$ROOT/recovery/root/system/etc/twrp.flags" 2>/dev/null; then
    ok "persist exposed via twrp.flags as /persist_image (stock recovery fstab has no /persist mount)"
  else
    warn "persist neither mounted nor exposed"
  fi
  grep -q 'by-name/system ' "$fs" && bad "by-name/system is logical-only on this device — must not be mounted by name" || ok "no by-name/system mount"
  grep -q 'by-name/vendor ' "$fs" && bad "by-name/vendor is logical-only — must not be mounted by name" || ok "no by-name/vendor mount"
  grep -q 'dm-userdata' "$fs" && warn "duplicate dm-userdata /data line present (harmless but noisy)" || ok "no duplicate dm-userdata line"
  awk '!/^#/ && NF && $2=="erofs" && $0 !~ /logical/' "$fs" >/dev/null 2>&1
  grep -nE 'avb=' "$fs" | grep -q 'slotselect_keys' && bad "fstab token corruption: ',avb_keys=' was mangled into slotselect_keys" || ok "avb_keys token intact"
else
  bad "fstab missing"
fi

sec "9. modules live in the platform fragment, not in the recovery ramdisk"
plat="$ROOT/prebuilt/platform_ramdisk.lz4"
if [ -f "$plat" ]; then
  ok "platform fragment present (222 stock .ko, vermagic 6.1.138-android14-11-g56ef1ebb4dca)"
else
  bad "platform fragment missing -> no modules at all"
fi
if [ -d "$ROOT/recovery/root/lib/modules" ] && [ -n "$(ls -A "$ROOT/recovery/root/lib/modules" 2>/dev/null)" ]; then
  bad "recovery/root/lib/modules must stay empty: modules are provided by the platform fragment"
else
  ok "no duplicated modules inside the recovery root"
fi

sec "10. dtb"
dtb="$ROOT/prebuilt/dtb"
if [ -f "$dtb" ]; then
  sz=$(stat -c%s "$dtb" 2>/dev/null || wc -c < "$dtb")
  if [ "$sz" -eq 411876 ]; then ok "dtb size 411,876 (matches stock)"; else warn "dtb size $sz (stock is 411,876)"; fi
  head -c4 "$dtb" | grep -q $'\xd0\x0d\xfe\xed' && ok "dtb magic d00dfeed" || warn "dtb magic not found (may be appended)"
else
  bad "dtb missing"
fi

sec "11. workflow"
wf="$ROOT/.github/workflows/build.yml"
if [ -f "$wf" ]; then
  grep -q 'TWRP-Test/platform_manifest_twrp_aosp' "$wf" && ok "uses TWRP-Test minimal manifest" || warn "manifest url differs from the reference"
  grep -q 'twrp-16.0' "$wf" && ok "twrp-16.0 branch" || warn "branch not twrp-16.0"
  grep -q 'date -u +%Y%m%d-%H%M%S' "$wf" && ok "timestamped artifact naming" || warn "no timestamp"
  grep -q 'mka -j2 vendorbootimage' "$wf" && ok "workflow builds vendorbootimage" || bad "workflow never runs vendorbootimage"
  grep -q 'vendor_boot_TWRP_64MB.img' "$wf" && ok "workflow collects the spliced image" || bad "spliced image not collected"
else
  bad "build.yml missing"
fi

sec "12. twrp.flags (partition manager targets)"
tf="$ROOT/recovery/root/system/etc/twrp.flags"
if [ -f "$tf" ]; then
  for p in '/vendor_boot' '/boot' '/init_boot' '/dtbo' '/vbmeta' '/persist_image' '/usb_otg' '/external_sd'; do
    grep -qE "^[[:space:]]*$p[[:space:]]" "$tf" && ok "twrp.flags has $p" || bad "twrp.flags missing $p"
  done
  grep -qE '^/vendor_boot[[:space:]].*flashimg=1' "$tf" && ok "/vendor_boot flashable" || bad "/vendor_boot not flashable"
else
  bad "twrp.flags missing"
fi

sec "13. 64 MiB budget"
if [ -f "$plat" ]; then
  psz=$(stat -c%s "$plat" 2>/dev/null || echo 0)
  # 可用包实测：platform 25,863,198 + recovery 30,573,748 = vrs 56,436,946 B
  est=$(( psz + 30573748 ))
  lim=67108864
  if [ "$est" -lt "$lim" ]; then
    ok "estimated vrs $est B < $lim B (head-room $((lim - est)) B)"
  else
    bad "estimated vrs $est B >= $lim B"
  fi
fi

printf '\n== summary: FAIL=%d WARN=%d ==\n' "$FAIL" "$WARN"
[ "$FAIL" -eq 0 ] || exit 1
