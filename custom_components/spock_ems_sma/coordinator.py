import logging
import async_timeout
import json
from aiohttp import ClientSession, ClientError
from typing import Optional, Dict, Any

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from pysma import (
    SMAWebConnect,
    SmaAuthenticationException,
    SmaConnectionException,
    SmaReadException,
)
from pysma.helpers import DeviceInfo

from .const import DOMAIN, SCAN_INTERVAL_SMA
from .sma_writer import SMABatteryWriter

_LOGGER = logging.getLogger(__name__)


def to_int_str_or_none(val: Any) -> Optional[str]:
    """Convierte un valor a int-string, o devuelve None (objeto)."""
    if val is None:
        return None
    try:
        # Convertimos a float, luego a int (para truncar), luego a str
        return str(int(float(val)))
    except (ValueError, TypeError):
        return None  # Devuelve None (objeto)


class SmaTelemetryCoordinator(DataUpdateCoordinator):
    """
    Coordina la obtención de datos de SMA (PULL),
    el envío de telemetría a Spock (PUSH)
    y la aplicación de órdenes de Spock a la batería SMA (Modbus).
    """

    def __init__(
        self,
        hass,
        pysma_api: SMAWebConnect,
        http_session: ClientSession,
        api_token: str,
        plant_id: str,
        spock_api_url: str,
        modbus_host: str,
        modbus_port: int,
        modbus_unit_id: int,
    ):
        """Inicializa el coordinador."""
        self.hass = hass
        self.pysma_api = pysma_api
        self._http_session = http_session
        self._spock_api_url = spock_api_url
        self._plant_id = plant_id

        self._headers = {
            "X-Auth-Token": api_token,
            "Content-Type": "application/json",
        }

        # Configuración Modbus para control de batería
        self._modbus_host = modbus_host
        self._modbus_port = modbus_port
        self._modbus_unit_id = modbus_unit_id

        self.sensors = None
        self.polling_enabled = True

        self.sma_device_info: Optional[DeviceInfo] = None

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} Telemetry",
            update_interval=SCAN_INTERVAL_SMA,
        )

    async def async_initialize_sensors(self):
        """Obtiene la info del dispositivo y la lista de sensores."""
        try:
            _LOGGER.info("Obteniendo información del dispositivo SMA...")
            self.sma_device_info = await self.pysma_api.device_info()
            _LOGGER.info(
                "Dispositivo encontrado: %s (Serial: %s)",
                self.sma_device_info.name,
                self.sma_device_info.serial,
            )

            _LOGGER.info("Obteniendo lista de sensores de SMA...")
            self.sensors = await self.pysma_api.get_sensors()
            _LOGGER.info("Encontrados %d sensores en SMA.", len(self.sensors))

        except Exception as e:
            _LOGGER.error("Error al inicializar sensores de pysma: %s", e)
            raise UpdateFailed(
                f"No se pudo obtener la lista de sensores: {e}"
            ) from e

    async def _async_update_data(self) -> Dict[str, Any]:
        """
        Función principal de polling.
        Paso 1: PULL de datos de SMA (usando pysma).
        Paso 2: Mapeo y PUSH de datos a Spock.
        Paso 3: Aplicación de orden de Spock a la batería SMA (Modbus).
        """

        if not self.polling_enabled:
            _LOGGER.debug(
                "Operativa global desactivada por el switch maestro. Saltando PULL/PUSH."
            )
            return self.data

        if not self.sensors:
            raise UpdateFailed("La lista de sensores de SMA no está inicializada.")

        sensors_dict: Dict[str, Any] = {}

        # --- Paso 1: PULL de SMA ---
        try:
            await self.pysma_api.read(self.sensors)
            sensors_dict = {s.name: s.value for s in self.sensors}
            _LOGGER.debug("Datos PULL de SMA recibidos: %s", sensors_dict)
        except (SmaReadException, SmaConnectionException) as err:
            raise UpdateFailed(f"Error al leer SMA: {err}") from err
        except SmaAuthenticationException as err:
            _LOGGER.warning(
                "Autenticación de SMA fallida, se re-intentará: %s", err
            )
            raise UpdateFailed(f"Autenticación de SMA fallida: {err}") from err

        # --- Paso 2 y 3: PUSH a Spock + Aplicar orden ---
        try:
            spock_payload = self._map_sma_to_spock(sensors_dict)
            await self._async_push_to_spock(spock_payload)
        except Exception as e:
            _LOGGER.error("Error al hacer PUSH de telemetría a Spock: %s", e)
            # Fallback: poner batería en modo AUTO si hay cualquier problema con la petición
            await self._fallback_auto_mode()

        return sensors_dict

    # ---------------------------------------------------------------------
    # Mapeo telemetría
    # ---------------------------------------------------------------------

    def _map_sma_to_spock(self, sensors_dict: dict) -> dict:
        """
        Toma el diccionario de sensores de pysma y lo mapea
        al payload que espera la API de Spock.
        """

        # 1. Potencia de Batería
        charge = sensors_dict.get("battery_power_charge_total", 0) or 0
        discharge = sensors_dict.get("battery_power_discharge_total", 0) or 0
        battery_power = charge - discharge

        # 2. PV Power (Suma de strings A y B)
        pv_a = sensors_dict.get("pv_power_a", 0) or 0
        pv_b = sensors_dict.get("pv_power_b", 0) or 0
        pv_power = pv_a + pv_b

        # --- Lógica de red corregida (según tu petición) ---
        # Usamos los sensores del 'metering' (contador)
        grid_absorb = sensors_dict.get("metering_power_absorbed", 0) or 0
        grid_supply = sensors_dict.get("metering_power_supplied", 0) or 0

        # 'ongrid_power' = valor neto (Importación - Exportación)
        net_grid_power = grid_absorb - grid_supply

        # 'total_grid_output_energy' = valor de exportación bruta
        # (Tal como pediste, usamos 'metering_power_supplied' para esto)
        supply_power = grid_supply
        # --- FIN de la corrección ---

        spock_payload = {
            "plant_id": str(self._plant_id),
            "bat_soc": to_int_str_or_none(sensors_dict.get("battery_soc_total")),
            "bat_power": to_int_str_or_none(battery_power),
            "pv_power": to_int_str_or_none(pv_power),
            "ongrid_power": to_int_str_or_none(net_grid_power),
            "bat_charge_allowed": "true",
            "bat_discharge_allowed": "true",
            "bat_capacity": "0",
            "total_grid_output_energy": to_int_str_or_none(supply_power),
        }

        return spock_payload

    # ---------------------------------------------------------------------
    # Envío a Spock y aplicación de comando
    # ---------------------------------------------------------------------

    async def _async_push_to_spock(self, spock_payload: dict) -> None:
        """Envía telemetría a Spock y aplica la orden recibida (si procede)."""

        _LOGGER.debug(
            "Haciendo PUSH a %s con payload: %s",
            self._spock_api_url,
            spock_payload,
        )

        serialized_payload = json.dumps(spock_payload)

        try:
            async with async_timeout.timeout(10):
                response = await self._http_session.post(
                    self._spock_api_url,
                    data=serialized_payload,
                    headers=self._headers,
                )

            if response.status != 200:
                txt = await response.text()
                _LOGGER.error(
                    "Error HTTP al llamar a Spock (%s): %s",
                    response.status,
                    txt,
                )
                raise UpdateFailed(
                    f"Error de API Spock (HTTP {response.status})"
                )

            try:
                data = await response.json(content_type=None)
            except Exception as e:
                _LOGGER.error("No se pudo parsear JSON de respuesta Spock: %s", e)
                raise

        except ClientError as e:
            _LOGGER.warning("Error de red en PUSH a Spock: %s", e)
            raise
        except Exception as e:
            _LOGGER.error("Error inesperado en PUSH a Spock: %s", e)
            raise

        if not isinstance(data, dict):
            _LOGGER.warning(
                "Respuesta de Spock no es un dict. data=%s", data
            )
            return

        _LOGGER.debug("Respuesta de Spock: %s", data)

        status = data.get("status")
        op_mode = (data.get("operation_mode") or "").lower()

        # Si el formato no es el esperado, no aplicamos nada (pero NO forzamos error aquí)
        if status != "ok" or not op_mode:
            _LOGGER.warning(
                "Respuesta de Spock sin comando válido (status/op_mode). data=%s",
                data,
            )
            return

        # Aplicar comando a la batería
        await self._apply_spock_command(data)

    async def _apply_spock_command(self, spock_cmd: dict) -> None:
        """
        Aplica la orden recibida desde Spock (control de batería por Modbus).
        Espera un diccionario con:
        - operation_mode: 'charge' | 'discharge' | 'auto'
        - action: magnitud en W (positiva, sólo para charge/discharge)
        """
        op_mode = (spock_cmd.get("operation_mode") or "auto").lower()
        raw_action = spock_cmd.get("action", 0)

        try:
            mag = int(float(raw_action))
        except Exception:
            mag = 0

        if mag < 0:
            mag = -mag

        writer = SMABatteryWriter(
            host=self._modbus_host,
            port=self._modbus_port,
            unit_id=self._modbus_unit_id,
        )

        # Modo AUTO → devolver control interno
        if op_mode == "auto":
            _LOGGER.debug(
                "Spock: operation_mode=auto. Poniendo batería SMA en modo AUTO."
            )
            await self.hass.async_add_executor_job(writer.set_auto_mode)
            return

        # Modo CHARGE → consigna de carga
        if op_mode == "charge":
            if mag <= 0:
                _LOGGER.warning(
                    "Spock: operation_mode=charge pero 'action' no válido (%s). "
                    "Pasando a AUTO.",
                    raw_action,
                )
                await self.hass.async_add_executor_job(writer.set_auto_mode)
                return

            _LOGGER.debug(
                "Spock: operation_mode=charge, action=%s W. Forzando CARGA.", mag
            )
            await self.hass.async_add_executor_job(
                writer.set_charge_watts, mag
            )
            return

        # Modo DISCHARGE → consigna de descarga
        if op_mode == "discharge":
            if mag <= 0:
                _LOGGER.warning(
                    "Spock: operation_mode=discharge pero 'action' no válido (%s). "
                    "Pasando a AUTO.",
                    raw_action,
                )
            else:
                _LOGGER.debug(
                    "Spock: operation_mode=discharge, action=%s W. Forzando DESCARGA.",
                    mag,
                )
                await self.hass.async_add_executor_job(
                    writer.set_discharge_watts, mag
                )
                return

            # Si llegamos aquí, 'action' no era válido
            await self.hass.async_add_executor_job(writer.set_auto_mode)
            return

        # Cualquier otro modo desconocido → AUTO por seguridad
        _LOGGER.warning(
            "Spock: operation_mode '%s' no soportado. Pasando a AUTO.", op_mode
        )
        await self.hass.async_add_executor_job(writer.set_auto_mode)

    async def _fallback_auto_mode(self) -> None:
        """Pone la batería en modo AUTO como fallback si falla la petición a Spock."""
        _LOGGER.warning(
            "Fallo en la petición a Spock. Poniendo batería SMA en modo AUTO por seguridad."
        )
        writer = SMABatteryWriter(
            host=self._modbus_host,
            port=self._modbus_port,
            unit_id=self._modbus_unit_id,
        )
        await self.hass.async_add_executor_job(writer.set_auto_mode)
