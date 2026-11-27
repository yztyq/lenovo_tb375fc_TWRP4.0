#!/system/bin/sh
# nf_magisk_off.sh —— 关闭所有 Magisk 模组（给每个模组目录放 disable 文件）
# 用法: nf_magisk_off.sh [--yes]
#
# 2026-11-19 修复：本机没有 Magisk 模组时不再当成错误退出，
# 直接给出「0 个模组」的正常结论，避免按钮报失败。
NF=$(cd "$(dirname "$0")" && pwd); . "$NF/nf_lib.sh"

MODDIR=/data/adb/modules
if [ ! -d "$MODDIR" ]; then
    nf_say "本机没有 Magisk 模组目录（$MODDIR 不存在）"
    nf_say "说明当前系统未安装 Magisk 或 /data 未解密，无需关闭，直接视为完成"
    exit 0
fi

n=0
for d in "$MODDIR"/*; do
    [ -d "$d" ] || continue
    name=$(basename "$d")
    case "$name" in
        modules_update|*.tmp) continue ;;
    esac
    if [ -f "$d/disable" ]; then
        nf_say "已禁用（跳过）: $name"
        continue
    fi
    touch "$d/disable" || nf_say "[警告] 无法写入 $name/disable"
    nf_say "已关闭: $name"
    n=$((n + 1))
done

sync
if [ "$n" -eq 0 ]; then
    nf_say "没有需要关闭的模组（共 0 个）"
else
    nf_say "共关闭 $n 个模组，重启到系统后生效"
    nf_say "重新启用某个模组：删掉 /data/adb/modules/<模组名>/disable 即可"
fi
