"""Minimal 6502 assembler for monitor and test programs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


class AsmError(Exception):
    pass


@dataclass
class Line:
    label: str | None
    op: str | None
    arg: str | None
    lineno: int


@dataclass
class Image:
    origin: int
    data: bytes
    labels: dict[str, int] = field(default_factory=dict)


IMPLIED = {
    "BRK": 0x00, "PHP": 0x08, "CLC": 0x18, "PLP": 0x28, "SEC": 0x38,
    "RTI": 0x40, "PHA": 0x48, "CLI": 0x58, "RTS": 0x60, "PLA": 0x68,
    "SEI": 0x78, "DEY": 0x88, "TXA": 0x8A, "TYA": 0x98, "TXS": 0x9A,
    "TAY": 0xA8, "TAX": 0xAA, "CLV": 0xB8, "TSX": 0xBA, "INY": 0xC8,
    "DEX": 0xCA, "CLD": 0xD8, "INX": 0xE8, "NOP": 0xEA, "SED": 0xF8,
}

ACCUM = {"ASL": 0x0A, "LSR": 0x4A, "ROL": 0x2A, "ROR": 0x6A}

BRANCH = {
    "BPL": 0x10, "BMI": 0x30, "BVC": 0x50, "BVS": 0x70,
    "BCC": 0x90, "BCS": 0xB0, "BNE": 0xD0, "BEQ": 0xF0,
}

TABLE = {
    ("imm", "LDA"): 0xA9, ("zp", "LDA"): 0xA5, ("zpx", "LDA"): 0xB5,
    ("abs", "LDA"): 0xAD, ("absx", "LDA"): 0xBD, ("absy", "LDA"): 0xB9,
    ("indx", "LDA"): 0xA1, ("indy", "LDA"): 0xB1,
    ("imm", "LDX"): 0xA2, ("zp", "LDX"): 0xA6, ("zpy", "LDX"): 0xB6,
    ("abs", "LDX"): 0xAE, ("absy", "LDX"): 0xBE,
    ("imm", "LDY"): 0xA0, ("zp", "LDY"): 0xA4, ("zpx", "LDY"): 0xB4,
    ("abs", "LDY"): 0xAC, ("absx", "LDY"): 0xBC,
    ("zp", "STA"): 0x85, ("zpx", "STA"): 0x95, ("abs", "STA"): 0x8D,
    ("absx", "STA"): 0x9D, ("absy", "STA"): 0x99, ("indx", "STA"): 0x81,
    ("indy", "STA"): 0x91,
    ("zp", "STX"): 0x86, ("zpy", "STX"): 0x96, ("abs", "STX"): 0x8E,
    ("zp", "STY"): 0x84, ("zpx", "STY"): 0x94, ("abs", "STY"): 0x8C,
    ("imm", "ADC"): 0x69, ("zp", "ADC"): 0x65, ("zpx", "ADC"): 0x75,
    ("abs", "ADC"): 0x6D, ("absx", "ADC"): 0x7D, ("absy", "ADC"): 0x79,
    ("indx", "ADC"): 0x61, ("indy", "ADC"): 0x71,
    ("imm", "SBC"): 0xE9, ("zp", "SBC"): 0xE5, ("zpx", "SBC"): 0xF5,
    ("abs", "SBC"): 0xED, ("absx", "SBC"): 0xFD, ("absy", "SBC"): 0xF9,
    ("indx", "SBC"): 0xE1, ("indy", "SBC"): 0xF1,
    ("imm", "AND"): 0x29, ("zp", "AND"): 0x25, ("zpx", "AND"): 0x35,
    ("abs", "AND"): 0x2D, ("absx", "AND"): 0x3D, ("absy", "AND"): 0x39,
    ("indx", "AND"): 0x21, ("indy", "AND"): 0x31,
    ("imm", "ORA"): 0x09, ("zp", "ORA"): 0x05, ("zpx", "ORA"): 0x15,
    ("abs", "ORA"): 0x0D, ("absx", "ORA"): 0x1D, ("absy", "ORA"): 0x19,
    ("indx", "ORA"): 0x01, ("indy", "ORA"): 0x11,
    ("imm", "EOR"): 0x49, ("zp", "EOR"): 0x45, ("zpx", "EOR"): 0x55,
    ("abs", "EOR"): 0x4D, ("absx", "EOR"): 0x5D, ("absy", "EOR"): 0x59,
    ("indx", "EOR"): 0x41, ("indy", "EOR"): 0x51,
    ("imm", "CMP"): 0xC9, ("zp", "CMP"): 0xC5, ("zpx", "CMP"): 0xD5,
    ("abs", "CMP"): 0xCD, ("absx", "CMP"): 0xDD, ("absy", "CMP"): 0xD9,
    ("indx", "CMP"): 0xC1, ("indy", "CMP"): 0xD1,
    ("imm", "CPX"): 0xE0, ("zp", "CPX"): 0xE4, ("abs", "CPX"): 0xEC,
    ("imm", "CPY"): 0xC0, ("zp", "CPY"): 0xC4, ("abs", "CPY"): 0xCC,
    ("zp", "BIT"): 0x24, ("abs", "BIT"): 0x2C,
    ("abs", "JMP"): 0x4C, ("ind", "JMP"): 0x6C, ("abs", "JSR"): 0x20,
    ("zp", "ASL"): 0x06, ("zpx", "ASL"): 0x16, ("abs", "ASL"): 0x0E, ("absx", "ASL"): 0x1E,
    ("zp", "LSR"): 0x46, ("zpx", "LSR"): 0x56, ("abs", "LSR"): 0x4E, ("absx", "LSR"): 0x5E,
    ("zp", "ROL"): 0x26, ("zpx", "ROL"): 0x36, ("abs", "ROL"): 0x2E, ("absx", "ROL"): 0x3E,
    ("zp", "ROR"): 0x66, ("zpx", "ROR"): 0x76, ("abs", "ROR"): 0x6E, ("absx", "ROR"): 0x7E,
    ("zp", "INC"): 0xE6, ("zpx", "INC"): 0xF6, ("abs", "INC"): 0xEE, ("absx", "INC"): 0xFE,
    ("zp", "DEC"): 0xC6, ("zpx", "DEC"): 0xD6, ("abs", "DEC"): 0xCE, ("absx", "DEC"): 0xDE,
}


def parse_lines(source: str) -> list[Line]:
    lines: list[Line] = []
    for lineno, raw in enumerate(source.splitlines(), 1):
        text = raw.split(";", 1)[0].strip()
        if not text:
            continue
        label = None
        op = None
        arg = None
        if text.endswith(":") and " " not in text:
            lines.append(Line(text[:-1], None, None, lineno))
            continue
        equ = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", text)
        if equ:
            lines.append(Line(equ.group(1), ".EQU", equ.group(2).strip(), lineno))
            continue
        first = text.split(None, 1)[0]
        if first.endswith(":"):
            label = first[:-1]
            text = text[len(first) :].strip()
        if text:
            parts = text.split(None, 1)
            op = parts[0].upper()
            arg = parts[1].strip() if len(parts) > 1 else None
        lines.append(Line(label, op, arg, lineno))
    return lines


def parse_number(token: str, labels: dict[str, int]) -> int:
    return parse_expr(token, labels)


def parse_expr(token: str, labels: dict[str, int]) -> int:
    token = token.strip()
    if token.startswith("<"):
        return parse_expr(token[1:], labels) & 0xFF
    if token.startswith(">"):
        return (parse_expr(token[1:], labels) >> 8) & 0xFF
    parts: list[str] = []
    buf = ""
    for ch in token:
        if ch in "+-" and buf:
            parts.append(buf.strip())
            parts.append(ch)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf.strip())
    if not parts:
        raise AsmError(f"empty expression {token!r}")
    total = _atom(parts[0], labels)
    i = 1
    while i < len(parts):
        op = parts[i]
        rhs = _atom(parts[i + 1], labels)
        total = total + rhs if op == "+" else total - rhs
        i += 2
    return total


def _atom(token: str, labels: dict[str, int]) -> int:
    token = token.strip()
    if len(token) == 3 and token[0] == token[-1] and token[0] in "'\"":
        return ord(token[1])
    if token in labels:
        return labels[token]
    if token.startswith("$"):
        return int(token[1:], 16)
    if re.fullmatch(r"-?[0-9]+", token):
        return int(token, 10)
    raise AsmError(f"unknown value {token!r}")


def is_literal_zp(expr: str, labels: dict[str, int]) -> bool:
    try:
        v = parse_number(expr, labels)
    except AsmError:
        return False
    return 0 <= v <= 0xFF


def encode_mode(op: str, mode: str, value: int, lineno: int) -> bytes:
    key = (mode, op)
    if key not in TABLE:
        raise AsmError(f"line {lineno}: {op} does not support {mode}")
    opcode = TABLE[key]
    if mode in ("imm", "zp", "zpx", "zpy", "indx", "indy"):
        return bytes([opcode, value & 0xFF])
    return bytes([opcode, value & 0xFF, (value >> 8) & 0xFF])


def operand_bytes(line: Line, labels: dict[str, int], pc: int) -> bytes:
    op = line.op or ""
    arg = line.arg
    if op in IMPLIED and arg is None:
        return bytes([IMPLIED[op]])
    if op in ACCUM and (arg is None or arg.upper() == "A"):
        return bytes([ACCUM[op]])
    if op in BRANCH:
        if not expr_resolvable(arg or "0", labels):
            return bytes([BRANCH[op], 0])
        target = parse_number(arg or "0", labels)
        rel = target - (pc + 2)
        if rel < -128 or rel > 127:
            raise AsmError(f"line {line.lineno}: branch out of range ({rel})")
        return bytes([BRANCH[op], rel & 0xFF])
    if arg is None:
        raise AsmError(f"line {line.lineno}: {op} needs an operand")

    a = arg.strip()
    if a.startswith("#"):
        expr = a[1:]
        v = parse_number(expr, labels) if expr_resolvable(expr, labels) else 0
        return encode_mode(op, "imm", v, line.lineno)

    m = re.fullmatch(r"\(([^,]+)\s*,\s*[Xx]\)", a)
    if m:
        return encode_mode(op, "indx", parse_number(m.group(1), labels), line.lineno)
    m = re.fullmatch(r"\(([^)]+)\)\s*,\s*[Yy]", a)
    if m:
        return encode_mode(op, "indy", parse_number(m.group(1), labels), line.lineno)
    m = re.fullmatch(r"\(([^)]+)\)", a)
    if m:
        return encode_mode(op, "ind", parse_number(m.group(1), labels), line.lineno)
    m = re.fullmatch(r"(.+),\s*[Xx]", a)
    if m:
        expr = m.group(1).strip()
        v = parse_number(expr, labels) if expr_resolvable(expr, labels) else 0
        mode = "zpx" if is_literal_zp(expr, labels) and ("zpx", op) in TABLE else "absx"
        if not expr_resolvable(expr, labels):
            mode = "absx"
            v = 0
        else:
            v = parse_number(expr, labels)
        return encode_mode(op, mode, v, line.lineno)
    m = re.fullmatch(r"(.+),\s*[Yy]", a)
    if m:
        expr = m.group(1).strip()
        if not expr_resolvable(expr, labels):
            return encode_mode(op, "absy", 0, line.lineno)
        v = parse_number(expr, labels)
        mode = "zpy" if is_literal_zp(expr, labels) and ("zpy", op) in TABLE else "absy"
        return encode_mode(op, mode, v, line.lineno)

    if not expr_resolvable(a, labels):
        return encode_mode(op, "abs", 0, line.lineno)
    v = parse_number(a, labels)
    if is_literal_zp(a, labels) and ("zp", op) in TABLE:
        return encode_mode(op, "zp", v, line.lineno)
    return encode_mode(op, "abs", v, line.lineno)


def expr_resolvable(expr: str, labels: dict[str, int]) -> bool:
    try:
        parse_number(expr, labels)
        return True
    except AsmError:
        return False


def directive_bytes(line: Line, labels: dict[str, int]) -> bytes:
    op = line.op or ""
    arg = line.arg or ""
    if op in (".BYTE", ".DB"):
        out = bytearray()
        for p in split_args(arg):
            if len(p) >= 2 and p[0] == '"' and p[-1] == '"':
                out.extend(p[1:-1].encode("ascii"))
            else:
                out.append(parse_number(p, labels) & 0xFF)
        return bytes(out)
    if op in (".WORD", ".DW"):
        out = bytearray()
        for p in split_args(arg):
            v = parse_number(p, labels) if expr_resolvable(p, labels) else 0
            out.extend((v & 0xFF, (v >> 8) & 0xFF))
        return bytes(out)
    if op == ".ASCII":
        if arg.startswith('"') and arg.endswith('"'):
            return arg[1:-1].encode("ascii")
        raise AsmError(f"line {line.lineno}: .ascii needs a string")
    raise AsmError(f"line {line.lineno}: unknown directive {op}")


def split_args(arg: str) -> list[str]:
    parts: list[str] = []
    cur = ""
    q = False
    for ch in arg:
        if ch == '"':
            q = not q
            cur += ch
        elif ch == "," and not q:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def assemble(source: str, default_origin: int = 0x0200) -> Image:
    lines = parse_lines(source)
    labels: dict[str, int] = {}
    pc = default_origin
    origin = default_origin
    sizes: list[int] = []

    for line in lines:
        if line.label:
            labels[line.label] = pc
        if not line.op:
            sizes.append(0)
            continue
        if line.op == ".EQU":
            labels[line.label or ""] = parse_number(line.arg or "0", labels)
            sizes.append(0)
            continue
        if line.op == ".ORG":
            pc = parse_number(line.arg or "0", labels)
            if all(s == 0 for s in sizes):
                origin = pc
            sizes.append(0)
            continue
        if line.op.startswith("."):
            n = len(directive_bytes(line, labels))
            sizes.append(n)
            pc += n
            continue
        n = len(operand_bytes(line, labels, pc))
        sizes.append(n)
        pc += n

    # pass 2: labels now complete; recompute pc and emit
    pc = default_origin
    chunks: list[tuple[int, bytes]] = []
    for line, n in zip(lines, sizes):
        if line.label:
            labels[line.label] = pc
        if not line.op:
            continue
        if line.op == ".EQU":
            labels[line.label or ""] = parse_number(line.arg or "0", labels)
            continue
        if line.op == ".ORG":
            pc = parse_number(line.arg or "0", labels)
            continue
        if line.op.startswith("."):
            data = directive_bytes(line, labels)
        else:
            data = operand_bytes(line, labels, pc)
        if len(data) != n:
            raise AsmError(f"line {line.lineno}: size mismatch ({n} vs {len(data)})")
        chunks.append((pc, data))
        pc += len(data)

    if not chunks:
        return Image(origin=origin, data=b"", labels=labels)
    start = min(a for a, _ in chunks)
    end = max(a + len(d) for a, d in chunks)
    buf = bytearray(end - start)
    for addr, data in chunks:
        off = addr - start
        buf[off : off + len(data)] = data
    return Image(origin=start, data=bytes(buf), labels=labels)
