# Home Assistant support for Viomi Vacuum V8 (STYJ02YM)

This is for Viomi Vacuum V8 (STYJ02YM) (apparently EU version) with 3.5.3_0017 firmware.

_Original code by [@KrzysztofHajdamowicz](https://github.com/KrzysztofHajdamowicz/home-assistant-vacuum-styj02ym) and [@nqkdev](https://github.com/nqkdev/home-assistant-vacuum-styj02ym)._

## Install and usage
- Install it with [HACS](https://hacs.xyz/)
- Add the configuration to `configuration.yaml`, example:

```yaml
vacuum:
  - platform: viomi_vacuum_v8
    host: 192.168.0.105
    token: !secret viomi_vacuum_v8_token
    name: 'Viomi Vacuum V8'
```

Services described in the `services.yaml`.
