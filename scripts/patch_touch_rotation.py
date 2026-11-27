#!/usr/bin/env python3
"""Give twrpminui a sensible default touch rotation on the TB375FC panel.

The panel (NVTCapacitiveTouchScreen) reports its coordinates in native
portrait (ABS_X 0..18400 / ABS_Y 0..29440) while the GUI runs landscape at
2944x1840, so input only lands correctly after a 270 degree remap.

twrp_input.cpp already honours the runtime property
``ro.twrp.touch.rotation``; it simply falls back to 0 when the property is
absent.  The hand built ramdisks carry that property in ``prop.default``, but
a full AOSP build regenerates the recovery root and can drop it, so make 270
the compiled-in default as well (the property still wins when present).

Idempotent: running it twice is a no-op.
"""

import sys

OLD = """    // An unset property preserves the historical input mapping for other SKUs.
    touch_rotation = 0;
"""

NEW = """    // TB375FC: panel is native portrait, GUI is landscape -> default 270.
    // The runtime property (ro.twrp.touch.rotation) still overrides this.
    touch_rotation = 270;
"""

MARK = "TB375FC: panel is native portrait"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_touch_rotation.py <path to twrpminui/twrp_input.cpp>")
        return 2
    path = sys.argv[1]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print("cannot read %s: %s" % (path, exc))
        return 3

    if MARK in text:
        print("already patched: %s" % path)
        return 0
    if OLD not in text:
        print("anchor not found in %s - upstream changed?" % path)
        return 4

    text = text.replace(OLD, NEW, 1)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("patched touch rotation default (0 -> 270): %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
