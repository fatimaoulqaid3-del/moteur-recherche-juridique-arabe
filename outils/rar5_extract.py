#!/usr/bin/env python3
"""Mini-extracteur RAR5 (non chiffré, non solide) avec vérification CRC32.
Usage : python3 rar5_extract.py archive.rar dossier_sortie
"""
import os
import sys
import zlib


def vint(b, p):
    r = s = 0
    while True:
        x = b[p]
        p += 1
        r |= (x & 0x7F) << s
        s += 7
        if not x & 0x80:
            return r, p


class Bits:
    def __init__(self, buf):
        self.buf = buf + b"\0" * 16
        self.pos = 0  # position en bits

    def peek(self, n):
        byte = self.pos >> 3
        v = int.from_bytes(self.buf[byte:byte + 8], "big")
        return (v >> (64 - (self.pos & 7) - n)) & ((1 << n) - 1)

    def read(self, n):
        v = self.peek(n)
        self.pos += n
        return v


class Huff:
    """Table de décodage canonique (MSB d'abord), préfixe de 15 bits."""
    def __init__(self, lengths):
        self.table = [None] * 32768
        code = 0
        for L in range(1, 16):
            for sym, l in enumerate(lengths):
                if l == L:
                    lo = code << (15 - L)
                    hi = lo + (1 << (15 - L))
                    ent = (sym, L)
                    for i in range(lo, hi):
                        self.table[i] = ent
                    code += 1
            code <<= 1

    def decode(self, br):
        ent = self.table[br.peek(15)]
        if ent is None:
            raise ValueError("code Huffman invalide")
        br.pos += ent[1]
        return ent[0]


NC, DC, LDC, RC, BC = 306, 64, 16, 44, 20


def read_tables(br):
    bl = []
    i = 0
    while i < BC:
        n = br.read(4)
        if n == 15:
            z = br.read(4)
            if z == 0:
                bl.append(15)
                i += 1
            else:
                z += 2
                for _ in range(z):
                    if i < BC:
                        bl.append(0)
                        i += 1
        else:
            bl.append(n)
            i += 1
    bc = Huff(bl)
    total = NC + DC + LDC + RC
    t = []
    while len(t) < total:
        s = bc.decode(br)
        if s < 16:
            t.append(s)
        elif s < 18:
            n = (br.read(3) + 3) if s == 16 else (br.read(7) + 11)
            t.extend([t[-1]] * n)
        else:
            n = (br.read(3) + 3) if s == 18 else (br.read(7) + 11)
            t.extend([0] * n)
    t = t[:total]
    return (Huff(t[:NC]), Huff(t[NC:NC + DC]),
            Huff(t[NC + DC:NC + DC + LDC]), Huff(t[NC + DC + LDC:]))


def slot_to_len(br, slot):
    if slot < 8:
        return 2 + slot
    lb = slot // 4 - 1
    ln = 2 + ((4 | (slot & 3)) << lb)
    return ln + br.read(lb)


def unpack(packed, usize):
    br = Bits(packed)
    out = bytearray()
    old = [0, 0, 0, 0]
    last_len = 0
    tables = None
    block_end_bits = -1
    last_block = False
    while len(out) < usize:
        if br.pos >= block_end_bits:
            if last_block and tables is not None and block_end_bits >= 0:
                break
            br.pos = (br.pos + 7) & ~7
            flags = br.read(8)
            chk = br.read(8)
            nbytes = ((flags >> 3) & 3) + 1
            size = 0
            sb = []
            for i in range(nbytes):
                v = br.read(8)
                sb.append(v)
                size |= v << (8 * i)
            c = 0x5A ^ flags
            for v in sb:
                c ^= v
            if c != chk:
                raise ValueError("checksum d'en-tête de bloc invalide")
            bitsize = (flags & 7) + 1
            start = br.pos
            block_end_bits = start + (size - 1) * 8 + bitsize
            last_block = bool(flags & 0x40)
            if flags & 0x80:
                tables = read_tables(br)
        LD, DD, LDD, RD = tables
        s = LD.decode(br)
        if s < 256:
            out.append(s)
        elif s >= 262:
            ln = slot_to_len(br, s - 262)
            ds = DD.decode(br)
            if ds < 4:
                dist = 1 + ds
            else:
                db = ds // 2 - 1
                dist = 1 + ((2 | (ds & 1)) << db)
                if db >= 4:
                    if db > 4:
                        dist += br.read(db - 4) << 4
                    dist += LDD.decode(br)
                else:
                    dist += br.read(db)
            if dist > 0x100:
                ln += 1
            if dist > 0x2000:
                ln += 1
            if dist > 0x40000:
                ln += 1
            old = [dist] + old[:3]
            last_len = ln
            copy(out, ln, dist)
        elif s == 256:
            raise NotImplementedError("filtre RAR rencontré")
        elif s == 257:
            if last_len:
                copy(out, last_len, old[0])
        else:
            k = s - 258
            dist = old[k]
            old = [dist] + old[:k] + old[k + 1:]
            ln = slot_to_len(br, RD.decode(br))
            last_len = ln
            copy(out, ln, dist)
    return bytes(out[:usize])


def copy(out, ln, dist):
    if dist <= 0 or dist > len(out):
        raise ValueError("distance invalide")
    st = len(out) - dist
    if dist >= ln:
        out += out[st:st + ln]
    else:
        for i in range(ln):
            out.append(out[st + i])


def extract(path, dest):
    data = open(path, "rb").read()
    assert data[:8] == b"Rar!\x1a\x07\x01\x00", "pas du RAR5"
    pos = 8
    ok = bad = 0
    while pos < len(data):
        p = pos + 4
        size, p = vint(data, p)
        hs = p
        typ, p = vint(data, p)
        flags, p = vint(data, p)
        if flags & 1:
            _, p = vint(data, p)
        dsize = 0
        if flags & 2:
            dsize, p = vint(data, p)
        if typ == 2:
            fl, p = vint(data, p)
            usize, p = vint(data, p)
            _, p = vint(data, p)
            if fl & 2:
                p += 4
            crc = None
            if fl & 4:
                crc = int.from_bytes(data[p:p + 4], "little")
                p += 4
            comp, p = vint(data, p)
            _, p = vint(data, p)
            nl, p = vint(data, p)
            name = data[p:p + nl].decode("utf8")
            dstart = hs + size
            packed = data[dstart:dstart + dsize]
            target = os.path.join(dest, name)
            if fl & 1:
                os.makedirs(target, exist_ok=True)
            else:
                method = (comp >> 7) & 7
                raw = packed if method == 0 else unpack(packed, usize)
                good = crc is None or (zlib.crc32(raw) & 0xFFFFFFFF) == crc
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as f:
                    f.write(raw)
                if good:
                    ok += 1
                else:
                    bad += 1
                    print("CRC KO :", name)
        pos = hs + size + dsize
    print(f"Extraction terminée : {ok} fichiers OK, {bad} CRC invalides")


if __name__ == "__main__":
    extract(sys.argv[1], sys.argv[2])
