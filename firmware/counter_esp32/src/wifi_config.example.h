// Copy to wifi_config.h (same folder, git-ignored) and fill in. Without wifi_config.h the firmware builds
// with WiFi disabled and talks over USB serial only.
#pragma once
#define WIFI_SSID "your-wifi-name"
#define WIFI_PASS "your-wifi-password"
#define PC_HOST   "192.168.1.50"   // the PC running pc/run.py or pc/counter/bridge.py (check with: ipconfig getifaddr en0)
#define PC_PORT   5055             // must match --counter-port tcp:5055
