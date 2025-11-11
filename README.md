# Spock EMS (SMA) para Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Este es un componente personalizado (Custom Component) para **Home Assistant** que integra tu inversor solar **SMA** con el servicio de gestión de energía (EMS) de **Spock-p2p**.

Este componente está diseñado como una solución híbrida:

1.  **PULL (Lectura):** Lee la telemetría local de tu inversor SMA (como el SOC de la batería, potencia FV, potencia de red, etc.) utilizando la librería `pysma` (protocolo Webconnect).
2.  **PUSH (Envío):** Formatea estos datos y los envía (Push) a la API en la nube de Spock-p2p para su procesado.
3.  **RECEIVE (Recepción):** Expone un *webhook* local en Home Assistant (`/api/spock_ems_sma`) para recibir comandos de control desde la nube de Spock-p2p.
4.  **CONTROL (HA):** Crea entidades en Home Assistant (sensores y un interruptor) para que puedas monitorizar y controlar la integración directamente desde tu panel de HA.

## Requisitos

* Una instancia de Home Assistant.
* Un inversor SMA (como Sunny Boy, Sunny Tripower, Sunny Island) con la interfaz **Webconnect** habilitada y accesible en tu red local.
* Las credenciales (IP, Grupo de Usuario y Contraseña) de tu dispositivo SMA. Se recomienda encarecidamente usar el grupo **"Installer"** para un acceso completo.
* Una cuenta en la plataforma **Spock-p2p** que te proporcione:
    * Un **Plant ID**.
    * Un **Token de API** (para el `X-Auth-Token`).
* [HACS](https://hacs.xyz/) (Recomendado para la instalación).

---

## 💾 Instalación

### Método 1: HACS (Recomendado)

1.  Abre **HACS** en tu Home Assistant.
2.  Ve a **Integraciones** y haz clic en los tres puntos (arriba a la derecha) y selecciona **"Repositorios personalizados"**.
3.  En la URL del repositorio, pega: `https://github.com/Spock-p2p/ha-spock_ems_sma`
4.  En la Categoría, selecciona **"Integración"**.
5.  Haz clic en **"Añadir"**.
6.  Busca "Spock EMS (SMA)" en HACS y haz clic en **"Instalar"**.
7.  **Reinicia Home Assistant**.

### Método 2: Instalación Manual

1.  Descarga la última [release](https://github.com/Spock-p2p/ha-spock_ems_sma/releases) (o el código `main`).
2.  Descomprime el archivo y localiza la carpeta `spock_ems_sma`.
3.  Copia la carpeta `spock_ems_sma` completa dentro de tu directorio `/config/custom_components/`.
4.  **Reinicia Home Assistant**.

---

## ⚙️ Configuración

Una vez instalado y reiniciado Home Assistant, la configuración se realiza a través de la interfaz de usuario:

1.  Ve a **Ajustes** > **Dispositivos y Servicios**.
2.  Haz clic en **"Añadir Integración"** (botón azul abajo a la derecha).
3.  Busca e instala **"Spock EMS (SMA)"**.
4.  Aparecerá un formulario de configuración. Rellena los siguientes campos:

    * **Plant ID (Spock):** Tu ID de planta proporcionado por Spock-p2p.
    * **Spock API Token:** Tu token de API secreto de Spock-p2p.
    * **Host (IP o DNS) del dispositivo SMA:** La dirección IP local de tu inversor SMA (ej: `192.168.1.50`).
    * **Grupo de Usuario:** El grupo de usuario para iniciar sesión en Webconnect (`user` o `installer`). Se recomienda **`installer`**.
    * **Contraseña:** La contraseña para ese grupo de usuario.
    * **Usar SSL (HTTPS):** Déjalo marcado. La verificación del certificado SSL está desactivada por defecto para permitir los certificados autofirmados de SMA.

5.  Haz clic en **"Enviar"**. La integración validará la conexión con el SMA y, si tiene éxito, la añadirá a Home Assistant.

### Reconfiguración

Puedes cambiar cualquiera de estos valores más tarde haciendo clic en **"Reconfigurar"** en la tarjeta de la integración.

---

## 📊 Entidades Proporcionadas

La integración creará un nuevo **Dispositivo** en Home Assistant, agrupando las siguientes entidades:

### Interruptor (Switch)

* **`switch.spock_ems_sma_control`**: Un interruptor maestro.
    * **ON (Encendido):** El componente funciona normalmente. Lee de SMA y envía datos a Spock cada 10 segundos.
    * **OFF (Apagado):** El componente se pausa. No leerá datos de SMA ni enviará nada a Spock. La API para recibir comandos seguirá activa, pero no ejecutará nada.

### Sensores (Sensor)

Se crean varias entidades de sensor para que puedas ver y graficar los datos de SMA directamente en Home Assistant.

* `sensor.sma_bateria_soc`: Estado de carga de la batería (%).
* `sensor.sma_potencia_red_importacion`: Potencia importada de la red (W).
* `sensor.sma_potencia_red_exportacion`: Potencia exportada a la red (W).
* `sensor.sma_pv_potencia_a`: Potencia del string PV A (W).
* `sensor.sma_pv_potencia_b`: Potencia del string PV B (W).
* `sensor.sma_bateria_potencia_carga`: Potencia de carga de la batería (W).
* `sensor.sma_bateria_potencia_descarga`: Potencia de descarga de la batería (W).
* `sensor.sma_bateria_temperatura`: Temperatura de la batería (°C).
* `sensor.sma_estado`: Estado operativo del inversor (ej: "Ok", "Warning").

---

## 📡 Lógica de la API

### Envío de Telemetría (PUSH a Spock)

Cada 10 segundos (si el *switch* maestro está encendido), el componente lee los datos de `pysma` y los mapea al formato JSON que espera la API de Spock.

Lógica de mapeo aplicada:

* **`bat_power`**: Se calcula como `carga - descarga`. Será positivo (cargando) o negativo (descargando).
* **`pv_power`**: Se calcula como `pv_power_a + pv_power_b`.
* **`ongrid_power`**: Se calcula como `metering_power_absorbed - metering_power_supplied`. Será positivo (importando) o negativo (exportando).
* **`total_grid_output_energy`**: Se mapea directamente a `metering_power_supplied` (exportación bruta).
* **Campos numéricos:** Se convierten a *string de enteros* (truncando decimales) o `null` (si el valor es `None`) para ser compatibles con la API de Spock.
* **Headers:** La petición se envía a `https://ems-ha.spock.es/api/ems_marstek` usando el header `X-Auth-Token` (sin "Bearer").

### Recepción de Comandos (API Local)

* El componente abre el endpoint `/api/spock_ems_sma` en tu Home Assistant.
* Valida las peticiones entrantes usando el `X-Auth-Token` y el `plant_id` proporcionados en la configuración.
* **FASE 1:** Actualmente, la ejecución de comandos está **desactivada**. El componente registrará que ha recibido un comando en el log, pero no ejecutará ninguna acción en el SMA y devolverá un `Status 200` (OK).

---

## 🐛 Depuración (Troubleshooting)

Si algo no funciona, la mejor forma de ver qué pasa es activar los logs de depuración. Añade esto a tu archivo `configuration.yaml`, reinicia HA y revisa los logs en **Ajustes > Sistema > Registros**.

```yaml
logger:
  default: warning
  logs:
    custom_components.spock_ems_sma: debug
    pysma: debug
```
