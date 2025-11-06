# custom_components/spock_ems_sma/compat_payload.py
from __future__ import annotations
from dataclasses import dataclass
from struct import unpack
from typing import List
from .compat_pymodbus import Endian

def _fmt_prefix(byteorder: Endian) -> str:
    if byteorder == Endian.Big:
        return ">"
    if byteorder == Endian.Little:
        return "<"
    # Auto/native; usa big-endian por seguridad en Modbus
    return ">"

@dataclass
class BinaryPayloadDecoder:
    _buf: bytes
    _pos: int
    _byteorder: Endian
    _wordorder: Endian

    @classmethod
    def fromRegisters(
        cls,
        registers: List[int],
        byteorder: Endian = Endian.Big,
        wordorder: Endian = Endian.Big,
    ) -> "BinaryPayloadDecoder":
        # Cada registro es 2 bytes. Aplicamos byteorder a nivel de byte.
        b = bytearray()
        for reg in registers:
            reg &= 0xFFFF
            if byteorder == Endian.Big:
                b.extend([(reg >> 8) & 0xFF, reg & 0xFF])
            else:  # Little
                b.extend([reg & 0xFF, (reg >> 8) & 0xFF])
        return cls(bytes(b), 0, byteorder, wordorder)

    # ---- helpers ----
    def _take(self, n: int) -> bytes:
        chunk = self._buf[self._pos : self._pos + n]
        if len(chunk) != n:
            raise IndexError("Decoder buffer underflow")
        self._pos += n
        return chunk

    def _reorder_words(self, data: bytes) -> bytes:
        # Cambia el orden de palabras de 16 bits si corresponde
        if self._wordorder == Endian.Little and len(data) % 2 == 0:
            words = [data[i : i + 2] for i in range(0, len(data), 2)]
            words.reverse()
            return b"".join(words)
        return data

    # ---- decoders más usados ----
    def decode_16bit_uint(self) -> int:
        data = self._take(2)
        return unpack(_fmt_prefix(self._byteorder) + "H", data)[0]

    def decode_16bit_int(self) -> int:
        data = self._take(2)
        return unpack(_fmt_prefix(self._byteorder) + "h", data)[0]

    def decode_32bit_uint(self) -> int:
        data = self._reorder_words(self._take(4))
        return unpack(_fmt_prefix(self._byteorder) + "I", data)[0]

    def decode_32bit_int(self) -> int:
        data = self._reorder_words(self._take(4))
        return unpack(_fmt_prefix(self._byteorder) + "i", data)[0]

    def decode_32bit_float(self) -> float:
        data = self._reorder_words(self._take(4))
        return unpack(_fmt_prefix(self._byteorder) + "f", data)[0]

    # utilitario opcional
    def skip_bytes(self, n: int) -> None:
        self._pos = min(len(self._buf), self._pos + n)


class BinaryPayloadBuilder:
    """
    Stub muy simple para no romper imports.
    Amplíalo si en el futuro realmente construyes payloads.
    """
    def __init__(self, byteorder: Endian = Endian.Big, wordorder: Endian = Endian.Big):
        self._byteorder = byteorder
        self._wordorder = wordorder
        self._buf: bytearray = bytearray()

    def to_registers(self) -> List[int]:
        b = bytes(self._buf)
        if len(b) % 2 == 1:
            b += b"\x00"
        regs = []
        for i in range(0, len(b), 2):
            hi, lo = b[i], b[i + 1]
            if self._byteorder == Endian.Big:
                regs.append((hi << 8) | lo)
            else:
                regs.append((lo << 8) | hi)
        if self._wordorder == Endian.Little and len(regs) > 1:
            regs = list(reversed(regs))
        return regs
