#!/system/bin/sh
# nf_magisk_install.sh —— 用 Magisk v31.1 修补当前槽 init_boot 并写回
# 用法:
#   nf_magisk_install.sh          只看状态
#   nf_magisk_install.sh --dry    只生成补丁镜像到 /sdcard/nf_magisk_new-boot.img
#   nf_magisk_install.sh --flash  真写 init_boot 分区
#
# 资源: /system/bin/nf/magisk/ 下已解出来的 boot_patch.sh + magiskboot/magiskinit/magisk/init-ld
NF=$(cd "$(dirname "$0")" && pwd); . "$NF/nf_lib.sh"

ASSET=${NF_MAGISK_DIR:-$NF/magisk}
MODE=$1

SLOT=$(nf_slot)
PART="init_boot$SLOT"
DEV="/dev/block/by-name/$PART"
[ -e "$DEV" ] || nf_die "找不到分区 $PART"
[ -f "$ASSET/boot_patch.sh" ] || nf_die "缺补丁资源: $ASSET/boot_patch.sh"

if [ -z "$MODE" ]; then
    nf_say "当前槽   : $SLOT"
    nf_say "目标分区 : $PART  $(nf_human "$(nf_size "$DEV")")"
    nf_say "补丁资源 : $ASSET"
    nf_say "写盘请用 : nf_magisk_install.sh --flash"
    exit 0
fi

W=/tmp/nf_magisk
rm -rf "$W"
mkdir -p "$W" || nf_die "无法创建 $W"
cp -r "$ASSET"/* "$W"/ 2>/dev/null || nf_die "复制补丁资源失败"
cd "$W" || nf_die "无法进入 $W"
chmod 755 magiskboot magiskinit magisk init-ld 2>/dev/null

nf_say "== 读取 $PART"
dd if="$DEV" of="$W/init_boot.img" bs=1M 2>/dev/null || nf_die "读取 $PART 失败"

nf_say "== 修补（Magisk boot_patch.sh）"
KEEPVERITY=true KEEPFORCEENCRYPT=true sh "$W/boot_patch.sh" "$W/init_boot.img" || nf_die "boot_patch.sh 失败"

[ -f "$W/new-boot.img" ] || nf_die "没有产出 new-boot.img"
nf_say "补丁镜像 : $(nf_human "$(stat -c %s "$W/new-boot.img")")  md5=$(nf_md5 "$W/new-boot.img")"

if [ "$MODE" = "--dry" ]; then
    OUT=${NF_OUT:-/tmp}
    cp "$W/new-boot.img" "$OUT/nf_magisk_new-boot.img"
    nf_say "已存 $OUT/nf_magisk_new-boot.img（未写盘）"
    exit 0
fi

nf_say "== 写回 $PART"
dd if="$W/new-boot.img" of="$DEV" bs=1M conv=fsync 2>/dev/null || nf_die "写入 $PART 失败"
sync
nf_say "完成：Magisk 已写入 $PART，重启进系统后打开 Magisk app 收尾"
