"""Quick tour of the library API (run against a connected rooted device)."""

from alipay_mp_extractor import AlipayMPExtractor

mp = AlipayMPExtractor(workdir="./ws")            # or AlipayMPExtractor(connect="127.0.0.1:5555")

print("devices:", mp.devices())
mp.sync()                                # pull packages from the device

for app in mp.list():                    # everything found
    print(f"{app.app_id}  {app.name:<12} v{app.version}  {app.size/1e6:.1f}MB")

print(mp.search("<name>"))               # search by name
app = mp.query("<appId>")                # resolve one app
print(app.to_dict())

out = mp.export("<name>", with_plugins=True)  # unpack + decompile (opt-in plugins)
print("exported to", out)
print("plugins:", [d["alias"] for d in app.plugins])

print("plugins on device:", [p.provider for p in mp.plugins()])
print("framework packages:", [f.name for f in mp.framework()])
