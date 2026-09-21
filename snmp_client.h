// ============================================================
// snmp_client.h - SNMP Client untuk MikroTik
// ============================================================
// Mengambil data monitoring dari MikroTik via SNMP.
// UDP port 161, community string.
// NON-BLOCKING: satu request per poll, agar loop() tetap
// memproses touch setiap saat.
// ============================================================

#ifndef SNMP_CLIENT_H
#define SNMP_CLIENT_H

#include <WiFi.h>
#include <WiFiUdp.h>

// ==================== OID MIKROTIK ====================
#define OID_SYS_NAME      "1.3.6.1.2.1.1.5.0"
#define OID_SYS_UPTIME    "1.3.6.1.2.1.1.3.0"
#define OID_MK_CPU_LOAD   "1.3.6.1.4.1.14988.1.1.3.10.0"
#define OID_MK_TOTAL_MEM  "1.3.6.1.4.1.14988.1.1.3.8.0"
#define OID_MK_FREE_MEM   "1.3.6.1.4.1.14988.1.1.3.11.0"
#define OID_MK_BOARD_NAME "1.3.6.1.4.1.14988.1.1.3.4.0"
#define OID_MK_VERSION    "1.3.6.1.4.1.14988.1.1.3.7.0"
#define OID_IF_DESCR      "1.3.6.1.2.1.2.2.1.2"
#define OID_IF_IN_OCTETS  "1.3.6.1.2.1.2.2.1.10"
#define OID_IF_OUT_OCTETS "1.3.6.1.2.1.2.2.1.16"
#define OID_IF_STATUS     "1.3.6.1.2.1.2.2.1.8"

// ==================== STRUKTUR DATA ====================
struct InterfaceInfo {
  char name[32];
  unsigned long rxBytes;
  unsigned long txBytes;
  int status;
  bool valid;
};

struct SNMPData {
  int cpuLoad;
  unsigned long totalMem;
  unsigned long freeMem;
  unsigned long uptimeTicks;
  char sysName[64];
  char boardName[64];
  char version[32];
  InterfaceInfo iface[8];
  int ifaceCount;
  bool connected;
};

// ==================== KELAS SNMP CLIENT ====================
class SNMPClient {
private:
  WiFiUDP udp;
  IPAddress routerIP;
  String community;
  int port;

  // ---- Async request state ----
  uint8_t _req[256];
  int _reqLen = 0;
  uint8_t _resp[350];
  int _respLen = 0;
  bool _pending = false;
  unsigned long _pendStart = 0;
  int _step = -2;      // -2 = idle, 0..6 = sistem, 7+ = interface
  int _ifIdx = 1;      // indeks OID interface (1..8)
  int _ifSub = 0;      // 0=name 1=status 2=rx 3=tx
  unsigned long _fetchStart = 0;
  char _currentOID[48]; // OID yang sedang di-request untuk decode

  // ==================== Private Methods ====================

  int encodeOID(const char* oid, uint8_t* out) {
    int parts[16], pc = 0;
    const char* p = oid;
    while (*p && pc < 16) {
      parts[pc++] = atoi(p);
      while (*p && *p != '.') p++;
      if (*p == '.') p++;
    }
    int pos = 0;
    out[pos++] = parts[0] * 40 + parts[1];
    for (int i = 2; i < pc; i++) {
      int v = parts[i];
      if (v < 128) {
        out[pos++] = v;
      } else {
        uint8_t t[8]; int ti = 0;
        t[ti++] = v & 0x7F; v >>= 7;
        while (v > 0) { t[ti++] = (v & 0x7F) | 0x80; v >>= 7; }
        for (int j = ti - 1; j >= 0; j--) out[pos++] = t[j];
      }
    }
    return pos;
  }

  int buildGetRequest(uint8_t* buf, const char* oid) {
    uint8_t oidBytes[32];
    int oidLen = encodeOID(oid, oidBytes);
    int pos = 0;
    buf[pos++] = 0x30;
    int seqP = pos++;
    buf[pos++] = 0x02; buf[pos++] = 0x01; buf[pos++] = 0x01;
    int cl = community.length();
    buf[pos++] = 0x04; buf[pos++] = cl;
    memcpy(buf + pos, community.c_str(), cl);
    pos += cl;
    buf[pos++] = 0xA0;
    int pduP = pos++;
    buf[pos++] = 0x02; buf[pos++] = 0x04;
    static uint32_t rid = 1;
    buf[pos++] = (rid >> 24) & 0xFF;
    buf[pos++] = (rid >> 16) & 0xFF;
    buf[pos++] = (rid >> 8) & 0xFF;
    buf[pos++] = rid & 0xFF;
    rid++;
    buf[pos++] = 0x02; buf[pos++] = 0x01; buf[pos++] = 0x00;
    buf[pos++] = 0x02; buf[pos++] = 0x01; buf[pos++] = 0x00;
    buf[pos++] = 0x30;
    int vbP = pos++;
    buf[pos++] = 0x30;
    int bnP = pos++;
    buf[pos++] = 0x06;
    buf[pos++] = oidLen;
    memcpy(buf + pos, oidBytes, oidLen);
    pos += oidLen;
    buf[pos++] = 0x05; buf[pos++] = 0x00;
    buf[bnP] = 2 + oidLen + 2;
    buf[vbP] = 2 + buf[bnP];
    buf[pduP] = pos - pduP - 1;
    buf[seqP] = pos - seqP - 1;
    return pos;
  }

  bool _send(const char* oid) {
    strncpy(_currentOID, oid, sizeof(_currentOID) - 1);
    _currentOID[sizeof(_currentOID) - 1] = '\0';
    _reqLen = buildGetRequest(_req, oid);
    Serial.printf("[SNMP] Sending to %s:%d, %d bytes\n", routerIP.toString().c_str(), port, _reqLen);
    udp.beginPacket(routerIP, port);
    udp.write(_req, _reqLen);
    bool ok = udp.endPacket();
    Serial.printf("[SNMP] Send %s\n", ok ? "OK" : "FAIL");
    _pending = true;
    _pendStart = millis();
    return ok;
  }

  // 0 = masih menunggu, 1 = selesai (data atau timeout)
  int _poll() {
    if (!_pending) return 1;
    int avail = udp.parsePacket();
    if (avail > 0) {
      _respLen = udp.read(_resp, sizeof(_resp));
      _pending = false;
      Serial.printf("[SNMP] Got response: %d bytes\n", _respLen);
      return 1;  // success
    }
    if (millis() - _pendStart > 800) {
      _pending = false;
      _respLen = 0;
      return -1;  // timeout
    }
    return 0;  // still waiting
  }

  // ==================== Proper TLV Parser for SNMP Response ====================
  // Parse single TLV at offset. Returns true on success.
  // Sets tag, len (value length), valPtr (points to value data).
  // Does NOT advance offset.
  bool _parseTLV(int offset, uint8_t& tag, int& len, const uint8_t*& valPtr) {
    if (offset + 1 >= _respLen) return false;
    tag = _resp[offset];
    int l = _resp[offset + 1];
    int hdr = 2;
    if (l & 0x80) {
      int n = l & 0x7F;
      if (offset + 2 + n > _respLen) return false;
      l = 0;
      for (int i = 0; i < n; i++) l = (l << 8) | _resp[offset + 2 + i];
      // hdr = 2 + n; // not needed, we just need value length
    }
    if (offset + 2 + l > _respLen) return false; // value length check (simplified for short form)
    // Actually we need to handle long form properly for the length check
    // For simplicity, assume short form (l < 128) which is true for our small responses
    valPtr = _resp + offset + 2;
    return true;
  }

  // Skip one TLV at offset, return new offset (or -1 on error)
  int _nextTLV(int offset) {
    if (offset + 1 >= _respLen) return -1;
    int l = _resp[offset + 1];
    int hdr = 2;
    if (l & 0x80) {
      int n = l & 0x7F;
      if (offset + 2 + n > _respLen) return -1;
      hdr += n;
    }
    int valLen = _resp[offset + 1];
    if (valLen & 0x80) return -1; // long form not expected for value length in our responses
    return offset + 2 + l;
  }

  // Parse SNMP GET-RESPONSE and extract value for current OID
bool _parseResponse(int expectedTag, void* outVal, bool isString) {
    if (_respLen < 10) return false;
    Serial.printf("[SNMP] Parse: len=%d tag=%d\n", _respLen, expectedTag);
    int off = 0;
    uint8_t tag; int len; const uint8_t* valPtr;

    // 1. Outer SEQUENCE (0x30)
    if (!_parseTLV(0, tag, len, valPtr) || tag != 0x30) return false;
    off = 2;
    if (_resp[1] & 0x80) return false; // long form not expected for outer len

    // Inside outer SEQUENCE:
    // 2. Version (INTEGER 0x02)
    if (off + 1 >= _respLen) return false;
    if (_resp[off] != 0x02) return false;
    int l = _resp[off + 1];
    if (l & 0x80) return false;
    off += 2 + l;

    // 3. Community (OCTET STRING 0x04)
    if (off + 1 >= _respLen) return false;
    if (_resp[off] != 0x04) return false;
    l = _resp[off + 1];
    if (l & 0x80) return false;
    off += 2 + l;

    // 4. PDU (GET-RESPONSE 0xA2)
    if (off + 1 >= _respLen) return false;
    if (_resp[off] != 0xA2) return false;
    int pduLen = _resp[off + 1];
    if (pduLen & 0x80) return false;
    int pduStart = off + 2;
    int pduEnd = pduStart + pduLen;

    int off2 = pduStart;

    // 5. request-id (INTEGER)
    if (off2 + 1 >= _respLen) return false;
    if (_resp[off2] != 0x02) return false;
    int l2 = _resp[off2 + 1];
    if (l2 & 0x80) return false;
    off2 += 2 + l2;

    // 6. error-status (INTEGER)
    if (off2 + 1 >= _respLen) return false;
    if (_resp[off2] != 0x02) return false;
    l2 = _resp[off2 + 1];
    if (l2 & 0x80) return false;
    off2 += 2 + l2;

    // 7. error-index (INTEGER)
    if (off2 + 1 >= _respLen) return false;
    if (_resp[off2] != 0x02) return false;
    l2 = _resp[off2 + 1];
    if (l2 & 0x80) return false;
    off2 += 2 + l2;

    // 8. varbinds SEQUENCE (0x30)
    if (off2 + 1 >= _respLen) return false;
    if (_resp[off2] != 0x30) return false;
    int vbLen = _resp[off2 + 1];
    int vbStart = off2 + 2;
    int vbEnd = vbStart + vbLen;

    int off3 = vbStart;

    // 9. varbind SEQUENCE (0x30)
    if (off3 + 1 >= _respLen) return false;
    if (_resp[off3] != 0x30) return false;
    int vbindLen = _resp[off3 + 1];
    int vbindStart = off3 + 2;
    int vbindEnd = vbindStart + vbindLen;

    int off4 = vbindStart;

    // 9. OID (0x06)
    if (off4 + 1 >= vbindEnd) return false;
    if (_resp[off4] != 0x06) return false;
    int l3 = _resp[off4 + 1];
    if (l3 & 0x80) return false;
    // Verify OID matches _currentOID (optional, skip for speed)
    off4 += 2 + l3;

    // VALUE (next TLV) - THIS IS WHAT WE WANT!
    if (off4 + 1 >= vbindEnd) return false;
    uint8_t valTag = _resp[off4];
    int valLen = _resp[off4 + 1];
    if (valLen & 0x80) return false; // long form not expected
    valPtr = _resp + off4 + 2;

    // Check tag matches expected
    if (valTag != (uint8_t)expectedTag) {
      Serial.printf("[SNMP] Tag mismatch: got 0x%02x expected 0x%02x\n", valTag, expectedTag);
      return false;
    }

    // Extract value
    if (isString) {
      if (expectedTag != 0x04) return false;
      int cp = min(valLen, 63);
      memcpy(outVal, _resp + off4 + 2, cp);
      ((char*)outVal)[cp] = '\0';
    } else {
      unsigned long val = 0;
      for (int j = 0; j < valLen; j++) val = (val << 8) | _resp[off4 + 2 + j];
      *(unsigned long*)outVal = val;
    }
    return true;
  }

  bool _decodeInteger(int* val) {
    if (_respLen <= 0) return false;
    unsigned long v = 0;
    if (!_parseResponse(0x02, &v, false)) return false;
    *val = (int)v;
    return true;
  }

  bool _decodeCounter(unsigned long* val) {
    if (_respLen <= 0) return false;
    // Counter (0x41), Gauge (0x42), TimeTicks (0x43)
    return _parseResponse(0x41, val, false) || _parseResponse(0x42, val, false) || _parseResponse(0x43, val, false);
  }

  // Ambil OCTET STRING value
  bool _decodeString(char* out, int maxLen) {
    if (_respLen <= 0) return false;
    out[0] = '\0';
    return _parseResponse(0x04, out, true);
  }

  void _finishFetch() {
    _step = -2;
    data.connected = true;
    unsigned long elapsed = millis() - _fetchStart;
    Serial.printf("[SNMP] OK %lu ms CPU:%d%% Ifaces:%d\n",
      elapsed, data.cpuLoad, data.ifaceCount);
  }

  void _advanceSystemStep() {
    _step++;
    if (_step == 7) {
      _ifIdx = 5; _ifSub = 0;
      _sendInterfaceStep();
      return;
    }
    switch (_step) { // OID untuk langkah berikutnya
      case 1: _send(OID_SYS_UPTIME); break;
      case 2: _send(OID_MK_CPU_LOAD); break;
      case 3: _send(OID_MK_TOTAL_MEM); break;
      case 4: _send(OID_MK_FREE_MEM); break;
      case 5: _send(OID_MK_BOARD_NAME); break;
      case 6: _send(OID_MK_VERSION); break;
    }
  }

  void _sendInterfaceStep() {
    if (_ifIdx > 12) { _finishFetch(); return; }
    switch (_ifSub) {
      case 0: sprintf(_currentOID, "%s.%d", OID_IF_DESCR, _ifIdx); break;
      case 1: sprintf(_currentOID, "%s.%d", OID_IF_STATUS, _ifIdx); break;
      case 2: sprintf(_currentOID, "%s.%d", OID_IF_IN_OCTETS, _ifIdx); break;
      default: sprintf(_currentOID, "%s.%d", OID_IF_OUT_OCTETS, _ifIdx); break;
    }
    _send(_currentOID);
  }

public:
  SNMPData data;

  bool isFetching() { return _step >= -1; }

  void begin(String ip, int snmpPort, String comm) {
    routerIP.fromString(ip);
    port = snmpPort;
    community = comm;
    udp.begin(161);  // Bind to fixed local port for NAT traversal
    memset(&data, 0, sizeof(data));
    data.connected = false;
    _step = -2;
    Serial.printf("[SNMP] Init: %s:%d community=%s\n",
      ip.c_str(), snmpPort, comm.c_str());
  }

  void updateConfig(String ip, int snmpPort, String comm) {
    routerIP.fromString(ip);
    port = snmpPort;
    community = comm;
    data.connected = false;
  }

  void startFetch() {
    if (WiFi.status() != WL_CONNECTED) {
      data.connected = false;
      _step = -2;
      return;
    }
    memset(&data, 0, sizeof(data));
    _step = 0;
    _ifIdx = 5;
    _ifSub = 0;
    _pending = false;
    _respLen = 0;
    _fetchStart = millis();
    _send(OID_SYS_NAME);
  }

  // Panggil tiap loop(). Return true saat selesai (atau idle).
  bool pollFetch() {
    if (_step < 0) return true;
    int pollResult = _poll();
    if (pollResult == 0) return false;
    if (pollResult < 0) {
      Serial.println("[SNMP] Request timeout");
      _advanceSystemStep();
      return false;
    }

    if (_step <= 6) {
      // Proses respon sistem yang baru
      switch (_step) {
        case 0: _decodeString(data.sysName, sizeof(data.sysName)); Serial.printf("[SNMP] sysName=%s\n", data.sysName); break;
        case 1: _decodeCounter(&data.uptimeTicks); Serial.printf("[SNMP] uptime=%lu\n", data.uptimeTicks); break;
        case 2: { int c = 0; if (_decodeInteger(&c)) { data.cpuLoad = c; Serial.printf("[SNMP] cpuLoad=%d\n", data.cpuLoad); } else { Serial.println("[SNMP] cpuLoad decode FAIL"); } break; }
        case 3: _decodeCounter(&data.totalMem); Serial.printf("[SNMP] totalMem=%lu\n", data.totalMem); break;
        case 4: _decodeCounter(&data.freeMem); Serial.printf("[SNMP] freeMem=%lu\n", data.freeMem); break;
        case 5: _decodeString(data.boardName, sizeof(data.boardName)); Serial.printf("[SNMP] board=%s\n", data.boardName); break;
        case 6: _decodeString(data.version, sizeof(data.version)); Serial.printf("[SNMP] version=%s\n", data.version); break;
      }
      _advanceSystemStep();
      return false;
    }

    // Interface step - support indices 5-12, stop after 8 valid interfaces
    if (data.ifaceCount < 8 && _ifIdx <= 12) {
      InterfaceInfo& f = data.iface[data.ifaceCount];
      if (_ifSub == 0) {
        char name[32];
        bool got = _decodeString(name, sizeof(name));
        Serial.printf("[SNMP] ifIdx=%d name='%s' got=%d\n", _ifIdx, name, got);
        if (!got || strlen(name) == 0) {
          _ifIdx++;
          _ifSub = 0;
          _sendInterfaceStep();
          return false;
        }
        strncpy(f.name, name, 31);
        f.name[31] = '\0';
        f.rxBytes = 0; f.txBytes = 0; f.status = 0; f.valid = true;
        _ifSub = 1;
      } else if (_ifSub == 1) {
        int s = 0;
        if (_decodeInteger(&s)) f.status = s;
        _ifSub = 2;
      } else if (_ifSub == 2) {
        unsigned long v = 0;
        if (_decodeCounter(&v)) f.rxBytes = v;
        _ifSub = 3;
      } else {
        unsigned long v = 0;
        if (_decodeCounter(&v)) f.txBytes = v;
        data.ifaceCount++;
        _ifIdx++;
        _ifSub = 0;
      }
    } else {
      _finishFetch();
      return true;
    }
    _sendInterfaceStep();
    return false;
  }

  String getUptime() {
    unsigned long sec = data.uptimeTicks / 100;
    unsigned long d = sec / 86400;
    unsigned long h = (sec % 86400) / 3600;
    unsigned long m = (sec % 3600) / 60;
    if (d > 0) return String(d) + "d " + String(h) + "h " + String(m) + "m";
    return String(h) + "h " + String(m) + "m";
  }

  float getMemPercent() {
    if (data.totalMem == 0) return 0;
    return ((float)(data.totalMem - data.freeMem) / data.totalMem) * 100.0;
  }

  static String fmtBytes(unsigned long b) {
    if (b < 1024) return String(b) + " B";
    if (b < 1048576) return String(b / 1024.0, 1) + " KB";
    if (b < 1073741824UL) return String(b / 1048576.0, 1) + " MB";
    return String(b / 1073741824.0, 2) + " GB";
  }
};

#endif