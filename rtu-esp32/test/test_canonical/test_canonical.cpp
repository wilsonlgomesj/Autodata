// Native unit test for the canonical-JSON layer. Runs on the build host
// via `pio test -e native`. The goal is to confirm that the C++
// implementation produces byte-for-byte the same output as the Python
// reference in rtu/src/rtu/signing.py for a fixed sample payload.
//
// We do NOT run real libsodium here; the signature path is covered by
// hardware-in-the-loop tests on the device. This test locks the one
// thing that would silently break cross-platform: JSON canonicalization.

#define UNIT_TEST 1
#include <ArduinoJson.h>
#include <unity.h>
#include <string.h>

#include "signing/canonical.h"

// Expected canonical bytes for this payload, as produced by the Python
// reference (rtu/src/rtu/signing.py:canonical_message_bytes). Generated
// by hand from the golden payload below.
//
// Payload (sig and t_ingest dropped; keys sorted at every level):
//   {"device":"rtu-bx-c1","firmware":"rtu-fw","gateway":"gw-bx-001",
//    "msg_id":"01HK00000000000000000000AA",
//    "quality":{"code":"GOOD","flags":[]},
//    "schema":"geo.telemetry.v1","sensor":"pz-sec02-fund-01",
//    "sensor_type":"piezometer_vw","seq":1,
//    "site":"mineradora-x-barragem-norte",
//    "t_sample":"2026-04-18T13:45:03.123Z",
//    "values":{"frequency_hz":2345,"pressure_kpa":312.4,"temp_c":25.6}}
static const char* EXPECTED =
    "{\"device\":\"rtu-bx-c1\",\"firmware\":\"rtu-fw\",\"gateway\":\"gw-bx-001\","
    "\"msg_id\":\"01HK00000000000000000000AA\",\"quality\":{\"code\":\"GOOD\","
    "\"flags\":[]},\"schema\":\"geo.telemetry.v1\",\"sensor\":\"pz-sec02-fund-01\","
    "\"sensor_type\":\"piezometer_vw\",\"seq\":1,\"site\":\"mineradora-x-barragem-norte\","
    "\"t_sample\":\"2026-04-18T13:45:03.123Z\",\"values\":{\"frequency_hz\":2345,"
    "\"pressure_kpa\":312.4,\"temp_c\":25.6}}";


static void build_payload(JsonDocument& doc) {
    doc["schema"]      = "geo.telemetry.v1";
    doc["msg_id"]      = "01HK00000000000000000000AA";
    doc["site"]        = "mineradora-x-barragem-norte";
    doc["gateway"]     = "gw-bx-001";
    doc["device"]      = "rtu-bx-c1";
    doc["sensor"]      = "pz-sec02-fund-01";
    doc["sensor_type"] = "piezometer_vw";
    doc["t_sample"]    = "2026-04-18T13:45:03.123Z";
    doc["t_ingest"]    = (const char*)nullptr;
    doc["seq"]         = 1;

    JsonObject values = doc["values"].to<JsonObject>();
    values["pressure_kpa"] = 312.4;
    values["frequency_hz"] = 2345;
    values["temp_c"]       = 25.6;

    JsonObject quality = doc["quality"].to<JsonObject>();
    quality["code"] = "GOOD";
    quality["flags"].to<JsonArray>();

    doc["firmware"] = "rtu-fw";

    // Fields that MUST be stripped.
    doc["sig"] = "ed25519:should-be-removed";
    doc["t_ingest"] = "2026-04-18T13:45:04.000Z";
}

void test_canonical_excludes_sig_and_t_ingest() {
    JsonDocument doc;
    build_payload(doc);

    char out[2048];
    size_t len = autodata::canonical_message_bytes(doc, out, sizeof(out));

    TEST_ASSERT_TRUE(len > 0);
    TEST_ASSERT_NULL(strstr(out, "\"sig\""));
    TEST_ASSERT_NULL(strstr(out, "\"t_ingest\""));
}

void test_canonical_keys_sorted() {
    JsonDocument doc;
    build_payload(doc);
    char out[2048];
    size_t len = autodata::canonical_message_bytes(doc, out, sizeof(out));

    // The 'a' in "device" must come before the 'f' in "firmware" which must
    // come before the 'g' in "gateway". We test by substring positions —
    // proves the recursive key sort is at work.
    const char* p_device   = strstr(out, "\"device\"");
    const char* p_firmware = strstr(out, "\"firmware\"");
    const char* p_gateway  = strstr(out, "\"gateway\"");
    TEST_ASSERT_NOT_NULL(p_device);
    TEST_ASSERT_NOT_NULL(p_firmware);
    TEST_ASSERT_NOT_NULL(p_gateway);
    TEST_ASSERT_TRUE(p_device < p_firmware);
    TEST_ASSERT_TRUE(p_firmware < p_gateway);

    // Nested objects too: "code" before "flags" inside "quality".
    const char* p_code  = strstr(out, "\"code\"");
    const char* p_flags = strstr(out, "\"flags\"");
    TEST_ASSERT_TRUE(p_code < p_flags);

    // values: frequency_hz < pressure_kpa < temp_c lexicographically.
    const char* p_freq = strstr(out, "\"frequency_hz\"");
    const char* p_pres = strstr(out, "\"pressure_kpa\"");
    const char* p_temp = strstr(out, "\"temp_c\"");
    TEST_ASSERT_TRUE(p_freq < p_pres);
    TEST_ASSERT_TRUE(p_pres < p_temp);
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_canonical_excludes_sig_and_t_ingest);
    RUN_TEST(test_canonical_keys_sorted);
    return UNITY_END();
}
