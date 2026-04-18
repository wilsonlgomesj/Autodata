// Canonical JSON serialization — must byte-for-byte match the Python
// reference in rtu/src/rtu/signing.py. The contract:
//
//   - Drop `sig` and `t_ingest` keys before signing.
//   - sort_keys at every object level.
//   - separators (",", ":") — no whitespace.
//   - UTF-8 output.
//
// Implementation notes:
//   - ArduinoJson's serializeJson() is compact (no whitespace) and deterministic
//     iff keys are inserted in sorted order. We rely on sorting the keys
//     ourselves via JsonDocument::asArray() / doc.as<JsonObject>() after a
//     manual sort pass — see canonicalize() below.
//   - We deliberately avoid floats-as-string conversions that could differ
//     between implementations. All numbers here are stored using native JSON
//     numbers. ArduinoJson uses %.17g internally; Python json uses %.17g-ish
//     too; tests must verify round-trip stability for a known sample set.

#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include <algorithm>
#include <string>
#include <vector>

namespace autodata {

// Recursively walk the document, sorting every JsonObject's keys in-place
// by copying the object's entries into a new JsonDocument in sorted order.
// Destructively rebuilds the document rooted at `root`.
inline void canonicalize_object(JsonObject obj, JsonDocument& scratch) {
    std::vector<std::pair<std::string, int>> keys;
    keys.reserve(obj.size());
    int i = 0;
    for (JsonPair kv : obj) {
        keys.emplace_back(std::string(kv.key().c_str()), i++);
    }
    std::sort(keys.begin(), keys.end(),
              [](auto& a, auto& b) { return a.first < b.first; });

    // Copy to scratch in sorted order, then clear+refill the original.
    scratch.clear();
    JsonObject out = scratch.to<JsonObject>();
    for (auto& [k, _] : keys) {
        out[k] = obj[k.c_str()];
    }
    obj.clear();
    for (JsonPair kv : out) {
        obj[kv.key()] = kv.value();
    }
    // Recurse into nested objects.
    for (JsonPair kv : obj) {
        if (kv.value().is<JsonObject>()) {
            canonicalize_object(kv.value().as<JsonObject>(), scratch);
        }
    }
}

// Builds canonical bytes for a telemetry payload.
// Caller owns `doc`; we strip sig/t_ingest before canonicalizing.
inline size_t canonical_message_bytes(JsonDocument& doc, char* out, size_t out_size) {
    // Remove fields excluded from the signature.
    doc.remove("sig");
    doc.remove("t_ingest");

    // Sort keys recursively (allocate a scratch doc sized for one object).
    JsonDocument scratch;
    if (doc.is<JsonObject>()) {
        canonicalize_object(doc.as<JsonObject>(), scratch);
    }

    return serializeJson(doc, out, out_size);
}

}  // namespace autodata
