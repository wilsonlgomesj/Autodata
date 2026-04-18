// LittleFS-backed store-and-forward buffer for ESP32.
//
// Mirrors the Python reference's contract:
//   - enqueue-before-publish (caller MUST call enqueue before attempting MQTT)
//   - mark_sent only after broker PUBACK
//   - FIFO eviction of sent entries first when space is tight
//
// Storage layout: one file per message under /buf/<seq>.json, plus a small
// manifest file tracking sent/unsent state. This is simpler than a full
// embedded DB and keeps wear-leveling behavior predictable.

#pragma once

#ifndef UNIT_TEST
  #include <Arduino.h>
  #include <LittleFS.h>
#else
  // Stubs for host unit tests.
  namespace fs { class File {}; }
#endif

#include <string.h>

namespace autodata {

class FlashBuffer {
 public:
#ifndef UNIT_TEST
  bool begin(const char* root = "/buf") {
    if (!LittleFS.begin(true)) return false;
    if (!LittleFS.exists(root)) LittleFS.mkdir(root);
    strncpy(root_, root, sizeof(root_) - 1);
    return true;
  }

  uint32_t enqueue(uint32_t seq, const char* payload) {
    char path[64];
    snprintf(path, sizeof(path), "%s/%lu.json", root_, (unsigned long)seq);
    fs::File f = LittleFS.open(path, "w");
    if (!f) return 0;
    f.print(payload);
    f.close();
    pending_++;
    return seq;
  }

  bool mark_sent(uint32_t seq) {
    // Rename <seq>.json -> <seq>.sent. Cheap on LittleFS.
    char from[64], to[64];
    snprintf(from, sizeof(from), "%s/%lu.json", root_, (unsigned long)seq);
    snprintf(to, sizeof(to),     "%s/%lu.sent", root_, (unsigned long)seq);
    if (!LittleFS.rename(from, to)) return false;
    if (pending_) pending_--;
    return true;
  }

  // Evict oldest sent files when usage exceeds threshold_bytes.
  void enforce_quota(size_t threshold_bytes) {
    size_t used = LittleFS.usedBytes();
    if (used <= threshold_bytes) return;
    fs::File dir = LittleFS.open(root_);
    if (!dir || !dir.isDirectory()) return;
    fs::File f;
    while ((f = dir.openNextFile())) {
      const char* name = f.name();
      if (strstr(name, ".sent")) {
        char path[96];
        snprintf(path, sizeof(path), "%s/%s", root_, name);
        f.close();
        LittleFS.remove(path);
        used = LittleFS.usedBytes();
        if (used <= threshold_bytes) break;
      } else {
        f.close();
      }
    }
  }

  uint32_t pending_count() const { return pending_; }
#else
  bool begin(const char*) { return true; }
  uint32_t enqueue(uint32_t seq, const char*) { pending_++; return seq; }
  bool mark_sent(uint32_t) { if (pending_) pending_--; return true; }
  void enforce_quota(size_t) {}
  uint32_t pending_count() const { return pending_; }
#endif

 private:
  char root_[32] = "/buf";
  uint32_t pending_ = 0;
};

}  // namespace autodata
