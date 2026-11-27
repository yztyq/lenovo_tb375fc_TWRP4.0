#!/system/bin/sh
# Magisk 模组开关（v12）：在 TWRP 里关闭/启用 /data/adb/modules 下的模组
# 用法：
#   twrp_magisk_modules.sh list           列出模组与状态
#   twrp_magisk_modules.sh off <模块ID>     关闭（创建 disable 文件）
#   twrp_magisk_modules.sh on  <模块ID>     启用（删除 disable 文件）
#   twrp_magisk_modules.sh off-all          全部关闭
#   twrp_magisk_modules.sh on-all           全部启用
set -u
MODS=/data/adb/modules

if ! mount | grep -q " /data "; then
    echo "[twrp] 错误: /data 未挂载。请先在 TWRP 里解密并挂载 /data 再执行。"
    exit 2
fi
if [ ! -d "$MODS" ]; then
    echo "[twrp] 没有找到 $MODS（可能还没装 Magisk）"
    exit 2
fi

case "${1:-}" in
    list)
        n=0
        for d in "$MODS"/*; do
            [ -d "$d" ] || continue
            id=$(basename "$d")
            if [ -f "$d/remove" ]; then
                st="待卸载"
            elif [ -f "$d/disable" ]; then
                st="已关闭"
            else
                st="启用中"
            fi
            echo "$st  $id"
            n=$((n + 1))
        done
        echo "[twrp] 共 $n 个模组"
        ;;
    off|on)
        id="${2:-}"
        if [ -z "$id" ]; then
            echo "[twrp] 用法: $0 $1 <模块ID>"
            exit 2
        fi
        if [ ! -d "$MODS/$id" ]; then
            echo "[twrp] 没有这个模块: $id"
            exit 2
        fi
        if [ "$1" = off ]; then
            touch "$MODS/$id/disable" && echo "[twrp] 已关闭: $id"
        else
            rm -f "$MODS/$id/disable" && echo "[twrp] 已启用: $id"
        fi
        ;;
    off-all|on-all)
        n=0
        for d in "$MODS"/*; do
            [ -d "$d" ] || continue
            id=$(basename "$d")
            if [ "$1" = off-all ]; then
                touch "$MODS/$id/disable"
            else
                rm -f "$MODS/$id/disable"
            fi
            n=$((n + 1))
        done
        echo "[twrp] 已处理 $n 个模组（$1）"
        ;;
    *)
        echo "用法: $0 list | off <ID> | on <ID> | off-all | on-all"
        exit 2
        ;;
esac
exit 0
