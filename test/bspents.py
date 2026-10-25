#!/usr/bin/env python3
"""Tiny CS:S (v20) BSP entity-lump tool.
  bspents.py list MAP.bsp [classname-regex]     -> brush triggers with model bounds
  bspents.py dump MAP.bsp > ents.txt             -> raw entity lump text
  bspents.py write MAP.bsp ents.txt OUT.bsp      -> new BSP with the entity lump replaced (appended at EOF)
"""
import struct, sys, re, lzma

def read(path):
    d = bytearray(open(path, 'rb').read())
    assert d[:4] == b'VBSP', 'not a VBSP'
    return d

def lump(d, i):
    off, ln, ver, cc = struct.unpack_from('<iii4s', d, 8 + 16 * i)
    return off, ln

def lump_bytes(d, i):
    off, ln = lump(d, i)
    b = bytes(d[off:off + ln])
    if b[:4] == b'LZMA':  # Valve LZMA lump: 'LZMA', actualSize, lzmaSize, props[5], data
        actual, lsize = struct.unpack_from('<ii', b, 4)
        alone = b[12:17] + struct.pack('<q', actual) + b[17:17 + lsize]
        b = lzma.decompress(alone, format=lzma.FORMAT_ALONE)
    return b

def ents_text(d):
    return lump_bytes(d, 0).rstrip(b'\0').decode('latin1')

def parse_ents(t):
    out = []
    for blk in re.findall(r'\{(.*?)\}', t, re.S):
        kv = re.findall(r'"([^"]*)"\s+"([^"]*)"', blk)
        out.append(kv)
    return out

def models(d):
    b = lump_bytes(d, 14)  # LUMP_MODELS: mins[3] maxs[3] origin[3] headnode firstface numfaces
    return [struct.unpack_from('<9f3i', b, 48 * i) for i in range(len(b) // 48)]

if __name__ == '__main__':
    cmd, path = sys.argv[1], sys.argv[2]
    d = read(path)
    if cmd == 'list':
        rx = re.compile(sys.argv[3] if len(sys.argv) > 3 else r'^trigger_')
        ms = models(d)
        for i, kv in enumerate(parse_ents(ents_text(d))):
            k = {a.lower(): b for a, b in kv}
            cn = k.get('classname', '')
            if not rx.search(cn): continue
            m = k.get('model', '')
            b = ''
            if m.startswith('*'):
                mm = ms[int(m[1:])]
                org = [float(x) for x in k.get('origin', '0 0 0').split()]
                b = 'mins %.0f %.0f %.0f maxs %.0f %.0f %.0f' % tuple(mm[j] + org[j % 3] for j in range(6))
            outs = [a for a, _ in kv if a.lower().startswith('on')]
            print(i, cn, m, k.get('targetname', ''), 'sf=' + k.get('spawnflags', ''), b, 'outs=' + ','.join(outs))
    elif cmd == 'dump':
        sys.stdout.write(ents_text(d))
    elif cmd == 'write':
        new = open(sys.argv[3], 'rb').read().rstrip(b'\0') + b'\0'
        out = sys.argv[4]
        while len(d) % 4: d += b'\0'
        off = len(d)
        d += new
        struct.pack_into('<iii4s', d, 8, off, len(new), 0, b'\0\0\0\0')  # uncompressed
        open(out, 'wb').write(d)
        print('wrote', out, 'entity lump', len(new), 'bytes at', off)
