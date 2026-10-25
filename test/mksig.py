#!/usr/bin/env python3
"""Make a unique SourceMod byte signature for a function in a Windows PE (x86 / x64).
usage: mksig.py DLL FUNC_VA      -> prints "\\x55\\x8B..." with \\x2A wildcards (relocations, rel32 calls/jumps, RIP disps)
"""
import sys, struct, re, subprocess
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from pevt import PE

def relocs(pe):
    """RVAs patched by base relocations (absolute addresses in the code)."""
    sec = pe.sec('.reloc')
    out = set()
    if not sec: return out
    d = pe.d[sec[3]:sec[3] + sec[4]]
    i = 0
    while i + 8 <= len(d):
        page, size = struct.unpack_from('<II', d, i)
        if size < 8: break
        for k in range((size - 8) // 2):
            e = struct.unpack_from('<H', d, i + 8 + 2 * k)[0]
            typ, off = e >> 12, e & 0xfff
            if typ in (3, 10):
                n = 4 if typ == 3 else 8
                for b in range(n): out.add(page + off + b)
        i += size
    return out

def insns(pe, va, n=0x300):
    tool = 'x86_64-w64-mingw32-objdump' if pe.x64 else 'i686-w64-mingw32-objdump'
    out = subprocess.run([tool, '-d', '--start-address=%#x' % va, '--stop-address=%#x' % (va + n), pe.path], capture_output=True, text=True).stdout
    res = []
    for l in out.splitlines():
        m = re.match(r'\s*([0-9a-f]+):\t((?:[0-9a-f]{2} )+)\s*\t?(.*)', l)
        if m:
            res.append((int(m.group(1), 16), bytes.fromhex(m.group(2).replace(' ', '')), m.group(3)))
    return res

def main():
    pe = PE(sys.argv[1]); va = int(sys.argv[2], 16)
    rel = relocs(pe)
    sig = []  # (byte or None)
    for addr, b, text in insns(pe, va):
        mask = [False] * len(b)
        for k in range(len(b)):
            if (addr - pe.base + k) in rel: mask[k] = True
        if b[0] in (0xE8, 0xE9) and len(b) == 5: mask[1:5] = [True] * 4
        if b[0] == 0x0F and len(b) == 6 and 0x80 <= b[1] <= 0x8F: mask[2:6] = [True] * 4
        if pe.x64 and '(%rip)' in text:
            # disp32 sits right before any immediate; immediates only for a few forms, assume none unless '$' in text
            imm = 0
            m = re.search(r'\$0x([0-9a-f]+),', text)
            if m: imm = 1 if int(m.group(1), 16) < 0x100 else 4
            end = len(b) - imm
            mask[end - 4:end] = [True] * 4
        sig += [None if mask[k] else b[k] for k in range(len(b))]
        # uniqueness check once we have >= 12 bytes
        if len(sig) >= 12:
            pat = b''.join(b'.' if x is None else re.escape(bytes([x])) for x in sig)
            text_sec = pe.sec('.text')
            blob = pe.d[text_sec[3]:text_sec[3] + text_sec[4]]
            hits = [m.start() for m in re.finditer(pat, blob, re.S)]
            if len(hits) == 1:
                print(''.join('\\x2A' if x is None else '\\x%02X' % x for x in sig))
                return
    print('not unique within window', file=sys.stderr); sys.exit(1)

if __name__ == '__main__':
    main()
