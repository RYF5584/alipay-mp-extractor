# Troubleshooting

| symptom | cause | fix |
|---|---|---|
| `cannot reach adb server` | adb not running / wrong host:port | `adb start-server`; check `--adb-host/--adb-port` |
| `device 'X' not found` | bad serial, unauthorized USB debugging | `adb devices`; re-plug / accept the RSA prompt; pass correct `--serial` |
| `no adb device available` | nothing connected | connect USB or `--connect IP:PORT` (wi-fi adb must be enabled) |
| `root required` | su not granted to shell | approve the Magisk/KernelSU su prompt for adb; verify `adb shell su -c id` returns `uid=0` |
| `pull ... failed` per target | legacy path absent on new Alipay | harmless - only the ccdn target is required on modern versions |
| `all pull targets failed` | no root or wrong device | fix root, then `sync --force` |
| `tar stream corrupted` | adb hiccup on very large transfer | rerun `sync --force`; the tool auto-falls back from adbutils to the system adb binary |
| `no mini-program matches 'X'` | target app never opened on the device | open the mini-program once in Alipay, then `sync --force` |
| `plugin ... not in cache` | plugin package not downloaded yet | open a host page that triggers the plugin, re-sync, re-export |
| beautified js missing (raw only) | formatting failed on that file | ignore - the original file is copied; `--no-beautify` skips formatting entirely |
| empty `used by` for plugins | host not scanned | run `alipay-mp plugins` (scans hosts first) |

## Notes

- The device dump lives in `<workdir>/device_dump/`; delete it or pass
  `--force` to re-pull.
- Multi-user / dual-app (Android user 999 etc.) installs are outside the
  default paths; extend `client.PULL_TARGETS` if needed.
- Windows: use `--connect` for wi-fi adb or install USB drivers; everything
  else is identical.
