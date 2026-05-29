# Viomi Vacuum V8 (STYJ02YM) for Home Assistant

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

Custom integration for the Viomi Vacuum V8 / STYJ02YM (EU version, firmware 3.5.3_0017+).

_Based on work by [@KrzysztofHajdamowicz](https://github.com/KrzysztofHajdamowicz/home-assistant-vacuum-styj02ym) and [@nqkdev](https://github.com/nqkdev/home-assistant-vacuum-styj02ym)._

## Installation

1. Install via [HACS](https://hacs.xyz/) (add as a custom repository) or copy `custom_components/viomi_vacuum_v8` manually.
2. Restart Home Assistant.
3. Add to `configuration.yaml`:

```yaml
vacuum:
  - platform: viomi_vacuum_v8
    host: 192.168.0.105
    token: !secret viomi_vacuum_v8_token
    name: "Viomi Vacuum V8"
```

## Features

- Start / pause / stop / return to dock
- Fan speed control (Silent, Standard, Medium, Turbo)
- Zone, area, point, and segment cleaning via services
- Automatic mop mode detection
- Battery level as a separate sensor entity (device class `battery`)
- Locate (audible signal)
- Send raw miio commands

## Services

| Service | Description |
|---------|-------------|
| `viomi_vacuum_v8.clean_zone` | Clean rectangular zone(s) |
| `viomi_vacuum_v8.clean_area` | Clean polygon area(s) |
| `viomi_vacuum_v8.clean_point` | Spot-clean at a coordinate |
| `viomi_vacuum_v8.clean_segment` | Clean room segment(s) by ID |

See `services.yaml` for full parameter details.

## Changelog

### 2026.5.0

- **Fixed:** Removed deprecated `battery_level` / `VacuumEntityFeature.BATTERY` — battery is now a separate sensor entity with `SensorDeviceClass.BATTERY` (HA 2026.8+ compatible)
- **Fixed:** Platform setup no longer blocks Home Assistant startup (removed `update_before_add=True`)
- **Fixed:** Device timeouts / "No response" now correctly mark entity as unavailable
- **Fixed:** Mop mode correction is now fault-tolerant (won't crash on timeout)
- **Improved:** Full code modernization — type hints, `_attr_*` pattern, clean imports
- **Improved:** Explicit `SCAN_INTERVAL` (30s)

### 2.0.0

- Migrated to `VacuumActivity` enum (replaced deprecated state constants)
- Removed unused `construct` dependency
- Cleaned up services and configuration

## Requirements

- Home Assistant 2024.12+
- `python-miio` >= 0.5.12
