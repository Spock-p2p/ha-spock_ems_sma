# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A **Home Assistant custom integration** (HACS, domain `spock_ems_sma`) that bridges a local **SMA** solar inverter to the **Spock-p2p** cloud EMS. All integration code lives under [custom_components/spock_ems_sma/](custom_components/spock_ems_sma/). There is no build system, test suite, or package manifest — dependencies are declared in [manifest.json](custom_components/spock_ems_sma/manifest.json) and installed by Home Assistant at runtime (`pysma`, `pymodbus`).

This is one of several sibling brand integrations (`ha-spock_ems_<brand>`: SMA, Growatt, Sonnen, Marstek). They share the same PULL/PUSH/command architecture but differ in the inverter protocol layer.

## Core Architecture: the hybrid control loop

Everything runs through one `DataUpdateCoordinator` ([coordinator.py](custom_components/spock_ems_sma/coordinator.py), `SmaTelemetryCoordinator`) firing every `SCAN_INTERVAL_SMA` (30s, in [const.py](custom_components/spock_ems_sma/const.py)). Each cycle, `_async_update_data` does three things in order:

1. **PULL** — read live telemetry from the SMA inverter via `pysma` (Webconnect HTTP protocol).
2. **PUSH** — map the readings to Spock's payload shape (`_map_sma_to_spock`) and POST them to the Spock cloud API (`SPOCK_TELEMETRY_API_ENDPOINT`).
3. **COMMAND** — the Spock POST **response body** carries the battery command (`operation_mode` ∈ `auto|charge|discharge`, plus `action` in watts). This is applied to the inverter over **Modbus TCP** ([sma_writer.py](custom_components/spock_ems_sma/sma_writer.py)).

**Key point — commands ride the PUSH response.** There is no inbound HTTP endpoint. `SPOCK_COMMAND_API_PATH` in const.py is dead code, and the README's description of a local `/api/spock_ems_sma` command endpoint and a "Phase 1 disabled" command stage is **outdated** — Modbus control is fully wired up. Trust the code over the README.

**Two distinct HTTP sessions** are created in [__init__.py](custom_components/spock_ems_sma/__init__.py): a `pysma` session with `verify_ssl=False` (hardcoded, to tolerate SMA self-signed certs) for the local inverter, and a normal HA session for the Spock cloud PUSH.

**Safety fallback:** any failure during the PUSH/command step calls `_fallback_auto_mode()`, which forces the battery back to internal AUTO control over Modbus. Unknown/invalid `operation_mode` or `action` values also fall back to AUTO. The guiding principle is *never leave the battery stuck on a stale external setpoint.*

**Master switch gate:** `coordinator.polling_enabled` (toggled by the switch entity in [switch.py](custom_components/spock_ems_sma/switch.py), state restored across restarts) short-circuits the entire cycle when OFF — no PULL, no PUSH, no command.

## Modbus battery control (sma_writer.py)

`SMABatteryWriter` performs raw register writes; `pymodbus` is synchronous, so calls are wrapped in `hass.async_add_executor_job`. Two registers drive everything:

- `40151` control mode: `802` = manual/external setpoint, `803` = auto/internal.
- `40149` power setpoint, **signed** 32-bit watts: **negative = charge, positive = discharge** (note the sign inversion — `set_charge_watts` negates the requested watts).

Port is hardcoded to `502`; `unit_id` is configurable (`CONF_MODBUS_UNIT_ID`, default `3`).

## Telemetry mapping gotcha (coordinator.py `_map_sma_to_spock`)

Grid import/export are summed **per phase** (`metering_active_power_draw_l1..l3`, `..._feed_l1..l3`), not read from the three-phase totals — the netted totals cancel across phases and read ~0. `load_power` is **derived** from an energy balance (`pv + grid_import − grid_export − bat_power`), not measured. All numeric fields are pushed as truncated integer strings (or `null`) via `to_int_str_or_none`.

## Entities

Sensors ([sensor.py](custom_components/spock_ems_sma/sensor.py)) are created **dynamically**: only `SENSOR_MAP` keys present in the first coordinator refresh become entities. All entities (sensors + master switch) attach to a single HA device keyed by the inverter serial. Adding a sensor = add an entry to `SENSOR_MAP` (the pysma sensor key must match exactly).

## Config flow ([config_flow.py](custom_components/spock_ems_sma/config_flow.py))

UI-driven setup validates the SMA connection live via `pysma.new_session()`/`device_info()` before creating the entry; the inverter serial becomes the unique ID (prevents duplicates). The options flow re-validates and rewrites `config_entry.data` (everything is stored in `.data`, nothing in `.options`), then reloads the integration. Translations: [translations/en.json](custom_components/spock_ems_sma/translations/en.json), [translations/es.json](custom_components/spock_ems_sma/translations/es.json).

## Development workflow

No local build/lint/test. To exercise changes you need a running Home Assistant instance:

- **Deploy:** copy `custom_components/spock_ems_sma/` into the HA config's `custom_components/` directory, then restart HA. (HACS does this from the GitHub repo for end users.)
- **Release:** bump `version` in [manifest.json](custom_components/spock_ems_sma/manifest.json) — HACS keys updates off it.
- **Debug logging** (add to HA `configuration.yaml`, restart):
  ```yaml
  logger:
    default: warning
    logs:
      custom_components.spock_ems_sma: debug
      pysma: debug
  ```

## Conventions

Code comments, docstrings, log messages, and commit messages are written in **Spanish** — match that when editing. HA constants (`CONF_HOST`, `CONF_SSL`, etc.) come from `homeassistant.const`; integration-specific keys live in [const.py](custom_components/spock_ems_sma/const.py).
