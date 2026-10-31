# Environment used to collect and analyse the data

Recorded by the sessions themselves (`data/raw/**/env/*.json`); one row per distinct (board, PlatformIO env, PlatformIO, host, Python).

| board | pio env | PlatformIO | host OS | Python | sessions | toolchain and framework packages |
|---|---|---|---|---|---|---|
| esp32 | esp32dev | PlatformIO Core, version 6.1.19 | macOS-26.3.1-arm64-arm-64bit | 3.11.7 | 8 | framework-arduinoespressif32 3.20017.241212+sha.dcc1105b; framework-espidf 4.60001.0; toolchain-esp32ulp 1.23800.240113; toolchain-xtensa-esp-elf 15.2.0+20251204; toolchain-xtensa-esp32 8.4.0+2021r2-patch5 |
| esp32 | esp32dev | PlatformIO Core, version 6.2.0 | macOS-26.3.1-arm64-arm-64bit | 3.11.7 | 3 | framework-arduinoespressif32 3.20017.241212+sha.dcc1105b; framework-espidf 4.60001.0; toolchain-esp32ulp 1.23800.240113; toolchain-xtensa-esp-elf 15.2.0+20251204; toolchain-xtensa-esp32 8.4.0+2021r2-patch5 |
| esp32 | esp32dev_offload | PlatformIO Core, version 6.1.19 | macOS-26.3.1-arm64-arm-64bit | 3.11.7 | 8 | framework-arduinoespressif32 3.20017.241212+sha.dcc1105b; framework-espidf 4.60001.0; toolchain-esp32ulp 1.23800.240113; toolchain-xtensa-esp-elf 15.2.0+20251204; toolchain-xtensa-esp32 8.4.0+2021r2-patch5 |
| esp8266 | nodemcuv2 | PlatformIO Core, version 6.1.19 | macOS-26.3.1-arm64-arm-64bit | 3.11.7 | 9 | framework-arduinoespressif8266 3.30102.0; toolchain-xtensa 2.100300.220621 |
| esp8266 | nodemcuv2 | PlatformIO Core, version 6.2.0 | macOS-26.3.1-arm64-arm-64bit | 3.11.7 | 3 | framework-arduinoespressif8266 3.30102.0; toolchain-xtensa 2.100300.220621 |
| esp8266 | nodemcuv2_offload | PlatformIO Core, version 6.1.19 | macOS-26.3.1-arm64-arm-64bit | 3.11.7 | 23 | framework-arduinoespressif8266 3.30102.0; toolchain-xtensa 2.100300.220621 |
| esp8266 | nodemcuv2_offload | PlatformIO Core, version 6.2.0 | macOS-26.3.1-arm64-arm-64bit | 3.11.7 | 4 | framework-arduinoespressif8266 3.30102.0; toolchain-xtensa 2.100300.220621 |
| uno | uno | PlatformIO Core, version 6.1.19 | macOS-26.3.1-arm64-arm-64bit | 3.11.7 | 8 | framework-arduino-avr 5.4.0; toolchain-atmelavr 1.70300.191015 |
| uno | uno_offload | PlatformIO Core, version 6.1.19 | macOS-26.3.1-arm64-arm-64bit | 3.11.7 | 4 | framework-arduino-avr 5.4.0; toolchain-atmelavr 1.70300.191015 |

## pip freeze of the interpreter used for the analysis (`3.11.7`)

```
contourpy==1.3.3
cycler==0.12.1
dill==0.4.1
fonttools==4.63.0
kiwisolver==1.5.0
lxml==6.1.1
matplotlib==3.11.1
numpy==2.4.6
packaging==26.3
pandas==3.0.5
pillow==12.3.0
psutil==7.2.2
pyparsing==3.3.2
pypdf==6.18.1
pyserial==3.5
python-dateutil==2.9.0.post0
python-docx==1.2.0
qiskit==2.5.1
qiskit-aer==0.17.2
rustworkx==0.18.1
scipy==1.17.1
six==1.17.0
stevedore==5.9.0
typing_extensions==4.16.0
```
