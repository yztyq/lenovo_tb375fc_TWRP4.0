#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 OrangeFox 编出的 vendor_boot.img 修正成可刷、可进 recovery 的 64 MB 镜像。

为什么需要这一步（2026-11-26 TB375FC 实测结论）：
  1. 本机 vendor_boot 是 A/B 的 v4 镜像，内含两个 ramdisk 分片：
       platform 分片 —— first_stage_ramdisk + 222 个官方 6.1.138 内核模块
       recovery 分片 —— TWRP/OrangeFox 根文件系统
     这个 platform 分片只能来自官方 vendor_boot，本树自己编不出来（自编出来的是
     空目录 => 4 字节分片，刷进去必然进不了 recovery）。所以这里把官方原片
     (prebuilt/platform_ramdisk.lz4) 拼回去。
  2. recovery 分片统一重新编码成 “0000 + zstd”，与已验证能进 recovery 的官方
     platform 包保持一致（bootloader 对这个格式最稳）。

用法：
  # A. 从编好的 vendor_boot.img 里取 recovery 分片（mkbootimg 支持分片时走这条）
  python3 scripts/splice_platform.py \
      --input  $OUT/vendor_boot.img \
      --platform prebuilt/platform_ramdisk.lz4 \
      --output vendor_boot_TWRP.img \
      --size 67108864

  # B. 直接从零件拼（fox_16.0 的 system/tools/mkbootimg 是旧版，不认
  #    --vendor_ramdisk_fragment，最后一步必然 ValueError；但 recovery.cpio.lz4
  #    和 dtb.img 都已经编出来了，用零件拼更稳）
  python3 scripts/splice_platform.py \
      --recovery-cpio $OUT/obj/PACKAGING/vendor_ramdisk_fragments_intermediates/recovery.cpio.lz4 \
      --dtb           $OUT/dtb.img \
      --header        prebuilt/vendor_boot_header.bin \
      --platform prebuilt/platform_ramdisk.lz4 \
      --output vendor_boot_TWRP.img \
      --size 67108864

不带参数时按脚本所在设备树的默认位置工作，方便在 CI 里直接调用。
"""

import argparse
import os
import struct
import sys

PAGE = 4096
HDR_SIZE = 2128
DEFAULT_SIZE = 67108864  # BOARD_VENDOR_BOOTIMAGE_PARTITION_SIZE


# ---------------------------------------------------------------- 解/压
def _lz4_block_decode(src):
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        t = src[i]
        i += 1
        lit = t >> 4
        if lit == 15:
            while True:
                b = src[i]
                i += 1
                lit += b
                if b != 255:
                    break
        out += src[i:i + lit]
        i += lit
        if i >= n:
            break
        off = src[i] | (src[i + 1] << 8)
        i += 2
        ml = t & 0xF
        if ml == 15:
            while True:
                b = src[i]
                i += 1
                ml += b
                if b != 255:
                    break
        ml += 4
        st = len(out) - off
        for _ in range(ml):
            out.append(out[st])
            st += 1
    return bytes(out)


def _lz4_legacy_decode(buf):
    out = bytearray()
    i = 4
    while i + 4 <= len(buf):
        bs = struct.unpack_from('<I', buf, i)[0]
        i += 4
        if bs == 0:
            break
        if bs & 0x80000000:
            r = bs & 0x7FFFFFFF
            out += buf[i:i + r]
            i += r
        else:
            out += _lz4_block_decode(buf[i:i + bs])
            i += bs
    return bytes(out)


def decode_ramdisk(buf):
    """把任意编码的 ramdisk 分片解成裸 cpio。"""
    if buf[:4] == b'\x00\x00\x00\x00':
        import zstandard
        return zstandard.ZstdDecompressor().decompress(buf[4:]), '0000+zstd'
    if buf[:4] == b'\x02\x21\x4c\x18':
        return _lz4_legacy_decode(buf), 'lz4'
    if buf[:2] == b'\x1f\x8b' or buf[:3] == b'\x1f\x8b\x08':
        import gzip
        return gzip.decompress(buf), 'gzip'
    if buf[:4] == b'\x28\xb5\x2f\xfd':
        import zstandard
        return zstandard.ZstdDecompressor().decompress(buf), 'zstd'
    return buf, 'raw'


def encode_ramdisk(cpio):
    """统一编码为 0000+zstd（与可用包一致）。"""
    import zstandard
    return b'\x00\x00\x00\x00' + zstandard.ZstdCompressor(level=19).compress(cpio), '0000+zstd'


# ---------------------------------------------------------------- 解析 vendor_boot v4
def parse_vendor_boot(path):
    """vendor_boot v4 布局（MTK/lineage mkbootimg 实测）：
         0    magic "TBOOTNRV"（反向）
         24   vendor_ramdisk_size
         2076 tags_addr / 2100 dtb_size / 2104 dtb_addr / 2096 header_size(=2128)
         2112 vendor_ramdisk_table_size
         2116 vendor_ramdisk_table_entry_num
         2120 vendor_ramdisk_table_entry_size(=108)
       分片表紧跟在 dtb 后一个 page 起始处，没有 12 字节表头，条目直接排列。
       条目结构：+0 size / +4 offset / +8 type（1=platform, 2=recovery, 3=dlkm）
                 +12..+108 board_id[16]（实际未使用，MTK 条目 108 B）
    """
    b = open(path, 'rb').read()
    vrs = struct.unpack_from('<I', b, 24)[0]
    dtb_size = struct.unpack_from('<I', b, 2100)[0]
    toff = PAGE + ((vrs + PAGE - 1) // PAGE) * PAGE + ((dtb_size + PAGE - 1) // PAGE) * PAGE
    num = struct.unpack_from('<I', b, 2116)[0]
    entry_size = struct.unpack_from('<I', b, 2120)[0] or 108
    frags = []
    for i in range(num):
        base = toff + i * entry_size
        size, off, typ = struct.unpack_from('<III', b, base)
        frags.append({'name': 'frag%d' % i, 'size': size, 'offset': off, 'type': typ,
                      'data': b[PAGE + off: PAGE + off + size]})
    dtb = b[PAGE + ((vrs + PAGE - 1) // PAGE) * PAGE:
            PAGE + ((vrs + PAGE - 1) // PAGE) * PAGE + dtb_size]
    return {'data': b, 'header': b[:HDR_SIZE], 'vrs': vrs, 'dtb_size': dtb_size,
            'dtb': dtb, 'frags': frags, 'table_entry_size': entry_size}


def build_image(header, platform, recovery, dtb, out_size, out_path):
    vrs = len(platform) + len(recovery)
    entry_size = 108
    hdr = bytearray(header)
    struct.pack_into('<I', hdr, 24, vrs)                        # vendor_ramdisk_size
    struct.pack_into('<I', hdr, 2100, len(dtb))                 # dtb_size
    struct.pack_into('<I', hdr, 2112, 2 * entry_size)           # table_size
    struct.pack_into('<I', hdr, 2116, 2)                        # entry_num
    struct.pack_into('<I', hdr, 2120, entry_size)               # entry_size

    blob = bytearray()
    blob += hdr
    # 头部只占 header_size(2128) 字节，但各分片的 offset 是相对 page(4096) 起点算的，
    # 所以必须把 header 补到整页，否则所有偏移都会前移 1968 字节。
    blob += b'\x00' * (PAGE - len(hdr))
    blob += platform
    blob += recovery
    pad = ((vrs + PAGE - 1) // PAGE) * PAGE - vrs
    blob += b'\x00' * pad
    blob += dtb
    dtb_pad = ((len(dtb) + PAGE - 1) // PAGE) * PAGE - len(dtb)
    blob += b'\x00' * dtb_pad

    # 分片表：与可用包一致，条目从 page 起始处直接排列
    table = bytearray(PAGE)
    # type 1 = platform, type 2 = recovery（可用包里就是这么写的，写错 bootloader 不认）
    for i, (off, size, typ) in enumerate([(0, len(platform), 1), (len(platform), len(recovery), 2)]):
        struct.pack_into('<III', table, i * entry_size, size, off, typ)
    blob += table

    if out_size and len(blob) < out_size:
        blob += b'\x00' * (out_size - len(blob))

    with open(out_path, 'wb') as f:
        f.write(blob)
    return vrs, len(blob)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    dev = os.path.dirname(here)
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=False,
                    default=os.path.join(dev, '..', '..', '..', 'out', 'target', 'product',
                                         'tb375fc', 'vendor_boot.img'))
    ap.add_argument('--platform', default=os.path.join(dev, 'prebuilt', 'platform_ramdisk.lz4'))
    ap.add_argument('--output', default='vendor_boot_TWRP_64MB.img')
    ap.add_argument('--size', type=int, default=DEFAULT_SIZE)
    # 零件模式：直接给 recovery 分片 cpio、dtb.img 和 2128 字节 vendor_boot 头模板，
    # 完全绕开编不出来的 vendor_boot.img（fox_16.0 的旧 mkbootimg 就是这样）。
    ap.add_argument('--recovery-cpio', dest='recovery_cpio', default=None)
    ap.add_argument('--dtb', dest='dtb', default=None)
    ap.add_argument('--header', dest='header', default=None)
    a = ap.parse_args()

    if not os.path.exists(a.platform):
        sys.exit('[!] 缺官方 platform 分片: %s' % a.platform)

    if a.recovery_cpio:
        for need, val in (('recovery cpio', a.recovery_cpio), ('dtb', a.dtb), ('header', a.header)):
            if not val or not os.path.exists(val):
                sys.exit('[!] 零件模式缺 %s: %s' % (need, val))
        hdr = open(a.header, 'rb').read()[:HDR_SIZE]
        if hdr[:8] != b'VNDRBOOT':
            sys.exit('[!] header 模板不是 VNDRBOOT: %s' % a.header)
        dtb = open(a.dtb, 'rb').read()
        raw = open(a.recovery_cpio, 'rb').read()
        rec, codec = decode_ramdisk(raw)
        print('[i] 零件模式：recovery.cpio=%s B (%s, 解压 %s B), dtb=%s B' %
              (format(len(raw), ','), codec, format(len(rec), ','), format(len(dtb), ',')))
        header = hdr
        dtb_size = len(dtb)
    else:
        if not os.path.exists(a.input):
            sys.exit('[!] 找不到编出来的 vendor_boot.img: %s' % a.input)
        vb = parse_vendor_boot(a.input)
        print('[i] 输入 %s : vrs=%s dtb=%s 分片=%d' %
              (a.input, format(vb['vrs'], ','), format(vb['dtb_size'], ','), len(vb['frags'])))
        for f in vb['frags']:
            print('    - frag size=%s type=%d' % (format(f['size'], ','), f['type']))
        header = vb['header']
        dtb = vb['dtb']
        dtb_size = vb['dtb_size']

        # 按分片表里的 type 选：1=platform，2=recovery。这个 type 位是 bootloader 的
        # 唯一依据，不能靠内容猜（platform 里也有 init.recovery.* / recovery.fstab）。
        rec = None
        for f in vb['frags']:
            if f['type'] != 2:
                continue
            cpio, codec = decode_ramdisk(f['data'])
            rec = cpio
            print('[i] recovery 分片：raw=%s (%s, 解压 %d 字节)' %
                  (format(f['size'], ','), codec, len(cpio)))
            break
        if rec is None:
            # 兜底：老工具可能不写 type，按内容再试一次
            for f in vb['frags']:
                cpio, codec = decode_ramdisk(f['data'])
                if any(x in cpio for x in (b'twres/', b'FFiles/', b'system/bin/twrp')):
                    rec = cpio
                    print('[i] 按内容认定 recovery 分片（type 位缺失）：%s' % codec)
                    break
    if rec is None:
        sys.exit('[!] 输入里没找到 recovery 分片（是不是 TARGET_NO_RECOVERY 还开着？）')
    if not any(x in rec for x in (b'twres/', b'FFiles/', b'system/bin/twrp', b'tb373fu')):
        sys.exit('[!] recovery 分片里没有 twres/FFiles，说明 OF 资源没进 ramdisk，先检查 BoardConfig')

    plat = open(a.platform, 'rb').read()
    rec_z, codec = encode_ramdisk(rec)
    if dtb_size and len(dtb) != dtb_size:
        print('[!] dtb 实际 %s B，头和 BOARD_DTB_SIZE 都写的是 %s B' %
              (format(len(dtb), ','), format(dtb_size, ',')))
    vrs, total = build_image(header, plat, rec_z, dtb, a.size, a.output)
    print('[✓] 输出 %s' % a.output)
    print('    platform = %s B (官方原片)' % format(len(plat), ','))
    print('    recovery = %s B (%s, 裸 cpio %s B)' %
          (format(len(rec_z), ','), codec, format(len(rec), ',')))
    print('    vrs      = %s B' % format(vrs, ','))
    print('    文件大小 = %s B (分区 %s B)' % (format(total, ','), format(a.size, ',')))
    if total > a.size:
        print('[!] 超出分区容量 %s B，需要再瘦身' % format(total - a.size, ','))


if __name__ == '__main__':
    main()
