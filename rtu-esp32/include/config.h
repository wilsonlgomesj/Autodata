// Build-time configuration. Override in build_flags or at provisioning.
//
// Secrets (WiFi password, Ed25519 private key) are NOT stored in this
// header — use ESP32 NVS + encrypted flash for production. The defines
// below are runtime-provisioning placeholders for dev/test.

#pragma once

#ifndef AUTODATA_SITE
  #define AUTODATA_SITE "mineradora-x-barragem-norte"
#endif

#ifndef AUTODATA_GATEWAY
  #define AUTODATA_GATEWAY "gw-bx-001"
#endif

#ifndef AUTODATA_DEVICE
  #define AUTODATA_DEVICE "rtu-bx-c1"
#endif

#ifndef AUTODATA_SENSOR
  #define AUTODATA_SENSOR "pz-sec02-fund-01"
#endif

#ifndef AUTODATA_SENSOR_TYPE
  #define AUTODATA_SENSOR_TYPE "piezometer_vw"
#endif

#ifndef AUTODATA_SAMPLE_INTERVAL_MS
  #define AUTODATA_SAMPLE_INTERVAL_MS 15000
#endif

// MQTT broker (dev default; override via NVS in prod)
#ifndef AUTODATA_MQTT_HOST
  #define AUTODATA_MQTT_HOST "192.168.1.10"
#endif
#ifndef AUTODATA_MQTT_PORT
  #define AUTODATA_MQTT_PORT 1883
#endif

#ifndef AUTODATA_FIRMWARE
  #define AUTODATA_FIRMWARE "rtu-esp32-0.1.0"
#endif
