#!/usr/bin/env python3
"""让 TWRP 4.0 的 DRM 后端在 MediaTek 显示驱动上走 legacy KMS。

实机日志（TB375FC / mt6897，驱动 $_driver = mediatek-drm）:
    TWRP DRM: display 0 found 0/2 primary planes for CRTC index 0
    Failed to init display
    gui2: minui display initialization failed
    E:GUI2 exited with error 1.

原因:
  TWRP 4.0 的 CLO/原子提交路径要求“primary plane 个数 == connector 的
  mode_properties 里的 layer mixer 数(2)”，MTK 的 dispsys 驱动不满足这个条件，
  于是 MinuiBackendDrm::Initdisplay() 直接返回 -1；而 fbdev 后端在这台机器上
  也没有后备（recovery 里 /dev/graphics 与 /proc/fb 都不存在），两个后端都失败，
  gr_init() 返回 -1，GUI2 退出，recovery 反复重启后 LK 回落 bootloader。

解法:
  graphics_drm.cpp 里只有 virtio_gpu 被划入 legacy KMS 分支
  （drmModeSetCrtc + dumb buffer，不依赖 plane/topology）。把 mediatek-drm
  也纳入该分支即可走通，顺带打印驱动名与开关状态，方便下一轮日志核对。
"""

import pathlib
import sys

OLD = 'legacy_modeset = version->name && !strcmp(version->name, "virtio_gpu");'

NEW = (
    'legacy_modeset = version->name &&\n'
    '            (!strcmp(version->name, "virtio_gpu") ||\n'
    '             strstr(version->name, "mediatek") || strstr(version->name, "mtk"));\n'
    '        fprintf(stderr, "TWRP DRM: driver=%s legacy_modeset=%d\\n", version->name,\n'
    '                legacy_modeset ? 1 : 0);'
)

MARKER = 'strstr(version->name, "mediatek")'


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: patch_drm_legacy.py <path to graphics_drm.cpp>")
        return 2
    path = pathlib.Path(sys.argv[1])
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        print("already patched:", path)
        return 0
    if OLD not in text:
        print("ERROR: anchor not found, TWRP source changed:", path)
        return 3
    path.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print("patched:", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
