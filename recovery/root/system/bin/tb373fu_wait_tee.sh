#!/system/bin/sh
# TB375FC recovery: bring up the Beanpod (microtrust) TEE stack, then start TWRP.
# v11: 在 v10 的并行等待基础上，面板被识别后再额外等 SETTLE_POLLS 轮（0.5s/轮），
#      确保 NVTCapacitiveTouchScreen 固件加载完成后再进 TWRP 主界面，
#      避免进界面后前几秒触摸全丢。
log=/tmp/tb373fu_tee.log
: > "$log"

SETTLE_POLLS=8

rm -rf /system/etc/vintf/manifest /vendor/etc/vintf/manifest

mkdir -p /mnt/vendor/persist
mount -t ext4 -o ro /dev/block/by-name/persist /mnt/vendor/persist 2>/dev/null
if ! mount | grep -q " /metadata "; then
    mount -t f2fs -o ro,nosuid,nodev,noatime /dev/block/by-name/metadata /metadata 2>/dev/null
fi

setprop ctl.start teei_daemon
km_started=0
touch_ready=0
touch_at=-1
i=0
while [ $i -lt 40 ]; do
    if [ $km_started -eq 0 ] && [ "$(getprop vendor.soter.teei.init)" = "INIT_OK" ]; then
        setprop ctl.start vendor.keymint-beanpod
        setprop ctl.start vendor.gatekeeper-beanpod
        km_started=1
    fi
    if [ $touch_ready -eq 0 ] && grep -q "NVTCapacitiveTouchScreen" /proc/bus/input/devices 2>/dev/null; then
        touch_ready=1
        touch_at=$i
    fi
    if [ $km_started -eq 1 ] && [ $touch_ready -eq 1 ] &&
       [ "$(getprop init.svc.vendor.keymint-beanpod)" = "running" ] &&
       [ "$(getprop init.svc.vendor.gatekeeper-beanpod)" = "running" ]; then
        break
    fi
    sleep 0.5
    i=$((i + 1))
done

# 面板已枚举，再留出固件加载/校准的稳定时间
s=0
while [ $s -lt $SETTLE_POLLS ]; do
    sleep 0.5
    s=$((s + 1))
done
sleep 1

echo "teei=$(getprop vendor.soter.teei.init) km=$(getprop init.svc.vendor.keymint-beanpod) gk=$(getprop init.svc.vendor.gatekeeper-beanpod) touch_at=$touch_at polls=$i settle=$s" >> "$log"
echo "touch_dev=$(grep -c 'NVTCapacitiveTouchScreen' /proc/bus/input/devices 2>/dev/null) kmver=$(getprop vendor.soter.teei.km.version) persist=$(getprop vendor.soter.teei.persist)" >> "$log"

setprop vendor.recovery.crypto.profile ready
setprop crypto.ready 1
setprop ctl.start recovery
# keystore2 不参与 TWRP 解密，放在 TWRP 之后启动，避免它的 watchdog 线程阻塞启动。
setprop ctl.start keystore2
exit 0
