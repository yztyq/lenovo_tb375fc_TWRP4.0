#!/system/bin/sh

# Maintain stable recovery-only links for the first removable SCSI disk.
# Internal UFS LUNs sda/sdb/sdc report removable=0 and are never selected.
while true; do
    selected=""
    for sysdev in /sys/class/block/sd?; do
        test -r "$sysdev/removable" || continue
        test "$(cat "$sysdev/removable" 2>/dev/null)" = "1" || continue
        name=${sysdev##*/}
        device="/dev/block/$name"
        test -b "$device" || continue
        selected=$device
        partition=""
        for candidate in /dev/block/${name}[0-9]*; do
            test -b "$candidate" || continue
            partition=$candidate
            break
        done
        ln -sf "$device" /dev/block/usb_otg
        if test -n "$partition"; then
            ln -sf "$partition" /dev/block/usb_otg1
        else
            ln -sf "$device" /dev/block/usb_otg1
        fi
        break
    done
    if test -z "$selected"; then
        rm -f /dev/block/usb_otg /dev/block/usb_otg1
    fi

    # Maintain stable recovery-only links for MicroSD card (MSDC1 11240000.mmc)
    # Handles both mmcblk0 and mmcblk1, partitioned (*p1) and unpartitioned whole-disk.
    sd_dev=""
    if test -b /dev/block/mmcblk1; then
        sd_dev="/dev/block/mmcblk1"
    elif test -b /dev/block/mmcblk0; then
        sd_dev="/dev/block/mmcblk0"
        if ! test -e /dev/block/mmcblk1; then
            ln -sf /dev/block/mmcblk0 /dev/block/mmcblk1
        fi
    fi

    if test -n "$sd_dev"; then
        if test -b "${sd_dev}p1"; then
            ln -sf "${sd_dev}p1" /dev/block/mmcblk1p1
        else
            ln -sf "$sd_dev" /dev/block/mmcblk1p1
        fi
    else
        if test -L /dev/block/mmcblk1p1; then
            rm -f /dev/block/mmcblk1p1
        fi
        if test -L /dev/block/mmcblk1; then
            rm -f /dev/block/mmcblk1
        fi
    fi
    sleep 1
done
