import logging
from typing import Optional

from pymodbus.client import ModbusTcpClient

_LOGGER = logging.getLogger(__name__)

# Direcciones de registros Modbus (según tus scripts)
REGISTER_POWER_SETPOINT = 40149  # signed 32-bit W (negativo=carga, positivo=descarga)
REGISTER_CONTROL_MODE = 40151    # 802 = manual/external, 803 = auto/internal

MANUAL_MODE_VALUE = 802
AUTO_MODE_VALUE = 803


class SMABatteryWriter:
    """
    Encapsula las escrituras Modbus necesarias para controlar
    la batería del inversor SMA (STPxx-3SE-40, etc.).
    """

    def __init__(self, host: str, port: int = 502, unit_id: int = 3) -> None:
        self._host = host
        self._port = port
        self._unit_id = unit_id

    # ------------------------
    # Helpers internos
    # ------------------------

    @staticmethod
    def _split_u32(val: int) -> tuple[int, int]:
        val &= 0xFFFFFFFF
        hi = (val >> 16) & 0xFFFF
        lo = val & 0xFFFF
        return hi, lo

    @classmethod
    def _split_s32(cls, val: int) -> tuple[int, int]:
        """
        Convierte un entero con signo a representación unsigned 32
        y lo separa en dos registros de 16 bits.
        """
        if val < 0:
            val = (val + (1 << 32)) & 0xFFFFFFFF
        return cls._split_u32(val)

    def _write_u32(self, client: ModbusTcpClient, address: int, value: int) -> None:
        hi, lo = self._split_u32(value)
        regs = [hi, lo]
        res = client.write_registers(address, regs, device_id=self._unit_id)
        if res is None or res.isError():
            _LOGGER.error(
                "Error en write_u32 adr=%s value=%s res=%s",
                address,
                value,
                res,
            )
        else:
            _LOGGER.debug(
                "write_u32 OK adr=%s value=%s regs=%s", address, value, regs
            )

    def _write_s32(self, client: ModbusTcpClient, address: int, value: int) -> None:
        hi, lo = self._split_s32(value)
        regs = [hi, lo]
        res = client.write_registers(address, regs, device_id=self._unit_id)
        if res is None or res.isError():
            _LOGGER.error(
                "Error en write_s32 adr=%s value=%s res=%s",
                address,
                value,
                res,
            )
        else:
            _LOGGER.debug(
                "write_s32 OK adr=%s value=%s regs=%s", address, value, regs
            )

    def _open_client(self) -> Optional[ModbusTcpClient]:
        client = ModbusTcpClient(self._host, port=self._port)
        if not client.connect():
            _LOGGER.error(
                "No se pudo conectar al inversor SMA por Modbus en %s:%s (unit_id=%s)",
                self._host,
                self._port,
                self._unit_id,
            )
            client.close()
            return None
        return client

    # ------------------------
    # API pública
    # ------------------------

    def set_auto_mode(self) -> None:
        """
        Pone la batería en modo AUTO / control interno:
          - 40149 = 0 W (sin consigna externa)
          - 40151 = 803 (control interno)
        """
        client = self._open_client()
        if client is None:
            return

        try:
            _LOGGER.info(
                "Poniendo batería SMA en modo AUTO (40149=0, 40151=%s)",
                AUTO_MODE_VALUE,
            )
            # 1) Quitar consigna externa
            self._write_s32(client, REGISTER_POWER_SETPOINT, 0)
            # 2) Volver a control interno
            self._write_u32(client, REGISTER_CONTROL_MODE, AUTO_MODE_VALUE)
        except Exception as e:
            _LOGGER.error("Error al poner modo AUTO en batería SMA: %s", e)
        finally:
            client.close()

    def set_charge_watts(self, watts: int) -> None:
        """
        Fuerza la carga de la batería con 'watts' W.
        Según tus scripts:
          - watts > 0 significa 'cargar' X W
          - pero el registro 40149 debe recibir un valor NEGATIVO para cargar.
        """
        if watts < 0:
            _LOGGER.warning(
                "set_charge_watts llamado con potencia no positiva (%s). Ignorando.",
                watts,
            )
            return

        client = self._open_client()
        if client is None:
            return

        setpoint = -int(abs(watts))  # negativo = carga

        try:
            _LOGGER.info(
                "Configurando batería SMA en modo MANUAL carga %s W "
                "(40151=%s, 40149=%s)",
                watts,
                MANUAL_MODE_VALUE,
                setpoint,
            )
            # 1) Habilitar control manual / externo
            self._write_u32(client, REGISTER_CONTROL_MODE, MANUAL_MODE_VALUE)
            # 2) Escribir consigna de potencia (negativa = carga)
            self._write_s32(client, REGISTER_POWER_SETPOINT, setpoint)
        except Exception as e:
            _LOGGER.error("Error al forzar carga en batería SMA: %s", e)
        finally:
            client.close()

    def set_discharge_watts(self, watts: int) -> None:
        """
        Fuerza la descarga de la batería con 'watts' W.
        Según tus scripts:
          - watts > 0 significa 'descargar' X W
          - el registro 40149 debe recibir un valor POSITIVO para descargar.
        """
        if watts < 0:
            _LOGGER.warning(
                "set_discharge_watts llamado con potencia no positiva (%s). Ignorando.",
                watts,
            )
            return

        client = self._open_client()
        if client is None:
            return

        setpoint = int(abs(watts))  # positivo = descarga

        try:
            _LOGGER.info(
                "Configurando batería SMA en modo MANUAL descarga %s W "
                "(40151=%s, 40149=%s)",
                watts,
                MANUAL_MODE_VALUE,
                setpoint,
            )
            # 1) Habilitar control manual / externo
            self._write_u32(client, REGISTER_CONTROL_MODE, MANUAL_MODE_VALUE)
            # 2) Escribir consigna de potencia (positiva = descarga)
            self._write_s32(client, REGISTER_POWER_SETPOINT, setpoint)
        except Exception as e:
            _LOGGER.error("Error al forzar descarga en batería SMA: %s", e)
        finally:
            client.close()
