#!/system/bin/sh
# Recovery uses host mappings; libgsi's booted file describes the previous boot.
marker=/metadata/gsi/dsu/booted
saved=/metadata/gsi/dsu/fox-last-booted
/system/bin/tb373fu_crypto_profile --prepare && exit 0
if [ "$(getprop ro.bootmode)" = recovery ] &&
   [ "$(getprop ro.gsid.image_running)" != 1 ] &&
   [ -z "$(getprop ro.boot.dsu_slot)" ] && [ -f "$marker" ]; then
    mv "$marker" "$saved" || exit 1
fi
/system/bin/tb373fu_crypto_profile --prepare
result=$?
if [ "$result" != 0 ] && [ -f "$saved" ] && [ ! -e "$marker" ]; then
    mv "$saved" "$marker"
fi
exit "$result"
