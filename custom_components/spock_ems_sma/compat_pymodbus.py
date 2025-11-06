# custom_components/spock_ems_sma/compat_pymodbus.py
from enum import Enum

try:
    # PyModbus < 3.11
    from pymodbus.constants import Endian as _Endian
    Endian = _Endian
except Exception:
    # PyModbus >= 3.11 ya no expone constants.Endian; usamos un shim mínimo
    class Endian(str, Enum):
        Auto = "@"
        Big = ">"
        Little = "<"
