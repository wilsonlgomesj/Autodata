// Autodata RTU — ESP32 reference firmware.
//
// Lifecycle:
//   1. setup() — bring up WiFi, NTP (for t_sample timestamps), NVS keys,
//      LittleFS buffer, MQTT broker connection.
//   2. loop()  — every AUTODATA_SAMPLE_INTERVAL_MS: read sensor, build
//      payload, sign, enqueue, attempt publish. On publish success, mark
//      the buffer entry sent. On failure, leave it pending for the next
//      drain cycle.
//
// This is a starter firmware: the analog sensor read function is a
// deterministic synthetic generator so the firmware can be flashed
// without physical instrumentation and exercise the full contract
// (schema + sig + MQTT) against the dev stack.

#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <time.h>

#include "config.h"
#include "signing/canonical.h"
#include "signing/ed25519_sign.h"
#include "buffer/flash_buffer.h"

// --------------------------------------------------------------------------
// Secrets (provision via NVS in production; hard-coded here for dev bring-up)
// --------------------------------------------------------------------------
#ifndef WIFI_SSID
#define WIFI_SSID "autodata-dev"
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "changeme"
#endif

static WiFiClient g_net;
static PubSubClient g_mqtt(g_net);
static autodata::Ed25519Signer g_signer;
static autodata::FlashBuffer g_buffer;

static uint8_t g_public_key[crypto_sign_PUBLICKEYBYTES];
static uint32_t g_seq = 0;

// --------------------------------------------------------------------------
// Utilities
// --------------------------------------------------------------------------

static String rfc3339_ms() {
    time_t now;
    time(&now);
    struct tm tm_utc;
    gmtime_r(&now, &tm_utc);
    char buf[32];
    strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S", &tm_utc);
    // Append .000Z (ESP32 Arduino does not track millisecond UTC directly).
    String out = String(buf) + ".000Z";
    return out;
}

// Crockford base32; deterministic output.
static const char ULID_ALPHABET[] = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
static void new_ulid(char out[27]) {
    for (int i = 0; i < 26; ++i) {
        out[i] = ULID_ALPHABET[esp_random() & 31];
    }
    out[26] = '\0';
}

// Synthetic sensor read: stable baseline + tiny noise. Replace with a real
// driver (VW freq counter, SDI-12, RS-485/MODBUS) when wiring hardware.
static void read_sensor(float& pressure, float& frequency, float& temp_c) {
    static uint32_t tick = 0;
    tick++;
    pressure  = 312.0f + 0.4f * sinf(tick * 0.1f);
    frequency = 2345.0f + 0.8f * cosf(tick * 0.15f);
    temp_c    = 25.0f + 0.2f * sinf(tick * 0.05f);
}

// --------------------------------------------------------------------------
// Connectivity
// --------------------------------------------------------------------------

static void ensure_wifi() {
    if (WiFi.status() == WL_CONNECTED) return;
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - start) < 15000) {
        delay(250);
    }
}

static void ensure_time() {
    // Only configure once; NTP keeps syncing afterwards.
    configTime(0, 0, "pool.ntp.org", "time.google.com");
    time_t now = 0;
    int tries = 0;
    while (now < 1700000000 && tries++ < 20) {
        delay(500);
        time(&now);
    }
}

static bool ensure_mqtt() {
    if (g_mqtt.connected()) return true;
    g_mqtt.setServer(AUTODATA_MQTT_HOST, AUTODATA_MQTT_PORT);
    g_mqtt.setBufferSize(2048);
    String cid = String("rtu-esp32-") + AUTODATA_DEVICE;
    return g_mqtt.connect(cid.c_str());
}

// --------------------------------------------------------------------------
// Payload build / sign / publish
// --------------------------------------------------------------------------

static bool build_and_publish() {
    float pressure, frequency, temp_c;
    read_sensor(pressure, frequency, temp_c);

    // JSON document sized to hold the full payload comfortably.
    JsonDocument doc;
    char ulid[27];
    new_ulid(ulid);

    doc["schema"]      = "geo.telemetry.v1";
    doc["msg_id"]      = ulid;
    doc["site"]        = AUTODATA_SITE;
    doc["gateway"]     = AUTODATA_GATEWAY;
    doc["device"]      = AUTODATA_DEVICE;
    doc["sensor"]      = AUTODATA_SENSOR;
    doc["sensor_type"] = AUTODATA_SENSOR_TYPE;
    doc["t_sample"]    = rfc3339_ms();
    doc["t_ingest"]    = (const char*)nullptr;
    doc["seq"]         = ++g_seq;

    JsonObject values = doc["values"].to<JsonObject>();
    values["pressure_kpa"] = pressure;
    values["frequency_hz"] = frequency;
    values["temp_c"]       = temp_c;

    JsonObject quality = doc["quality"].to<JsonObject>();
    quality["code"] = "GOOD";
    quality["flags"].to<JsonArray>();  // empty array

    doc["firmware"]    = AUTODATA_FIRMWARE;

    // Canonical bytes (sig/t_ingest excluded, keys sorted) → buffer.
    char canon[1536];
    JsonDocument signed_view;
    signed_view.set(doc);
    size_t clen = autodata::canonical_message_bytes(signed_view, canon, sizeof(canon));

    uint8_t raw_sig[crypto_sign_BYTES];
    if (!g_signer.sign(reinterpret_cast<const uint8_t*>(canon), clen, raw_sig)) {
        return false;
    }

    char sig_b64[96];
    autodata::base64_encode_sig(raw_sig, crypto_sign_BYTES, sig_b64);
    String sig = String("ed25519:") + sig_b64;
    doc["sig"] = sig;

    // Serialize the signed payload for transport.
    char out[2048];
    size_t n = serializeJson(doc, out, sizeof(out));
    String topic = String("tel/") + AUTODATA_SITE + "/"
                 + AUTODATA_GATEWAY + "/" + AUTODATA_DEVICE + "/"
                 + AUTODATA_SENSOR + "/meas";

    // Store-and-forward: buffer first, then publish.
    uint32_t row = g_buffer.enqueue(g_seq, out);
    if (!ensure_mqtt()) return false;
    bool ok = g_mqtt.publish(topic.c_str(), out, n);
    if (ok && row) g_buffer.mark_sent(row);

    // Quota: evict sent rows if flash usage exceeds 300KB.
    g_buffer.enforce_quota(300 * 1024);
    return ok;
}

// --------------------------------------------------------------------------
// Arduino entry points
// --------------------------------------------------------------------------

void setup() {
    Serial.begin(115200);
    delay(200);

    if (!g_signer.init()) {
        Serial.println("libsodium init failed");
    }

    // In dev we generate a fresh keypair each boot; in prod, load from NVS.
    uint8_t priv[crypto_sign_SECRETKEYBYTES];
    g_signer.generate_keypair(g_public_key, priv);
    g_signer.set_private_key(priv);

    if (!g_buffer.begin("/buf")) {
        Serial.println("LittleFS mount failed");
    }

    ensure_wifi();
    ensure_time();
    ensure_mqtt();

    Serial.println("Autodata RTU (ESP32) started");
    Serial.print("public key bytes: ");
    for (size_t i = 0; i < sizeof(g_public_key); ++i) {
        Serial.printf("%02x", g_public_key[i]);
    }
    Serial.println();
}

void loop() {
    static unsigned long next = 0;
    unsigned long now = millis();
    if (now >= next) {
        ensure_wifi();
        if (build_and_publish()) {
            Serial.print("published seq="); Serial.println(g_seq);
        } else {
            Serial.println("publish failed; data buffered");
        }
        next = now + AUTODATA_SAMPLE_INTERVAL_MS;
    }
    g_mqtt.loop();
    delay(20);
}
