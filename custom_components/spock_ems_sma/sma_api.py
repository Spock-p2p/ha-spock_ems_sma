import logging
import async_timeout
from aiohttp import ClientSession, ClientError
from typing import Optional, Dict, Any

_LOGGER = logging.getLogger(__name__)

# Endpoints de la API ennexOS
LOGIN_URL = "/api/v1/login"
RPC_URL = "/api/v1/services"

class SmaApiClient:
    """Cliente para la API JSON-RPC de SMA ennexOS (Data Manager M)."""

    def __init__(self, host: str, username: str, password: str, session: ClientSession):
        self._host = host
        self._username = username
        self._password = password
        self.session = session # Usamos la sesión de HA
        self._session_token: Optional[str] = None
        self._base_url = f"https://{self._host}"

    async def _request(
        self,
        method: str,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Hace una petición HTTP genérica, manejando errores."""
        
        # ennexOS usa certificados autofirmados, ignoramos la validación SSL
        async with async_timeout.timeout(10):
            try:
                resp = await self.session.request(
                    method,
                    url,
                    json=data,
                    headers=headers,
                    ssl=False  # ¡Importante!
                )
                
                if resp.status == 401:  # Token expirado
                    self._session_token = None
                    raise SmaApiError("Token expirado o inválido")
                
                resp.raise_for_status() # Lanza excepción si hay error HTTP
                
                return await resp.json()

            except ClientError as err:
                raise SmaApiError(f"Error de red: {err}")
            except Exception as e:
                raise SmaApiError(f"Error inesperado en request: {e}")

    async def _login(self):
        """Realiza el login y almacena el token de sesión."""

        url = self._base_url + LOGIN_URL

        # Mapeo de 'username' al 'right' (rol) que exige la API
        RIGHTS_MAP = {
            "installer": "inst",
            "user": "usr",
        }
        
        # Asigna el 'right' correcto, o usa 'usr' por defecto
        user_right = RIGHTS_MAP.get(self._username, "usr")

        payload = {
            "userName": self._username,
            "password": self._password,
            "right": user_right
        }
        
        _LOGGER.debug(f"Intentando login en {self._host} con payload: {{userName: '{self._username}', right: '{user_right}'}}")
        
        try:
            result = await self._request("POST", url, data=payload)
            self._session_token = result.get("token")
            if not self._session_token:
                raise SmaApiError("Login fallido, no se recibió token")
            _LOGGER.info(f"Login en SMA {self._host} exitoso")
        except SmaApiError as e:
            _LOGGER.error(f"Fallo al hacer login en SMA: {e}")
            raise

    async def _rpc_request(self, rpc_method: str, params: Optional[Dict] = None) -> Dict:
        """Ejecuta una llamada JSON-RPC."""
        if not self._session_token:
            await self._login()

        url = self._base_url + RPC_URL
        headers = {"Authorization": f"Bearer {self._session_token}"}
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": rpc_method,
            "params": params or {},
        }
        
        try:
            response = await self._request("POST", url, data=payload, headers=headers)
            if "error" in response:
                raise SmaApiError(f"Error RPC: {response['error']}")
            return response.get("result", {})
        
        except SmaApiError as e:
            # Si el token falló, reintenta el login una vez
            if "expirado" in str(e):
                _LOGGER.info("Token expirado, re-intentando login...")
                self._session_token = None
                return await self._rpc_request(rpc_method, params)
            raise

    async def test_connection(self):
        """Método simple para el Config Flow para validar credenciales."""
        await self._login()

    async def get_instantaneous_values(self) -> Dict[str, Any]:
        """
        Obtiene todos los valores de telemetría (instantáneos).
        Esta es la función que llamará el Coordinator.
        """
        # Pedimos todos los canales ("channels": [])
        result = await self._rpc_request("getValues", {"channels": []})
        
        # El resultado es un diccionario de canales, lo aplanamos
        # ej: {"channel_id": {"value": 123}} -> {"channel_id": 123}
        flat_data = {}
        if isinstance(result, dict):
            for channel_id, data in result.items():
                if isinstance(data, dict) and "value" in data:
                    flat_data[channel_id] = data["value"]
        
        if not flat_data:
            _LOGGER.warning("La API de SMA devolvió datos vacíos")

        return flat_data

class SmaApiError(Exception):
    """Error genérico para el cliente API de SMA."""
    pass
