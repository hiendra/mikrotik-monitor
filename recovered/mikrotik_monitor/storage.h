// ============================================================
// storage.h - Penyimpanan Konfigurasi Permanen (NVS)
// ============================================================

#ifndef STORAGE_H
#define STORAGE_H

#include <Preferences.h>

struct Settings {
  char mikrotikIP[32];
  char snmpCommunity[32];
  char wifiSSID[32];
  char wifiPass[64];
  int  snmpPort;
  int  apiPort;         // port API RouterOS (TCP), default 8728
  char mtUser[32];      // user login RouterOS API (default dari secrets.h)
  char mtPass[64];      // password login RouterOS API
  int  refreshInterval;
  bool darkMode;
  bool wifiConfigured;
  int  brightness;      // 10-100 (%)
  int  screenTimeout;   // detik, 0 = always on
  int  ledBright;       // 10-100 (%), kecerahan LED RGB
  bool chartGlow;       // efek glow neon pada garis grafik
  bool autoLock;        // kunci layar otomatis saat screen timeout habis
  char dashIface1[20];  // nama interface kartu 1 Dashboard ("" = otomatis)
  char dashIface2[20];  // nama interface kartu 2 Dashboard ("" = otomatis)
  char wifiSSIDs[5][32];   // profil WiFi tersimpan (MRU, [0] = aktif)
  char wifiPasses[5][64];
  int  wifiProfileCount;
};

class SettingsStorage {
private:
  Preferences prefs;

public:
  Settings current;

  void begin() {
    prefs.begin("mktmonitor", false);
    load();
  }

  void load() {
    strncpy(current.mikrotikIP,
      prefs.getString("ip", MIKROTIK_IP).c_str(), 31);
    current.mikrotikIP[31] = '\0';

    strncpy(current.snmpCommunity,
      prefs.getString("comm", SNMP_COMMUNITY).c_str(), 31);
    current.snmpCommunity[31] = '\0';

    strncpy(current.wifiSSID,
      prefs.getString("ssid", WIFI_SSID).c_str(), 31);
    current.wifiSSID[31] = '\0';

    strncpy(current.wifiPass,
      prefs.getString("wpass", WIFI_PASSWORD).c_str(), 63);
    current.wifiPass[63] = '\0';

    current.snmpPort = prefs.getInt("snmp_port", 161);
    current.apiPort = prefs.getInt("api_port", 8728);

    // Kredensial RouterOS API — bisa diubah dari Settings, default dari secrets.h
    strncpy(current.mtUser, prefs.getString("mtuser", MT_USER).c_str(), 31);
    current.mtUser[31] = '\0';
    strncpy(current.mtPass, prefs.getString("mtpass", MT_PASS).c_str(), 63);
    current.mtPass[63] = '\0';

    current.refreshInterval = prefs.getInt("refresh", 5);
    current.darkMode = prefs.getBool("dark", true);
    current.wifiConfigured = prefs.getBool("wconf", true);
    current.brightness = prefs.getInt("bright", 100);
    current.screenTimeout = prefs.getInt("scrto", 0);
    current.ledBright = prefs.getInt("ledbr", 100);
    current.chartGlow = prefs.getBool("glow", true);
    current.autoLock = prefs.getBool("alock", true);

    strncpy(current.dashIface1, prefs.getString("dif1", "").c_str(), 19);
    current.dashIface1[19] = '\0';
    strncpy(current.dashIface2, prefs.getString("dif2", "").c_str(), 19);
    current.dashIface2[19] = '\0';

    // Profil WiFi (maks 5, MRU)
    current.wifiProfileCount = prefs.getInt("wcount", 0);
    if (current.wifiProfileCount < 0 || current.wifiProfileCount > 5) current.wifiProfileCount = 0;
    for (int i = 0; i < 5; i++) {
      String ks = "wssid" + String(i), kp = "wpass" + String(i);
      strncpy(current.wifiSSIDs[i], prefs.getString(ks.c_str(), "").c_str(), 31);
      current.wifiSSIDs[i][31] = '\0';
      strncpy(current.wifiPasses[i], prefs.getString(kp.c_str(), "").c_str(), 63);
      current.wifiPasses[i][63] = '\0';
    }
    // Migrasi: profil kosong tapi ada SSID lama → jadikan profil[0]
    if (current.wifiProfileCount == 0 && strlen(current.wifiSSID) > 0) {
      strncpy(current.wifiSSIDs[0], current.wifiSSID, 31);
      strncpy(current.wifiPasses[0], current.wifiPass, 63);
      current.wifiProfileCount = 1;
    }
    syncLegacyWiFi();
  }

  // Samakan field lama (tampilan) dengan profil aktif [0]
  void syncLegacyWiFi() {
    if (current.wifiProfileCount > 0) {
      strncpy(current.wifiSSID, current.wifiSSIDs[0], 31);
      current.wifiSSID[31] = '\0';
      strncpy(current.wifiPass, current.wifiPasses[0], 63);
      current.wifiPass[63] = '\0';
      current.wifiConfigured = true;
    }
  }

  int findProfile(const char* ssid) {
    for (int i = 0; i < current.wifiProfileCount; i++) {
      if (strcmp(current.wifiSSIDs[i], ssid) == 0) return i;
    }
    return -1;
  }

  // Hapus satu profil WiFi tersimpan ("lupakan jaringan")
  bool removeProfile(const char* ssid) {
    int at = findProfile(ssid);
    if (at < 0) return false;              // bukan profil tersimpan
    for (int i = at; i < 4; i++) {
      strcpy(current.wifiSSIDs[i], current.wifiSSIDs[i + 1]);
      strcpy(current.wifiPasses[i], current.wifiPasses[i + 1]);
    }
    current.wifiProfileCount--;
    if (current.wifiProfileCount < 0) current.wifiProfileCount = 0;
    current.wifiSSIDs[current.wifiProfileCount][0] = '\0';
    current.wifiPasses[current.wifiProfileCount][0] = '\0';
    if (current.wifiProfileCount == 0) {
      current.wifiSSID[0] = '\0';
      current.wifiPass[0] = '\0';
      current.wifiConfigured = false;
    } else {
      syncLegacyWiFi();
    }
    save();
    return true;
  }

  void save() {
    prefs.putString("ip", current.mikrotikIP);
    prefs.putString("comm", current.snmpCommunity);
    prefs.putString("ssid", current.wifiSSID);
    prefs.putString("wpass", current.wifiPass);
    prefs.putInt("snmp_port", current.snmpPort);
    prefs.putInt("api_port", current.apiPort);
    prefs.putString("mtuser", current.mtUser);
    prefs.putString("mtpass", current.mtPass);
    prefs.putInt("refresh", current.refreshInterval);
    prefs.putBool("dark", current.darkMode);
    prefs.putBool("wconf", current.wifiConfigured);
    prefs.putInt("bright", current.brightness);
    prefs.putInt("scrto", current.screenTimeout);
    prefs.putInt("ledbr", current.ledBright);
    prefs.putBool("glow", current.chartGlow);
    prefs.putBool("alock", current.autoLock);
    prefs.putString("dif1", current.dashIface1);
    prefs.putString("dif2", current.dashIface2);
    prefs.putInt("wcount", current.wifiProfileCount);
    for (int i = 0; i < 5; i++) {
      prefs.putString(("wssid" + String(i)).c_str(), current.wifiSSIDs[i]);
      prefs.putString(("wpass" + String(i)).c_str(), current.wifiPasses[i]);
    }
  }

  bool isGarbageIP(const char* ip) {
    if (!ip || strlen(ip) == 0) return true;
    for (size_t i = 0; ip[i]; i++) {
      char c = ip[i];
      if (!(c >= '0' && c <= '9') && c != '.') return true;
    }
    return false;
  }

  void reset() {
    prefs.clear();
    load();
    // Setelah reset, wajib daftar ulang WiFi (bukan pakai SSID default)
    current.wifiConfigured = false;
    current.wifiProfileCount = 0;
    current.wifiSSIDs[0][0] = '\0';
    current.wifiSSID[0] = '\0';
    current.darkMode = true;   // tampilan default = theme gelap
    current.autoLock = true;   // kembali ke perilaku default (kunci saat timeout)
    save();
  }

  // Simpan/upsert profil WiFi (MRU: aktif selalu di [0], maks 5)
  void saveWiFi(const char* ssid, const char* pass) {
    char s[32], p[64];
    strncpy(s, ssid, 31); s[31] = '\0';
    strncpy(p, pass, 63); p[63] = '\0';
    int at = findProfile(s);
    if (at < 0) {
      // geser kanan, buang paling akhir bila penuh
      int n = current.wifiProfileCount < 5 ? current.wifiProfileCount : 4;
      for (int i = n; i > 0; i--) {
        strcpy(current.wifiSSIDs[i], current.wifiSSIDs[i - 1]);
        strcpy(current.wifiPasses[i], current.wifiPasses[i - 1]);
      }
      if (current.wifiProfileCount < 5) current.wifiProfileCount++;
    } else {
      // pindahkan ke depan
      for (int i = at; i > 0; i--) {
        strcpy(current.wifiSSIDs[i], current.wifiSSIDs[i - 1]);
        strcpy(current.wifiPasses[i], current.wifiPasses[i - 1]);
      }
    }
    strcpy(current.wifiSSIDs[0], s);
    strcpy(current.wifiPasses[0], p);
    syncLegacyWiFi();
    save();
  }
};

#endif
