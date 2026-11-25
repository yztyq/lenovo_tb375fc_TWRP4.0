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
for f in recovery/root/init.recovery.mt8792.rc recovery/root/system/etc/recovery.fstab prebuilt/dtb; do
  [ -f "$ROOT/$f" ] && ok "$f" || bad "$f missing"
done

sec "3. rc must be mt8792 (device reports ro.boot.hardware=mt8792)"
if ls "$ROOT"/recovery/root/init.recovery.*.rc >/dev/null 2>&1; then
  for rc in "$ROOT"/recovery/root/init.recovery.*.rc; do
    case "$(basename "$rc")" in
      init.recovery.mt8792.rc) ok "rc name matches hardware" ;;
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
chk BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT true
chk BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT true
chk TARGET_NO_RECOVERY true
grep -qE '^[[:space:]]*TARGET_NO_KERNEL[[:space:]]*:?=[[:space:]]*true' "$bc" && ok "TARGET_NO_KERNEL = true (vendor_boot carries no kernel segment)" || bad "TARGET_NO_KERNEL must be true"
if grep -qE '^[[:space:]]*TARGET_PREBUILT_KERNEL[[:space:]]*:?=' "$bc"; then bad "TARGET_PREBUILT_KERNEL must not be set (manifest prebuilts path is absent)"; else ok "no TARGET_PREBUILT_KERNEL"; fi
grep -qE '^[[:space:]]*TARGET_PREBUILT_DTB[[:space:]]*:?=' "$bc" && ok "TARGET_PREBUILT_DTB set" || bad "TARGET_PREBUILT_DTB missing"

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
  grep -q '/mnt/vendor/persist' "$fs" && ok "persist mounted at /mnt/vendor/persist" || warn "persist not mounted"
  grep -q 'by-name/system ' "$fs" && bad "by-name/system is logical-only on this device — must not be mounted by name" || ok "no by-name/system mount"
  grep -q 'by-name/vendor ' "$fs" && bad "by-name/vendor is logical-only — must not be mounted by name" || ok "no by-name/vendor mount"
  grep -q 'dm-userdata' "$fs" && warn "duplicate dm-userdata /data line present (harmless but noisy)" || ok "no duplicate dm-userdata line"
  awk '!/^#/ && NF && $2=="erofs" && $0 !~ /logical/' "$fs" >/dev/null 2>&1
  grep -nE 'avb=' "$fs" | grep -q 'slotselect_keys' && bad "fstab token corruption: ',avb_keys=' was mangled into slotselect_keys" || ok "avb_keys token intact"
else
  bad "fstab missing"
fi

sec "9. modules"
ko=$(find "$ROOT/recovery/root/lib/modules" -name '*.ko' 2>/dev/null | wc -l)
if [ "$ko" -ge 100 ]; then ok "$ko vendor modules staged"; else bad "only $ko modules staged (expected ~222)"; fi
if command -v file >/dev/null 2>&1 && [ "$ko" -gt 0 ]; then
  one=$(find "$ROOT/recovery/root/lib/modules" -name '*.ko' | head -1)
  file "$one" | grep -q 'ARM aarch64' && ok "module arch is aarch64" || warn "module arch not recognised"
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
else
  bad "build.yml missing"
fi

printf '\n== summary: FAIL=%d WARN=%d ==\n' "$FAIL" "$WARN"
[ "$FAIL" -eq 0 ] || exit 1
