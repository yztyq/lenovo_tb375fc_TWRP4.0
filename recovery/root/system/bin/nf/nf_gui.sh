#!/system/bin/sh
# nf_gui.sh —— 给 TWRP 界面按钮用的非交互入口（无 stdin、无提示）
# 用法:
#   nf_gui.sh ota <zip|payload.bin> [分区名...]   安装 OTA，只写指定的物理分区
#   nf_gui.sh backup [分区名...]                  备份（不给分区则用默认组合）
#   nf_gui.sh restore <目录> [img名...]           从目录还原（不给 img 则全部）
#   nf_gui.sh edl | magisk_off | magisk_on | log
#
# 2026-11-19 v3：分区名支持裸名（boot），由 nf_dev() 自动补当前槽；
#               备份/还原全流程带 MD5 校对。
NF=$(cd "$(dirname "$0")" && pwd)
. "$NF/nf_lib.sh"

TWRP_DIR=/sdcard/TWRP
# TB375FC 适配：没有独立 recovery 分区，默认备份不含 recovery
KEY_PARTS="boot init_boot vendor_boot dtbo vbmeta"

payload_from() {
    src=$1
    case "$src" in
        *.zip)
            W=/tmp/nf_payload
            rm -rf "$W"; mkdir -p "$W" || return 1
            nf_say "== 从 zip 取 payload.bin"
            unzip -o -q "$src" payload.bin -d "$W" || return 1
            [ -f "$W/payload.bin" ] || return 1
            echo "$W/payload.bin"
            ;;
        *)
            [ -f "$src" ] || return 1
            echo "$src"
            ;;
    esac
}

case "$1" in
ota)
    src=$2
    shift 2 2>/dev/null
    [ -n "$src" ] || nf_die "没有指定 OTA 文件"
    payload=$(payload_from "$src") || nf_die "取 payload.bin 失败: $src"
    nf_say "== payload: $payload"
    if [ $# -ge 1 ]; then
        sh "$NF/nf_ota.sh" "$payload" "$@"
    else
        sh "$NF/nf_ota.sh" "$payload"
    fi
    ;;
backup)
    # 2026-11-28 修：先 shift 掉 "backup" 本身，否则它会被当成一个分区名；
    # 目标目录优先用调用方给的 NF_DEST，其次 NF_ROOT（GUI 的存储位置选择：
    # 平板内存=/sdcard、SD 卡=/external_sd、U盘=/usb_otg），都没有才回落 /sdcard。
    shift
    if [ $# -ge 1 ]; then
        parts="$*"
    else
        parts="$KEY_PARTS"
    fi
    BASE="${NF_ROOT:-/sdcard}"
    DEST="${NF_DEST:-$BASE/TWRP/BF$(date +%Y%m%d%H%M%S)}"
    nf_say "== 备份到 $DEST"
    NF_DEST="$DEST" sh "$NF/nf_backup.sh" $parts
    ;;
restore)
    dir=$2
    shift 2 2>/dev/null
    [ -n "$dir" ] || nf_die "没有指定备份目录"
    [ -d "$dir" ] || nf_die "目录不存在: $dir"
    nf_say "== 使用备份 $dir"
    if [ $# -ge 1 ]; then
        files=""
        for n in "$@"; do
            # 依次尝试：原样、补 .img、按当前槽换真实名（boot -> boot_a.img）
            cand=""
            for c in "$n" "${n%.img}.img"; do
                [ -f "$dir/$c" ] && { cand="$dir/$c"; break; }
            done
            if [ -z "$cand" ]; then
                dev=$(nf_dev "$n")
                [ -n "$dev" ] && cand="$dir/$(basename "$dev").img"
            fi
            if [ -f "$cand" ]; then
                files="$files $cand"
            else
                nf_say "[跳过] 目录里没有: $n"
            fi
        done
        [ -n "$files" ] || nf_die "目录里没有选中的镜像"
    else
        files=""
        for f in "$dir"/*.img; do
            [ -f "$f" ] && files="$files $f"
        done
        [ -n "$files" ] || nf_die "目录里没有任何 .img"
    fi
    sh "$NF/nf_restore.sh" $files
    ;;
edl)
    nf_say "== 切到 9008（EDL）"
    sh "$NF/nf_edl.sh" --yes
    ;;
magisk_off)
    nf_say "== 关闭所有 Magisk 模组"
    sh "$NF/nf_magisk_off.sh" --yes
    ;;
magisk_on)
    nf_say "== 一键 root：Magisk v31.1 修补当前槽 init_boot"
    sh "$NF/nf_magisk_install.sh" --flash
    ;;
log)
    nf_say "== 导出恢复日志"
    sh /system/bin/twrp_log_dump.sh
    ;;
*)
    nf_say "用法: nf_gui.sh <ota <文件> [分区]|backup [分区]|restore <目录> [img]|edl|magisk_off|magisk_on|log>"
    exit 1
    ;;
esac

nf_say "== 结束（exit 0）"
exit 0
