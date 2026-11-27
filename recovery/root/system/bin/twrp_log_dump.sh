#!/system/bin/sh
# TWRP 现场日志一键导出（v12）
# 用法：twrp_log_dump.sh
# 输出：/sdcard/TWRP/logs/<时间戳>/   （/sdcard 不可写时退到 /tmp/logs-<时间戳>）
set -u

stamp=$(date +%Y%m%d-%H%M%S)
root=/tmp/logs-$stamp
if [ -d /sdcard ] && echo "$stamp" > /sdcard/.twrp_wtest 2>/dev/null; then
    rm -f /sdcard/.twrp_wtest
    root=/sdcard/TWRP/logs/$stamp
fi
mkdir -p "$root" || { echo "[twrp] 无法创建目录: $root"; exit 1; }

[ -f /tmp/recovery.log ] && cp /tmp/recovery.log "$root/recovery.log" 2>/dev/null
[ -f /tmp/tb373fu_tee.log ] && cp /tmp/tb373fu_tee.log "$root/tb373fu_tee.log" 2>/dev/null
[ -f /tmp/recovery_last.log ] && cp /tmp/recovery_last.log "$root/recovery_last.log" 2>/dev/null
dmesg > "$root/dmesg.txt" 2>/dev/null
getprop > "$root/getprop.txt" 2>/dev/null
mount > "$root/mount.txt" 2>/dev/null
cat /proc/partitions > "$root/partitions.txt" 2>/dev/null
cat /proc/cmdline > "$root/cmdline.txt" 2>/dev/null
ls -l /dev/block/by-name > "$root/by-name.txt" 2>/dev/null
ls -l /proc/bus/input/devices > "$root/input-devices.txt" 2>/dev/null
cat /sys/class/leds/lcd-backlight/max_brightness > "$root/backlight_max.txt" 2>/dev/null
cat /sys/class/leds/lcd-backlight/brightness > "$root/backlight_cur.txt" 2>/dev/null

{
    echo "stamp=$stamp"
    echo "uname=$(uname -a)"
    echo "decrypt=$(getprop twrp.decrypt.done) user0=$(getprop twrp.user.0.decrypt)"
    echo "data_mounted=$(mount | grep -c ' /data ')"
} > "$root/summary.txt" 2>/dev/null

echo "[twrp] 日志已导出到: $root"
ls -l "$root" 2>/dev/null
exit 0
