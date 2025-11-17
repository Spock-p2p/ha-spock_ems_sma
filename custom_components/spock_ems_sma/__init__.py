import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, Event
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from pysma import SMAWebConnect

from .const import (
    DOMAIN,
    CONF_GROUP,
    CONF_SPOCK_API_TOKEN,
    CONF_PLANT_ID,
    PLATFORMS,
    SPOCK_TELEMETRY_API_ENDPOINT,
    CONF_MODBUS_PORT,
    CONF_MODBUS_UNIT_ID,
)
from .coordinator import SmaTelemetryCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configura la integración desde la Config Entry."""

    config = entry.data
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}

    # --- Configuración del cliente PYSMA ---
    protocol = "https" if config[CONF_SSL] else "http"
    url = f"{protocol}://{config[CONF_HOST]}"

    # Sesión específica para pysma (sin verificar SSL, hardcoded)
    _LOGGER.debug("Creando sesión PYSMA con verify_ssl=False (Hardcoded)")
    pysma_session = async_get_clientsession(hass, verify_ssl=False)

    pysma_api = SMAWebConnect(
        session=pysma_session,
        url=url,
        password=config[CONF_PASSWORD],
        group=config[CONF_GROUP],
    )

    # Sesión genérica de HA (para el PUSH a Spock)
    http_session = async_get_clientsession(hass)

    # Parámetros Modbus para control de batería
    modbus_port = int(config.get(CONF_MODBUS_PORT, 502))
    modbus_unit_id = int(config.get(CONF_MODBUS_UNIT_ID, 3))

    # Coordinador: PULL de SMA + PUSH a Spock + aplicación de comandos (Modbus)
    coordinator = SmaTelemetryCoordinator(
        hass=hass,
        pysma_api=pysma_api,
        http_session=http_session,
        api_token=config[CONF_SPOCK_API_TOKEN],
        plant_id=config[CONF_PLANT_ID],
        spock_api_url=SPOCK_TELEMETRY_API_ENDPOINT,
        modbus_host=config[CONF_HOST],
        modbus_port=modbus_port,
        modbus_unit_id=modbus_unit_id,
    )

    # Inicializa la lista de sensores en pysma
    await coordinator.async_initialize_sensors()

    # Primera carga de datos
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    # Registrar las plataformas (sensor.py, switch.py)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Asegurar cierre de sesión de pysma en apagado de HA
    async def _async_handle_shutdown(event: Event) -> None:
        await pysma_api.close_session()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_handle_shutdown)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Descarga la integración."""

    coordinator: SmaTelemetryCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    # Cerramos la sesión de pysma
    await coordinator.pysma_api.close_session()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
