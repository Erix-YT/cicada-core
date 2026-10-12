# cicada-core

**English** | [Русский](#русский)

Cores for the Cicada Telegram plugin, built automatically from upstream:

- **xray** — [2dust/AndroidLibXrayLite](https://github.com/2dust/AndroidLibXrayLite)
- **singbox** — [Leadaxe/sing-box-lx](https://github.com/Leadaxe/sing-box-lx) (AmneziaWG, XHTTP, Hysteria2, TUIC)

A GitHub Actions workflow checks upstream once a day, builds `classes.dex` and the arm64-v8a
native library, and publishes a release (`xray-<version>`, `singbox-<version>`) with SHA-256 hashes.

Manifests (always the latest version):

- https://raw.githubusercontent.com/Erix-YT/cicada-core/main/manifests/xray.json
- https://raw.githubusercontent.com/Erix-YT/cicada-core/main/manifests/singbox.json

Not affiliated with Xray, sing-box or Telegram.

**License:** the scripts in this repository (`build_core.py`, workflow files) are MIT-licensed. The built cores are not covered by it: they remain under their upstream licenses (sing-box: GPL-3.0, Xray-core: MPL-2.0; see the upstream repositories).

---

## Русский

Ядра для Telegram-плагина Cicada, собираются автоматически из апстрима:

- **xray** — [2dust/AndroidLibXrayLite](https://github.com/2dust/AndroidLibXrayLite)
- **singbox** — [Leadaxe/sing-box-lx](https://github.com/Leadaxe/sing-box-lx) (AmneziaWG, XHTTP, Hysteria2, TUIC)

Раз в сутки GitHub Actions проверяет апстрим, собирает `classes.dex` и нативную библиотеку
arm64-v8a и выкладывает релиз (`xray-<версия>`, `singbox-<версия>`) с хэшами SHA-256.

Манифесты (всегда последняя версия):

- https://raw.githubusercontent.com/Erix-YT/cicada-core/main/manifests/xray.json
- https://raw.githubusercontent.com/Erix-YT/cicada-core/main/manifests/singbox.json

Проект не связан с Xray, sing-box и Telegram.

**Лицензия:** скрипты в этом репозитории (`build_core.py`, файлы workflow) распространяются под MIT. На собранные ядра она не распространяется: они остаются под лицензиями апстримов (sing-box: GPL-3.0, Xray-core: MPL-2.0; см. репозитории апстримов).
