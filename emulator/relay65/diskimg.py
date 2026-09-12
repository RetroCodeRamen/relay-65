"""CF image layout the real card will hold.

LBA 0     MBR (partition 1 starts at 2048)
LBA 1–128 kernel 64 KiB image (same bytes the ROM loader copies)
LBA 2048+ FUZIX filesystem
"""

from __future__ import annotations

import struct

KERNEL_LBA = 1
KERNEL_SECTORS = 128
FS_LBA = 2048
DEFAULT_SIZE = 4 * 1024 * 1024


def build_cf(
    kernel: bytes,
    filesys: bytes | None = None,
    size: int = DEFAULT_SIZE,
) -> bytes:
    img = bytearray(size)
    img[446] = 0x80
    img[450] = 0x81
    struct.pack_into("<I", img, 454, FS_LBA)
    fs_len = len(filesys) if filesys else 2048 * 512
    struct.pack_into("<I", img, 458, max(fs_len, 512) // 512)
    img[510] = 0x55
    img[511] = 0xAA
    blob = bytearray(KERNEL_SECTORS * 512)
    blob[: len(kernel)] = kernel[: len(blob)]
    off = KERNEL_LBA * 512
    img[off : off + len(blob)] = blob
    if filesys:
        fo = FS_LBA * 512
        end = fo + len(filesys)
        if end > len(img):
            img.extend(b"\x00" * (end - len(img)))
        img[fo:end] = filesys
    return bytes(img)
