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
  2. recovery 分片必须用 **lz4 legacy**（magic 0x184C2102）重新编码，和官方
     recovery 分片逐字节同格式。bootloader 侧的硬证据：本机 lk.img 里只有
     unlz4 / "lz4 decompress failure" 字符串，zstd 出现 0 次——MTK LK 解不了
     zstd。之前按 “0000 + zstd” 编码，bootloader 解不开 recovery 分片，于是
     回落到普通启动（结果就是“刷完 vendor_boot 进不去 TWRP，手机停在系统”）。

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
    """统一编码为 lz4 legacy（magic 0x184C2102 + [块长][块]... + 4 字节 0），
    与官方 recovery 分片完全同格式；MTK LK 只会 unlz4。"""
    try:
        import lz4.block
    except ImportError:
        sys.exit('[!] 需要 python lz4 模块：pip install lz4（CI 已装）')
    out = bytearray(b'\x02\x21\x4c\x18')
    block = 4 << 20
    for i in range(0, len(cpio), block):
        chunk = cpio[i:i + block]
        c = lz4.block.compress(chunk, mode='high_compression', compression=12, store_size=False)
        if len(c) >= len(chunk):
            c = chunk  # 存不下就存原文
        out += struct.pack('<I', len(c)) + c
    out += b'\x00\x00\x00\x00'
    return bytes(out), 'lz4'


# ------------------------------------------------ 64 MiB 里塞不下时的瘦身清单
# 只删三类“recovery 里没有任何进程会碰”的东西，解密链路一个不动：
#   - isee / thh 的 8 MB TA（teei_daemon 的 -r/-t 列表里没有它，recovery 也不起 thh HAL）
#   - AOSP OTA 的 update_engine_sideload（TWRP 走 minadbd，init.rc 无引用）
#   - super 分区工具链 + 只被 lpdump 链接的 protobuf 全量库
# 注意 vendor/thh/ta 里 keymaster/gatekeeper 那几个 TA 必须留，FBE 解 /data 靠它们。
DROP_BLOAT = (
    'vendor/thh/ta/7778c03fc30c4dd0a319ea29643d4d4b.ta',
    'system/bin/update_engine_sideload',
    'system/lib64/libprotobuf-cpp-full.so',
    'system/lib64/liblpdump.so',
    'system/bin/lpdump',
    'system/bin/lpmake',
    'system/bin/lpunpack',
    'system/bin/lptools',
    'system/bin/lpflash',
    'system/bin/lpadd',
)


def drop_bloat(cpio):
    """按 DROP_BLOAT 过滤 newc cpio，返回新的字节串；不动其余条目的头部/对齐。"""
    drop = set(DROP_BLOAT)
    out = bytearray()
    dropped = []
    i = 0
    while cpio[i:i + 6] == b'070701':
        namesz = int(cpio[i + 94:i + 102], 16)
        filesz = int(cpio[i + 54:i + 62], 16)
        name = cpio[i + 110:i + 110 + namesz - 1].decode('utf-8', 'replace')
        hdr_end = (i + 110 + namesz + 3) // 4 * 4
        data_end = (hdr_end + filesz + 3) // 4 * 4
        if name not in drop:
            out += cpio[i:data_end]
        else:
            dropped.append(name)
        i = data_end
        if name == 'TRAILER!!!':
            break
    if dropped:
        print('[i] 瘦身：去掉 %d 个 recovery 用不到的文件（省下 64 MiB 空间）' % len(dropped))
        for n in dropped:
            print('    - %s' % n)
    return bytes(out), dropped


def cpio_names(cpio):
    """逐个吐出 newc cpio 里的条目名（注意不能用 bytes in cpio 判断，
    脚本/配置里也会出现 system/bin/recovery 这种字面串）。"""
    i = 0
    while cpio[i:i + 6] in (b'070701', b'070702'):
        namesz = int(cpio[i + 94:i + 102], 16)
        filesz = int(cpio[i + 54:i + 62], 16)
        name = cpio[i + 110:i + 110 + namesz - 1].decode('utf-8', 'replace')
        if name == 'TRAILER!!!':
            return
        yield name
        i = (i + 110 + namesz + 3)//4*4 + (filesz + 3)//4*4


def count_cpio(cpio):
    """数一下 newc cpio 里的条目，用来判断 recovery 根是不是"壳"。"""
    return sum(1 for _ in cpio_names(cpio))


def is_bootable_root(cpio):
    """recovery 根必须带真正的 recovery 可执行文件，否则内核起不来 recovery。
    MOVE 模式下的"壳"分片（run#17，764 个条目）就是缺这个。"""
    for n in cpio_names(cpio):
        if n.lstrip('./') in ('system/bin/recovery', 'sbin/recovery'):
            return True
    return False


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
    # +12..+28 是 board_id 字段，可用包在 recovery 条目里塞了名字 "recovery"，
    # 字节级对齐它（md5 才能和已验证包一致）。
    for i, (off, size, typ, name) in enumerate([(0, len(platform), 1, b''),
                                                (len(platform), len(recovery), 2, b'recovery')]):
        struct.pack_into('<III', table, i * entry_size, size, off, typ)
        table[i * entry_size + 12:i * entry_size + 12 + len(name)] = name
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
    # 编出来的 recovery 分片可能只是个"壳"：MOVE 模式下 AOSP 只把 recovery 的
    # 上下文文件装进 recovery/root，真正的 system/bin/recovery、lib/、linker64、
    # file_contexts 这些要等 twrp_ramdisk / recovery 模块做完才进得去。
    # run#17（2026-11-26）实测只有 764 个文件、缺 system/bin/recovery，刷进去
    # 进不了 recovery。所以这里允许给一份已验证可启动的分片做兜底。
    ap.add_argument('--fallback-cpio', dest='fallback_cpio', default=None)
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

    # 编出来的分片若只是个"壳"（缺 system/bin/recovery），就换成兜底分片。
    print('[i] 待用 recovery 分片：%s B / %d 个 cpio 条目 / system/bin/recovery=%s'
          % (format(len(rec), ','), count_cpio(rec), is_bootable_root(rec)))
    if not is_bootable_root(rec):
        if not a.fallback_cpio or not os.path.exists(a.fallback_cpio):
            sys.exit('[!] recovery 分片缺 system/bin/recovery，也没有 --fallback-cpio 可用，'
                     '这个包刷进去进不了 recovery')
        fb_raw = open(a.fallback_cpio, 'rb').read()
        fb, fb_codec = decode_ramdisk(fb_raw)
        if not is_bootable_root(fb):
            sys.exit('[!] 兜底分片也不完整: %s' % a.fallback_cpio)
        print('[!] 编出来的分片不完整，改用已验证可启动的那份：%s（%s B / %s / %d 条目）'
              % (a.fallback_cpio, format(len(fb_raw), ','), fb_codec, count_cpio(fb)))
        rec, codec = fb, fb_codec

    plat = open(a.platform, 'rb').read()
    rec, _dropped = drop_bloat(rec)
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
        sys.exit('[!] 超出分区容量 %s B：再压也塞不进 64 MiB，先砍 recovery 根'
                 % format(total - a.size, ','))
    if rec_z[:4] != b'\x02\x21\x4c\x18':
        sys.exit('[!] recovery 分片不是 lz4 legacy，bootloader 解不开')


if __name__ == '__main__':
    main()
