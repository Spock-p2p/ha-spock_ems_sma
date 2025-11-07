import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_SPOCK_API_TOKEN,
    CONF_PLANT_ID,
    PLATFORMS,
    SPOCK_TELEMETRY_API_ENDPOINT,
)
from .sma_api import SmaApiClient
from .coordinator import SmaTelemetryCoordinator
from .http_api import SpockApiView

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Configura la integración desde la Config Entry."""
    
    config = entry.data
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}

    # Datos de configuración
    sma_host = config[CONF_HOST]
    sma_user = config[CONF_USERNAME]
    sma_pass = config[CONF_PASSWORD]
    api_token = config[CONF_SPOCK_API_TOKEN]
    plant_id = config[CONF_PLANT_ID]
    
    session = async_get_clientsession(hass)

    # 1. Configurar el Cliente API de SMA (para Telemetría PULL)
    api_client_sma = SmaApiClient(
        host=sma_host,
        username=sma_user,
        password=sma_pass,
        session=session,
    )

    # 2. Configurar el Coordinador (PULL de SMA y PUSH a Spock)
    coordinator = SmaTelemetryCoordinator(
        hass=hass,
        api_client=api_client_sma,
        session=session,
        api_token=api_token,
        plant_id=plant_id,
        spock_api_url=SPOCK_TELEMETRY_API_ENDPOINT
    )
    
    # Realiza la primera carga de datos (PULL) y envío (PUSH)
    await coordinator.async_config_entry_first_refresh()
    
    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    # 3. Registrar las plataformas (sensor.py)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 4. Registrar la vista HTTP para RECIBIR comandos (INBOUND)
    view = SpockApiView(
        hass=hass,
        entry_id=entry.entry_id,
        api_token=api_token,
        plant_id=plant_id
    )
    hass.http.register_view(view)
    
    hass.data[DOMAIN][entry.entry_id]["api_view"] = view
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Descarga la integración."""
    
    # 1. Des-registra la vista HTTP
    view = hass.data[DOMAIN][entry.entry_id].get("api_view")
    if view:
        hass.http.unregister_view(view.url)

    # 2. Descarga las plataformas (sensores)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    # 3. Limpia los datos
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
