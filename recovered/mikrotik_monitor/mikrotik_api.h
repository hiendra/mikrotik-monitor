// ============================================================
// mikrotik_api.h - MikroTik RouterOS API Client (TCP port 8728)
// ============================================================
// Uses MikroTik's native API protocol over TCP (port 8728)
// No ArduinoJson dependency - manual parsing for low memory
// ============================================================

#ifndef MIKROTIK_API_H
#define MIKROTIK_API_H

#include <WiFi.h>
#include <WiFiClient.h>

#ifndef MT_API_PORT   // default dari config.h; runtime pakai storage.current.apiPort
#define MT_API_PORT 8728
#endif
#define MAX_IFACES 80
#define MAX_PPP 80

struct MTInterface {
  char name[32];
  unsigned long long rxBytes;
  unsigned long long txBytes;
  bool running;
  bool disabled;
};

struct MTPPPUser {
  char name[32];
  char uptime[24];   // mentah "1w2d3h..." dari /ppp/active
  int ifIdx;         // index interface <nama> yg cocok (-1 bila tak ada)
};

struct MTSystemData {
  char version[32];
  char boardName[64];
  unsigned long uptime;
  int cpuLoad;
  unsigned long totalMem;
  unsigned long freeMem;
  MTInterface interfaces[MAX_IFACES];
  int ifaceCount;
  float temp;
  float voltage;
  int activeUsers;
  MTPPPUser pppUsers[MAX_PPP];
  int pppCount;
};

class MikroTikAPI {
private:
  WiFiClient _client;
  String _host;
  int _port;
  String _user;
  String _pass;
  bool _connected = false;

  // Send a word (length-prefixed string) per MikroTik API protocol
  bool _writeWord(const String& word) {
    if (!_client.connected()) return false;
    size_t len = word.length();   // size_t: uint8_t memotong word >255 byte (cabang 3/4-byte jadi dead code)
    if (len < 0x80) {
      _client.write((uint8_t)len);
    } else if (len < 0x4000) {
      _client.write(0x80 | (len >> 8));
      _client.write(len & 0xFF);
    } else if (len < 0x200000) {
      _client.write(0xC0 | (len >> 16));
      _client.write((len >> 8) & 0xFF);
      _client.write(len & 0xFF);
    } else {
      _client.write(0xE0 | (len >> 24));
      _client.write((len >> 16) & 0xFF);
      _client.write((len >> 8) & 0xFF);
      _client.write(len & 0xFF);
    }
    _client.write(word.c_str(), len);
    return _client.connected();
  }

  // Read a single byte with timeout
  int _readByte(uint32_t timeout = 5000) {
    uint32_t start = millis();
    while (_client.available() == 0) {
      if (millis() - start > timeout) return -1;
      delay(1);
    }
    return _client.read();
  }

  // Read a word (length-prefixed string)
  // Buang `count` byte dari socket tanpa disimpan, supaya stream tetap sinkron
  // ketika word lebih panjang dari buffer simpan.
  bool _drain(int count, uint32_t deadline, uint32_t timeout) {
    char sink[64];
    while (count > 0) {
      while (_client.available() == 0) {
        if (millis() - deadline > timeout) return false;
        delay(1);
      }
      int c = _client.available();
      if (c > count) c = count;
      if (c > (int)sizeof(sink)) c = (int)sizeof(sink);
      int n = _client.readBytes((uint8_t*)sink, c);
      if (n <= 0) return false;
      count -= n;
    }
    return true;
  }

  bool _readWord(String& out, uint32_t timeout = 5000) {
    if (!_client.connected()) return false;
    int first = _readByte(timeout);
    if (first < 0) return false;
    
    int len = 0;
    if (first < 0x80) {
      len = first;
    } else if (first < 0xC0) {
      int b2 = _readByte();
      if (b2 < 0) return false;
      len = ((first & 0x3F) << 8) | b2;
    } else if (first < 0xE0) {
      int b2 = _readByte(), b3 = _readByte();
      if (b2 < 0 || b3 < 0) return false;
      len = ((first & 0x1F) << 16) | (b2 << 8) | b3;
    } else {
      int b2 = _readByte(), b3 = _readByte(), b4 = _readByte();
      if (b2 < 0 || b3 < 0 || b4 < 0) return false;
      len = ((first & 0x0F) << 24) | (b2 << 16) | (b3 << 8) | b4;
    }
    
    if (len == 0) { out = ""; return true; }
    // RouterOS bisa mengirim word > 255 byte. Seluruh word tetap DIBACA agar
    // stream tidak desync; hanya 255 byte pertama yang disimpan.
    const int KEEP_MAX = 255;
    int keep = len < KEEP_MAX ? len : KEEP_MAX;
    
    uint32_t start = millis();
    while (_client.available() < keep) {
      if (millis() - start > timeout) return false;
      delay(1);
    }
    char buf[KEEP_MAX + 1];
    int read = _client.readBytes((uint8_t*)buf, keep);
    if (read < keep) return false;
    buf[read] = '\0';
    if (len > keep) {
      if (!_drain(len - keep, start, timeout)) return false;   // jaga sinkronisasi stream
    }
    out = String(buf);
    return true;
  }

  // Send a command sentence (list of words ending with empty word)
  bool _sendSentence(const String words[], int count) {
    for (int i = 0; i < count; i++) {
      if (!_writeWord(words[i])) return false;
    }
    return _writeWord("");  // empty word terminates sentence
  }

  // Read a response sentence (list of words ending with empty word)
  bool _readSentence(String words[], int& count, int maxWords) {
    count = 0;
    while (count < maxWords) {
      String word;
      if (!_readWord(word)) return false;
      if (word.length() == 0) return true;  // empty word = end of sentence
      words[count++] = word;
    }
    return true;
  }

  // Parse attributes from response words
  // Parse uptime RouterOS "1w5d23h10m50s" -> detik
static unsigned long parseUptime(const String& v) {
  unsigned long total = 0, cur = 0;
  for (unsigned int i = 0; i < v.length(); i++) {
    char c = v[i];
    if (c >= '0' && c <= '9') { cur = cur * 10 + (c - '0'); }
    else {
      switch (c) {
        case 'w': total += cur * 604800UL; break;
        case 'd': total += cur * 86400UL; break;
        case 'h': total += cur * 3600UL; break;
        case 'm': total += cur * 60UL; break;
        case 's': total += cur; break;
      }
      cur = 0;
    }
  }
  return total;
}

  bool _parseAttrs(const String words[], int count, 
                   int& cpuLoad, unsigned long& totalMem, unsigned long& freeMem,
                   unsigned long& uptime, char* boardName, char* version) {
    for (int i = 0; i < count; i++) {
      const String& w = words[i];
      if (w.startsWith("=")) {
        int eq = w.indexOf('=', 1);
        if (eq > 0) {
          String key = w.substring(1, eq);
          String val = w.substring(eq + 1);
          
          if (key == "cpu-load") cpuLoad = val.toInt();
          else if (key == "total-memory") totalMem = val.toInt();
          else if (key == "free-memory") freeMem = val.toInt();
          else if (key == "uptime") uptime = parseUptime(val);
          else if (key == "board-name") { val.toCharArray(boardName, 64); }
          else if (key == "version") { val.toCharArray(version, 32); }
        }
      }
    }
    return true;
  }

  // Parse interface attributes
  bool _parseIface(const String words[], int count, MTInterface& iface) {
    for (int i = 0; i < count; i++) {
      const String& w = words[i];
      if (w.startsWith("=")) {
        int eq = w.indexOf('=', 1);
        if (eq > 0) {
          String key = w.substring(1, eq);
          String val = w.substring(eq + 1);
          if (key == "name") val.toCharArray(iface.name, 32);
          else if (key == "rx-byte") iface.rxBytes = strtoull(val.c_str(), NULL, 10);
          else if (key == "tx-byte") iface.txBytes = strtoull(val.c_str(), NULL, 10);
          else if (key == "running") iface.running = (val == "true");
          else if (key == "disabled") iface.disabled = (val == "true");
        }
      }
    }
    return true;
  }

public:
  MikroTikAPI() {}

  bool connect(String host, int port, String user, String pass, uint32_t timeoutMs = 2500) {
    _host = host;
    _port = port;
    _user = user;
    _pass = pass;
    
    if (!_client.connect(_host.c_str(), _port, timeoutMs)) {
      Serial.printf("[API] Connect failed to %s:%d\n", _host.c_str(), _port);
      return false;
    }
    Serial.printf("[API] Connected to %s:%d\n", _host.c_str(), _port);

    // Login
    String words[3] = {"/login", "=name=" + _user, "=password=" + _pass};
    if (!_sendSentence(words, 3)) {
      _client.stop();
      return false;
    }
    
    String resp[10];
    int count;
    if (!_readSentence(resp, count, 10)) {
      _client.stop();
      return false;
    }
    
    if (count > 0 && resp[0] == "!done") {
      _connected = true;
      Serial.println("[API] Login successful");
      return true;
    } else if (count > 0 && resp[0] == "!trap") {
      Serial.printf("[API] Login failed: %s\n", resp[1].c_str());
      _client.stop();
      return false;
    }
    _client.stop();
    return false;
  }

  bool isConnected() { return _connected && _client.connected(); }

  // Tutup koneksi (mis. setelah port diubah dari Settings) supaya loop
  // reconnect otomatis memakai port baru.
  void disconnect() { _client.stop(); _connected = false; }

  // Fetch system resource info
  bool getSystemResource(MTSystemData& data) {
    if (!_connected) return false;
    String words[2] = {"/system/resource/print", "=.proplist=cpu-load,total-memory,free-memory,uptime,board-name,version"};
    if (!_sendSentence(words, 2)) return false;

    String resp[20];
    int count;
    while (_readSentence(resp, count, 20)) {
      if (count > 0 && resp[0] == "!re") {
        _parseAttrs(resp, count, data.cpuLoad, data.totalMem, data.freeMem, 
                    data.uptime, data.boardName, data.version);
      } else if (count > 0 && resp[0] == "!done") {
        break;
      } else if (count > 0 && resp[0] == "!trap") {
        return false;
      }
    }
    return true;
  }

  // Fetch interfaces
  bool getInterfaces(MTSystemData& data) {
    if (!_connected) return false;
    String words[2] = {"/interface/print", "=.proplist=name,rx-byte,tx-byte,running,disabled"};
    if (!_sendSentence(words, 2)) return false;

    String resp[30];
    int count;
    data.ifaceCount = 0;

    while (_readSentence(resp, count, 30)) {
      if (count > 0 && resp[0] == "!re") {
        if (data.ifaceCount < MAX_IFACES) {
          MTInterface& f = data.interfaces[data.ifaceCount];
          _parseIface(resp, count, f);
          if (strlen(f.name) > 0) data.ifaceCount++;
        }
      } else if (count > 0 && resp[0] == "!done") {
        break;
      } else if (count > 0 && resp[0] == "!trap") {
        return false;
      }
    }
    return true;
  }

  // Fetch system health (temperature, voltage)
  bool getHealth(MTSystemData& data) {
    if (!_connected) return false;
    String words[2] = {"/system/health/print", "=detail="};
    if (!_sendSentence(words, 2)) return false;

    String resp[20];
    int count;
    bool found = false;
    while (_readSentence(resp, count, 20)) {
      if (count > 0 && resp[0] == "!trap") {
        // tiriskan sisa respon (!done) sampai tuntas
        while (_readSentence(resp, count, 20)) {
          if (count > 0 && resp[0] == "!done") break;
        }
        // RouterOS lama menolak "=detail=", coba tanpa parameter
        String words2[1] = {"/system/health/print"};
        if (!_sendSentence(words2, 1)) return false;
        while (_readSentence(resp, count, 20)) {
          if (count > 0 && resp[0] == "!trap") return false;
          if (count > 0 && resp[0] == "!re") {
            found = true;
            parseHealthRow(resp, count, data);
          } else if (count > 0 && resp[0] == "!done") break;
        }
        break;
      }
      if (count > 0 && resp[0] == "!re") {
        found = true;
        parseHealthRow(resp, count, data);
      } else if (count > 0 && resp[0] == "!done") {
        break;
      }
    }
    return found || data.temp > 0 || data.voltage > 0;
  }

  void parseHealthRow(const String resp[], int count, MTSystemData& data) {
    // Format name=pair: =name=system-temp=40=type=C  (old)
    // atau nama atribut langsung: =temperature=40 =voltage=47.5
    if (count <= 4) {
      // old style: satu baris per sensor, .id/name/value/type
      String nm, vv;
      for (int i = 1; i < count; i++) {
        const String& w = resp[i];
        if (w.startsWith("=name=")) nm = w.substring(6);
        else if (w.startsWith("=value=")) vv = w.substring(7);
      }
      if (nm.length() && vv.length()) {
        if (nm.indexOf("temp") >= 0) data.temp = vv.toFloat();
        else if (nm.indexOf("volt") >= 0) data.voltage = vv.toFloat();
      }
    } else {
      // new style: banyak atribut dalam satu baris
      for (int i = 1; i < count; i++) {
        const String& w = resp[i];
        if (!w.startsWith("=")) continue;
        int eq = w.indexOf('=', 1);
        if (eq < 0) continue;
        String key = w.substring(1, eq);
        String val = w.substring(eq + 1);
        if (key == "temperature") data.temp = val.toFloat();
        else if (key == "voltage") data.voltage = val.toFloat();
        else if (key == "board-temperature") data.temp = val.toFloat();
        else if (key == "board-voltage") data.voltage = val.toFloat();
        else if (key == "cpu-temperature") data.temp = val.toFloat();
        else if (key == "cpu-voltage") data.voltage = val.toFloat();
      }
    }
  }

  // Count active PPPoE sessions (/ppp/active)
  bool getActiveUsers(MTSystemData& data) {
    if (!_connected) return false;
    String words[2] = {"/ppp/active/print", "=count-only="};
    if (!_sendSentence(words, 2)) return false;

    String resp[20];
    int count;
    bool ok = false;
    data.activeUsers = 0;
    while (_readSentence(resp, count, 20)) {
      if (count > 0 && resp[0] == "!re") {
        for (int i = 1; i < count; i++) {
          const String& w = resp[i];
          if (w.startsWith("=ret=")) {
            data.activeUsers = w.substring(5).toInt();
            ok = true;
          }
        }
      } else if (count > 0 && resp[0] == "!trap") {
        return false;
      } else if (count > 0 && resp[0] == "!done") {
        for (int i = 1; i < count; i++) {
          const String& w = resp[i];
          if (w.startsWith("=ret=")) {
            data.activeUsers = w.substring(5).toInt();
            ok = true;
          }
        }
        break;
      }
    }
    return ok;
  }

  // Daftar sesi PPP aktif (/ppp/active) + cocokkan ke interface <nama>
  bool getPPPActive(MTSystemData& data) {
    if (!_connected) return false;
    String words[2] = {"/ppp/active/print", "=.proplist=name,uptime"};
    if (!_sendSentence(words, 2)) return false;

    String resp[20];
    int count;
    data.pppCount = 0;
    while (_readSentence(resp, count, 20)) {
      if (count > 0 && resp[0] == "!re") {
        if (data.pppCount < MAX_PPP) {
          MTPPPUser& u = data.pppUsers[data.pppCount];
          u.name[0] = '\0'; u.uptime[0] = '\0'; u.ifIdx = -1;
          for (int i = 1; i < count; i++) {
            const String& w = resp[i];
            if (!w.startsWith("=")) continue;
            int eq = w.indexOf('=', 1);
            if (eq < 0) continue;
            String key = w.substring(1, eq);
            String val = w.substring(eq + 1);
            if (key == "name") val.toCharArray(u.name, 32);
            else if (key == "uptime") val.toCharArray(u.uptime, 24);
          }
          if (strlen(u.name) > 0) {
            // Cocokkan ke interface dinamis PPP. RouterOS menamainya
            // "<user>" untuk PPP client, tapi "<pppoe-user>" untuk PPPoE
            // server — jadi dicocokkan dgn pola bracket + mengandung nama user.
            for (int k = 0; k < data.ifaceCount; k++) {
              String nm = String(data.interfaces[k].name);
              if (nm.length() < 3 || nm[0] != '<' || nm[nm.length() - 1] != '>') continue;
              if (nm.indexOf(u.name) >= 0) { u.ifIdx = k; break; }
            }
            // Fallback: nama interface sama persis dgn nama user
            if (u.ifIdx < 0) {
              for (int k = 0; k < data.ifaceCount; k++) {
                if (strcmp(data.interfaces[k].name, u.name) == 0) { u.ifIdx = k; break; }
              }
            }
            data.pppCount++;
          }
        }
      } else if (count > 0 && resp[0] == "!trap") {
        return false;
      } else if (count > 0 && resp[0] == "!done") {
        break;
      }
    }
    // Jangan timpa hasil =count-only= dari getActiveUsers(): pppCount dibatasi MAX_PPP (80),
    // sehingga jumlah user > 80 akan salah tampil. Dipakai hanya sebagai fallback bila kosong.
    if (data.activeUsers <= 0) data.activeUsers = data.pppCount;
    return true;
  }

  // Fetch all data in one go
  bool fetchAll(MTSystemData& data) {
    if (!_connected) return false;
    if (!getSystemResource(data)) return false;
    if (!getInterfaces(data)) return false;
    getHealth(data);
    getActiveUsers(data);
    getPPPActive(data);
    return true;
  }
};

#endif