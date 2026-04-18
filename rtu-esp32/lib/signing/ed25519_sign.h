// Ed25519 sign/verify using libsodium's crypto_sign_detached.
//
// Key handling: for the dev / bootstrap path we let the firmware generate
// a keypair on first boot and store it in NVS. For production, devices are
// provisioned with a factory-installed key (sealed via ESP32 flash encryption
// + secure boot). The public key is uploaded to geo.device during pairing.

#pragma once

#include <Arduino.h>

#ifndef UNIT_TEST
  #include <sodium.h>
#else
  // Minimal shims to let host-side unit tests compile without libsodium.
  // The real Ed25519 calls are not exercised in native tests; we cover
  // the canonical-JSON layer and delegate signature logic to hardware CI.
  extern "C" {
    #define crypto_sign_SECRETKEYBYTES 64
    #define crypto_sign_PUBLICKEYBYTES 32
    #define crypto_sign_BYTES 64
    static inline int sodium_init(void) { return 0; }
    static inline int crypto_sign_keypair(unsigned char*, unsigned char*) { return 0; }
    static inline int crypto_sign_detached(
        unsigned char* sig, unsigned long long* sig_len,
        const unsigned char*, unsigned long long,
        const unsigned char*) {
      if (sig_len) *sig_len = 64;
      if (sig) memset(sig, 0, 64);
      return 0;
    }
  }
#endif

#include <string.h>

namespace autodata {

class Ed25519Signer {
 public:
  // Must be called once at boot. Returns true on success.
  bool init() {
    return sodium_init() >= 0;
  }

  // Generate a new keypair into the provided buffers.
  bool generate_keypair(uint8_t public_key[crypto_sign_PUBLICKEYBYTES],
                        uint8_t private_key[crypto_sign_SECRETKEYBYTES]) {
    return crypto_sign_keypair(public_key, private_key) == 0;
  }

  // Load an already-provisioned private key (e.g., from NVS).
  void set_private_key(const uint8_t pk[crypto_sign_SECRETKEYBYTES]) {
    memcpy(private_key_, pk, crypto_sign_SECRETKEYBYTES);
    has_key_ = true;
  }

  // Sign `message` (length `len`). Writes `crypto_sign_BYTES` to `out_sig`.
  // Returns true on success.
  bool sign(const uint8_t* message, size_t len, uint8_t out_sig[crypto_sign_BYTES]) {
    if (!has_key_) return false;
    unsigned long long sig_len = 0;
    return crypto_sign_detached(out_sig, &sig_len, message, len, private_key_) == 0
        && sig_len == crypto_sign_BYTES;
  }

 private:
  uint8_t private_key_[crypto_sign_SECRETKEYBYTES] = {};
  bool has_key_ = false;
};

// Base64 encode exactly 64 raw bytes into a null-terminated buffer of
// length >= 89. Unlike stdlib base64 variants, padding is always included
// to match the Python reference ("ed25519:<base64>").
inline size_t base64_encode_sig(const uint8_t* src, size_t len, char* out) {
    static const char* tbl =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    size_t i = 0, o = 0;
    while (i + 3 <= len) {
        uint32_t n = ((uint32_t)src[i] << 16) | ((uint32_t)src[i+1] << 8) | src[i+2];
        out[o++] = tbl[(n >> 18) & 63];
        out[o++] = tbl[(n >> 12) & 63];
        out[o++] = tbl[(n >>  6) & 63];
        out[o++] = tbl[ n        & 63];
        i += 3;
    }
    if (i < len) {
        uint32_t n = (uint32_t)src[i] << 16;
        if (i + 1 < len) n |= (uint32_t)src[i+1] << 8;
        out[o++] = tbl[(n >> 18) & 63];
        out[o++] = tbl[(n >> 12) & 63];
        out[o++] = (i + 1 < len) ? tbl[(n >> 6) & 63] : '=';
        out[o++] = '=';
    }
    out[o] = '\0';
    return o;
}

}  // namespace autodata
