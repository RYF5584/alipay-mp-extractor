# On-device storage & package format

Tested against Alipay Android 10.x (XRiver / appx-ng container), 2026-10.
All paths under `/data/data/com.eg.android.AlipayGphone/`.

## Storage map

| content | path | format |
|---|---|---|
| business apps + plugins | `files/Sandbox/<hash>/database/ccdn/caches/app/data/<md5-of-url>/0.dc` | tar |
| legacy business apps | `files/nebulaApp/<appId>/<ver>/<appId>.tar` | tar (probed automatically) |
| framework packages | `files/nebulaInstallApps/<appId>/<md5>/<appId>.tar` | tar |
| container metadata | `databases/nebula_app.db`, `nebulax_app.db`, `xriver_app.db`, `aomp_mini_app_center.db` | sqlite |
| ccdn download profile | `shared_prefs/pref_ccdn_profile.xml` | xml |

**Nothing is encrypted.** `0.dc` = USTAR whose first member is `.signature`
(RSA signature, ignorable for reading), followed by `.meta`, `.manifest`,
`<appId>.tar`. The inner tar is the compiled bundle.

## App identity

- third-party mini-program appId: a 16-digit number
- plugin provider ids share the same namespace; declared in the host's
  `appConfig.json` under `"plugins": {"<别名>": {"provider": "<appId>"}}`
- `nebulax_app.db` table `nebulax_resource_app_table`: name/version/package_url
  per app; `nebulax_resource_plugin_table`: plugin packages

## Compiled bundle layout (XRiver / appx-ng)

```
meta.json          page route -> {render: [chunks], worker: [...]}
appConfig.json     window/pages/plugins/launchParams  (app.json equivalent)
index.worker.js    logic layer: single webpack bundle, all business code
index.js           render layer: DSL compiled to Svelte-style functions,
                   CSS embedded as string literals
splitchunk~N/      subpackage render chunks
images/, *.ttf     assets
```

Render functions use a Svelte-like contract (`c`/`d`/`l` hooks, `e.$C`
component helper). `.axml` source is NOT recoverable 1:1; class names, text
and attributes remain in the beautified JS.

## Plugin packages

Plugins live in the same ccdn cache and use the same tar format. The
container DB marks them in `nebulax_resource_plugin_table`. This library
marks them `kind="plugin"`; with `with_plugins=True` a host app's declared
plugins are exported into `plugins/<别名>/`.
