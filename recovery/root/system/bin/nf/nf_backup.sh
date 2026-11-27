#!/system/bin/sh
# nf_backup.sh —— 按分区 dd 备份到 .img（自动补当前槽后缀），备份完做 MD5 校对
# 用法: nf_backup.sh <分区名> [分区名...]
#       NF_DEST=/sdcard/TWRP/BFxxx nf_backup.sh boot dtbo
NF=$(cd "$(dirname "$0")" && pwd); . "$NF/nf_lib.sh"

if [ $# -lt 1 ]; then
    nf_say "用法: nf_backup.sh <分区名> [分区名...]"
    nf_say "可用分区:"
    nf_list_parts | while read -r n; do
        printf "  %-22s %s\n" "$n" "$(nf_human "$(nf_size "/dev/block/by-name/$n")")"
    done
    exit 1
fi

DEST=${NF_DEST:-/sdcard/TWRP/BF$(date +%Y%m%d%H%M%S)}
mkdir -p "$DEST" || nf_die "无法创建目录 $DEST"

# 第一遍：解析真实节点 + 统计空间
list=""
total=0
for p in "$@"; do
    dev=$(nf_dev "$p")
    if [ -z "$dev" ]; then
        nf_say "[跳过] 分区不存在: $p"
        continue
    fi
    list="$list $(basename "$dev")"
    total=$(nf_add "$total" "$(nf_size "$dev")")
done
[ -n "$list" ] || nf_die "没有一个可备份的分区"

free=$(nf_free "$DEST")
nf_say "目标目录 : $DEST"
nf_say "需要空间 : $(nf_human "$total")    可用: $(nf_human "$free")"
nf_ge "$free" "$total" || nf_die "存储空间不足，请先清理 $DEST 所在分区"

# 第二遍：dd 写出 + MD5 校对（回读设备与文件对比）
: >"$DEST/md5.txt"
ok=0
bad=0
for name in $list; do
    dev="/dev/block/by-name/$name"
    nf_say "== 备份 $name"
    dd if="$dev" of="$DEST/$name.img" bs=1M 2>/dev/null || nf_die "dd 读取失败: $name"
    sync
    size=$(stat -c %s "$DEST/$name.img" 2>/dev/null)
    md5=$(nf_md5 "$DEST/$name.img")

    # 校对：把分区重新读一遍，和文件比 MD5（分区 ≤ 256MB 才做，避免双倍 IO 太慢）
    devmd5=""
    if nf_ge 268435456 "$size"; then
        blocks=$((size / 1048576))
        dd if="$dev" of=/tmp/nf_chk.img bs=1M count=$blocks 2>/dev/null
        devmd5=$(nf_md5 /tmp/nf_chk.img)
        rm -f /tmp/nf_chk.img
    fi
    if [ -n "$devmd5" ]; then
        if [ "$devmd5" = "$md5" ]; then
            nf_say "   $(nf_human "$size")  md5=$md5  [校对一致]"
        else
            nf_say "   $(nf_human "$size")  md5=$md5  设备=$devmd5  [校对不一致]"
            bad=$((bad + 1))
        fi
    else
        nf_say "   $(nf_human "$size")  md5=$md5  （分区较大，跳过回读校对）"
    fi
    echo "$name $size $md5" >>"$DEST/md5.txt"
    ok=$((ok + 1))
done

nf_say "备份完成: $DEST"
nf_say "共 $ok 个分区，MD5 不一致 $bad 个；校验清单见 $DEST/md5.txt"
[ "$bad" -eq 0 ] || exit 1
