#!/usr/bin/env python3
"""MSVC RTTI vtable finder for Windows server.dll (PE32 and PE32+), no dependencies.

  pevt.py DLL vt CLASS              -> slot: function VA
  pevt.py DLL strref STRING         -> VAs of functions referencing STRING (via objdump)
"""
import struct, sys, re, subprocess

class PE:
    def __init__(s, path):
        s.path = path
        s.d = open(path, 'rb').read()
        pe = struct.unpack_from('<I', s.d, 0x3c)[0]
        s.nsec = struct.unpack_from('<H', s.d, pe + 6)[0]
        optsz = struct.unpack_from('<H', s.d, pe + 20)[0]
        opt = pe + 24
        s.magic = struct.unpack_from('<H', s.d, opt)[0]
        s.x64 = s.magic == 0x20b
        s.base = struct.unpack_from('<Q', s.d, opt + 24)[0] if s.x64 else struct.unpack_from('<I', s.d, opt + 28)[0]
        s.ptr = 8 if s.x64 else 4
        s.secs = []
        for i in range(s.nsec):
            o = opt + optsz + 40 * i
            name = s.d[o:o + 8].rstrip(b'\0').decode()
            vsz, va, rsz, raw = struct.unpack_from('<IIII', s.d, o + 8)
            s.secs.append((name, va, max(vsz, rsz), raw, rsz))

    def off(s, rva):
        for name, va, sz, raw, rsz in s.secs:
            if va <= rva < va + sz:
                return raw + rva - va if rva - va < rsz else None
        return None

    def rva_of(s, off):
        for name, va, sz, raw, rsz in s.secs:
            if raw <= off < raw + rsz:
                return va + off - raw
        return None

    def sec(s, name):
        for x in s.secs:
            if x[0] == name:
                return x

    def u32(s, rva):
        return struct.unpack_from('<I', s.d, s.off(rva))[0]

    def uptr(s, rva):
        return struct.unpack_from('<Q' if s.x64 else '<I', s.d, s.off(rva))[0]

    def vtable(s, cls):
        name = ('.?AV%s@@' % cls).encode()
        i = s.d.find(b'\0' + name + b'\0')
        if i < 0:
            i = s.d.find(name)
            assert i >= 0, 'type descriptor not found'
        else:
            i += 1
        td_rva = s.rva_of(i) - (16 if s.x64 else 8)
        _, rva, sz, raw, rsz = s.sec('.rdata')
        blob = s.d[raw:raw + rsz]
        cols = []
        if s.x64:
            pat = struct.pack('<I', td_rva)
            for m in re.finditer(re.escape(pat), blob):
                col = rva + m.start() - 12
                sig, offs, cd, td, chd, self_ = struct.unpack_from('<IIIIII', s.d, s.off(col))
                if sig == 1 and offs == 0 and self_ == col:
                    cols.append(col)
        else:
            pat = struct.pack('<I', s.base + td_rva)
            for m in re.finditer(re.escape(pat), blob):
                col = rva + m.start() - 12
                sig, offs, cd = struct.unpack_from('<III', s.d, s.off(col))
                if sig == 0 and offs == 0:
                    cols.append(col)
        assert cols, 'no complete object locator'
        col = cols[0]
        pat = struct.pack('<Q' if s.x64 else '<I', s.base + col)
        m = re.search(re.escape(pat), blob)
        assert m, 'vtable not found'
        vt = rva + m.start() + s.ptr
        out = []
        text = s.sec('.text')
        while True:
            f = s.uptr(vt + s.ptr * len(out))
            frva = f - s.base
            if not (text[1] <= frva < text[1] + text[2]):
                break
            out.append(f)
        return out

    def strva(s, string):
        pat = string.encode() + b'\0'
        i = s.d.find(pat)
        while i > 0 and (chr(s.d[i - 1]).isalnum() or s.d[i - 1] == ord('_')):
            i = s.d.find(pat, i + 1)
        return s.base + s.rva_of(i)

if __name__ == '__main__':
    pe = PE(sys.argv[1])
    if sys.argv[2] == 'vt':
        for i, f in enumerate(pe.vtable(sys.argv[3])):
            print(i, hex(f))
