#!/system/bin/sh
# nf_lib.sh —— 自定义功能公共函数（红魔 11 Pro+ / sm88XX / TWRP 4.0）
#
# 2026-11-19 修复：本机所有分区都是 A/B 命名（boot_a / init_boot_a …），
# 之前脚本直接找 /dev/block/by-name/boot 这类裸名，一定找不到，
# 导致备份/还原/OTA 全部失败。现在统一走 nf_dev() 解析：
#   裸名 boot -> 当前槽 boot_a
#   已带槽位 boot_a -> 原样返回
# 找不到则返回 1，由调用方决定跳过还是报错。

NF_LOG=${NF_LOG:-/tmp/nf.log}

nf_say() { echo "$*"; echo "$*" >>"$NF_LOG" 2>/dev/null; }
nf_die() { nf_say "[错误] $*"; exit 1; }

nf_byname() { echo "/dev/block/by-name/$1"; }

nf_slot() {
    s=$(getprop ro.boot.slot_suffix)
    [ -n "$s" ] || s=_a
    echo "$s"
}

# 解析分区设备节点（自动补当前槽后缀，也支持裸名/函数外的 _a _b）
nf_dev() {
    name=$1
    if [ -e "/dev/block/by-name/$name" ]; then
        echo "/dev/block/by-name/$name"
        return 0
    fi
    slot=$(nf_slot)
    if [ -e "/dev/block/by-name/$name$slot" ]; then
        echo "/dev/block/by-name/$name$slot"
        return 0
    fi
    other=_a
    [ "$slot" = "_a" ] && other=_b
    if [ -e "/dev/block/by-name/$name$other" ]; then
        echo "/dev/block/by-name/$name$other"
        return 0
    fi
    return 1
}

# 逻辑分区（super 里）判断：by-name 没有节点但 mapper 有
nf_is_logical() { [ -e "/dev/block/mapper/$1" ]; }

# 分区字节数：blockdev → sysfs → /proc/partitions 依次兜底
nf_size() {
    sz=$(blockdev --getsize64 "$1" 2>/dev/null)
    if [ -n "$sz" ] && [ "$sz" -gt 0 ] 2>/dev/null; then echo "$sz"; return; fi
    real=$(readlink -f "$1" 2>/dev/null)
    nb=$(basename "$real")
    sec=$(cat "/sys/class/block/$nb/size" 2>/dev/null)
    if [ -n "$sec" ]; then echo $((sec * 512)); return; fi
    awk -v n="$nb" '$4==n {print $3*1024; exit}' /proc/partitions 2>/dev/null
}

nf_human() {
    awk -v b="$1" 'BEGIN{split("B KB MB GB TB",u," ");i=1;while(b>=1024&&i<5){b/=1024;i++}printf "%.1f%s",b,u[i]}'
}

nf_free() {
    df -k "$1" 2>/dev/null | tail -1 | awk '{print $4*1024}'
}

nf_md5() { md5sum "$1" 2>/dev/null | cut -d' ' -f1; }

# 大数比较（sh 的 [ ] 是 32 位，几 GB 会溢出，统一交给 awk）
nf_ge() { awk -v a="$1" -v b="$2" 'BEGIN{exit !(a >= b)}'; }
nf_add() { awk -v s="$1" -v n="$2" 'BEGIN{printf "%.0f", s + n}'; }

# /data 是否已解密可用
nf_data_ready() {
    [ -d /data/media/0 ] && [ -d /data/adb ] && return 0
    [ -d /data/adb ] && return 0
    mount | grep -q " /data " && return 0
    return 1
}

# 列出可备份的物理分区（含槽位，排除杂项）
nf_list_parts() {
    for d in /dev/block/by-name/*; do
        n=$(basename "$d")
        case "$n" in
            ALIGN_TO_128K_*|cdt|ddr|devinfo|dpm|efisp|fsg|fsc|fs_bkup|apdp|apdpb|connsec|frp|misc|persist*|rawdump|secdata|xbl*) continue ;;
        esac
        [ -e "$d" ] && echo "$n"
    done
}
