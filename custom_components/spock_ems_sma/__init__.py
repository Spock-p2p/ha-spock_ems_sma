import logging
# import ssl (ya no se usa)
# from aiohttp import TCPConnector (ya no se usa)

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
)
from .coordinator import SmaTelemetryCoordinator
from .http_api import SpockApiView

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Configura la integración desde la Config Entry."""
    
    config = entry.data
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}

    # --- Configuración del cliente PYSMA ---
    protocol = "https" if config[CONF_SSL] else "http"
    url = f"{protocol}://{config[CONF_HOST]}"
    
    # --- ¡CORRECCIÓN! ---
    # Sesión específica para pysma (sin verificar SSL, hardcoded)
    _LOGGER.debug("Creando sesión PYSMA con verify_ssl=False (Hardcoded)")
    pysma_session = async_get_clientsession(hass, verify_ssl=False)
    # --- FIN DE LA CORRECCIÓN ---

    pysma_api = SMAWebConnect(
        session=pysma_session,
        url=url,
        password=config[CONF_PASSWORD],
        group=config[CONF_GROUP],
    )
    
    # Sesión genérica de HA (para el PUSH a Spock)
    http_session = async_get_clientsession(hass)

    # 2. Configurar el Coordinador (PULL de SMA y PUSH a Spock)
    coordinator = SmaTelemetryCoordinator(
        hass=hass,
        pysma_api=pysma_api,
        http_session=http_session,
        api_token=config[CONF_SPOCK_API_TOKEN],
        plant_id=config[CONF_PLANT_ID],
        spock_api_url=SPOCK_TELEMETRY_API_ENDPOINT
    )
    
    # Inicializa la lista de sensores en pysma
    await coordinator.async_initialize_sensors()
    
    # Realiza la primera carga de datos
    await coordinator.async_config_entry_first_refresh()
    
    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    # 3. Registrar las plataformas (sensor.py, switch.py)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 4. Registrar la vista HTTP para RECIBIR comandos
    view = SpockApiView(
        hass=hass,
        entry_id=entry.entry_id,
        api_token=config[CONF_SPOCK_API_TOKEN],
        plant_id=config[CONF_PLANT_ID],
        pysma_api=pysma_api 
    )
    hass.http.register_view(view)
    
    hass.data[DOMAIN][entry.entry_id]["api_view"] = view
    
    # 5. Asegurar cierre de sesión de pysma
    async def _async_handle_shutdown(event: Event) -> None:
        await pysma_api.close_session()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_handle_shutdown)
    )
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Descarga la integración."""
    
    view = hass.data[DOMAIN][entry.entry_id].get("api_view")
    if view:
        hass.http.unregister_view(view.url)

    # Cerramos la sesión de pysma
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    await coordinator.pysma_api.close_session()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
