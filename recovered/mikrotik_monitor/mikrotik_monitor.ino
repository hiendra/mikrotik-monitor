// ============================================================
// mikrotik_monitor.ino - MikroTik Monitor (API)
// ESP32-024 + ST7789 2.4 inch, landscape 320x240
// Layout IMG_6056: Sidebar ikon kiri + Header + statistik kiri
// + kartu interface kanan (area chart Tx biru / Rx pink)
// ============================================================

#include <WiFi.h>
#include <Preferences.h>
#include <SPI.h>
#include <TFT_eSPI.h>
#include "fonts.h"
#include "config.h"
#include "storage.h"
#include "mikrotik_api.h"
#include "touch.h"
#include "keyboard.h"
#include "icons.h"

TFT_eSPI tft;
XPT2046 touch;
MikroTikAPI mtapi;
SettingsStorage storage;
Keyboard kbd;

void drawIcon(int x, int y, const uint8_t* bitmap, uint16_t color, uint16_t bg) {
  tft.drawBitmap(x, y, bitmap, MDI_ICON_W, MDI_ICON_H, color, bg);
}

MTSystemData mtData;

int page = 0;
bool darkMode = true;
bool needRedraw = true;
bool needRefresh = true;
bool inWiFiScanMode = false;
bool wifiConnecting = false;
bool triedSaved = false;   // connect dari profil tersimpan (tanpa input pass)
bool confirmReset = false;
bool confirmScan = false;              // popup konfirmasi sebelum scan WiFi
bool confirmLock = false;              // popup konfirmasi sebelum kunci layar
bool popupBright = false;
bool popupScreen = false;
bool popupLED = false;
bool popupTheme = false;
bool popupGlow = false;
bool popupAutoLock = false;             // popup Auto Lock (ON/OFF + OK)
bool popupPPP = false;                 // popup live trafik client PPP
int pppSel = -1;                       // index user PPP yang dibuka di popup
bool screenLocked = false;             // layar terkunci (ikon gembok di header)
unsigned long lockOpened = 0;          // waktu kunci diaktifkan (masa tenggang sentuh)
bool wifiAction = false;               // popup konfirmasi Connect/Lupakan WiFi
int  wifiActIdx = -1;                  // index SSID di wifiList yang dipilih
bool wifiActSaved = false;             // SSID terpilih punya profil tersimpan
int themeSel = 0;                      // 0=Dark, 1=Light (pilihan pending di popup)
int glowSel = 0;                       // 0=ON, 1=OFF (pilihan pending di popup)
int autoLockSel = 0;                   // 0=ON, 1=OFF (pilihan pending popup Auto Lock)
int screenSel = 0;                     // indeks pilihan pending popup Screen Time
int settingsTab = 0;                   // tab SETTINGS: 0=NETWORK, 1=APPEARANCE, 2=DEVICE
bool ledR = false, ledG = false, ledB = false;
bool serverOK = false;                 // true bila fetch terakhir berhasil
unsigned long lastApiRetry = 0;        // throttle reconnect saat server down
#define API_RETRY_MS 15000UL           // coba reconnect tiap 15 dtk bila down
unsigned long lastActivity = 0;
bool screenOff = false;

// Atur kecerahan backlight (0-100%) via PWM; hormati screenOff
void applyBrightness() {
  int duty = screenOff ? 0 : map(constrain(storage.current.brightness, 10, 100), 0, 100, 0, 255);
  ledcWrite(TFT_BL, duty);
}

// LED RGB status (active LOW via PWM agar terang bisa diatur)
void applyLED() {
  int lvl = map(constrain(storage.current.ledBright, 10, 100), 0, 100, 0, 255);
  ledcWrite(LED_R, ledR ? 255 - lvl : 255);
  ledcWrite(LED_G, ledG ? 255 - lvl : 255);
  ledcWrite(LED_B, ledB ? 255 - lvl : 255);
}
void setLED(bool r, bool g, bool b) {
  ledR = r; ledG = g; ledB = b;
  applyLED();
}
// Hijau=normal, Merah=WiFi/API gagal, Biru=scan/connect, Ungu=layar mati
void updateStatusLED() {
  if (screenOff) { setLED(true, false, true); return; }   // ungu
  if (inWiFiScanMode || wifiConnecting) { setLED(false, false, true); return; }  // biru
  if (WiFi.status() != WL_CONNECTED) { setLED(true, false, false); return; }     // merah
  if (!mtapi.isConnected()) { setLED(true, false, false); return; }              // merah
  setLED(false, true, false);  // hijau
}
void updateScreenTimeout(unsigned long now) {
  if (storage.current.screenTimeout > 0 && !screenOff &&
      now - lastActivity > (unsigned long)storage.current.screenTimeout * 1000UL) {
    screenOff = true;
    // Timeout → layar ikut terkunci otomatis (bisa dimatikan di Settings → Auto Lock)
    if (storage.current.autoLock) screenLocked = true;
    applyBrightness();
  }
}
unsigned long lastRefresh = 0;
unsigned long lastTouch = 0;
unsigned long wifiConnectStart = 0;

// ==================== LAYOUT ====================
#define SIDEBAR_W   24
#define CONTENT_X   (SIDEBAR_W + 2)      // 26
#define HEADER_H    28
#define STATS_X     28
#define STATS_W     110
#define IFACE_X     142
#define IFACE_W     176                   // 142..318
#define STATS_ROW_H 34

// ==================== THEME ====================
Theme darkTheme  = {COLOR_BG, COLOR_HEADER, COLOR_CARD, COLOR_TEXT_TITLE, COLOR_TEXT_LABEL, COLOR_CARD_BORDER, COLOR_BG2};
Theme lightTheme = {0xEF7D, 0xD6BA, 0xD6BA, 0x0000, 0x630C, 0xB5B6, 0xE71C};
Theme theme;
Theme getTheme() { return darkMode ? darkTheme : lightTheme; }

#undef COLOR_BG
#undef COLOR_HEADER
#undef COLOR_CARD
#undef COLOR_CARD_BORDER
#undef COLOR_TEXT_TITLE
#undef COLOR_TEXT_LABEL
#undef COLOR_BG2
#define COLOR_BG            theme.bg
#define COLOR_HEADER        theme.header
#define COLOR_CARD          theme.card
#define COLOR_CARD_BORDER   theme.border
#define COLOR_TEXT_TITLE    theme.text
#define COLOR_TEXT_LABEL    theme.dim
#define COLOR_BG2           theme.bg2

// ==================== GRADIENT + GLASS HELPERS ====================
// Gradient vertical: warna dari atas ke bawah (topColor → bottomColor)
void fillScreenGradient(uint16_t topColor, uint16_t botColor) {
  for (int y = 0; y < SCREEN_HEIGHT; y++) {
    uint8_t r = ((topColor >> 11) & 0x1F);
    uint8_t g = ((topColor >> 5) & 0x3F);
    uint8_t b = (topColor & 0x1F);
    uint8_t r2 = ((botColor >> 11) & 0x1F);
    uint8_t g2 = ((botColor >> 5) & 0x3F);
    uint8_t b2 = (botColor & 0x1F);
    uint8_t rr = r + (int)(r2 - r) * y / SCREEN_HEIGHT;
    uint8_t gg = g + (int)(g2 - g) * y / SCREEN_HEIGHT;
    uint8_t bb = b + (int)(b2 - b) * y / SCREEN_HEIGHT;
    uint16_t c = (rr << 11) | (gg << 5) | bb;
    tft.drawFastHLine(0, y, SCREEN_WIDTH, c);
  }
}
// Kartu glass: background gelap semi-opaque + border halus + sedikit highlight di atas
void drawGlassCard(int x, int y, int w, int h) {
  tft.fillRoundRect(x, y, w, h, 4, COLOR_CARD);
  tft.drawRoundRect(x, y, w, h, 4, COLOR_CARD_BORDER);
  // Garis highlight tipis di tepi atas (glass reflection)
  tft.drawFastHLine(x + 4, y + 1, w - 8, 0x4208);  // abu sangat terang tipis
}

// ==================== PROPORTIONAL FONTS ====================
void useFont(const GFXfont* f) {
  tft.setFreeFont(f);
  tft.setTextDatum(TL_DATUM);
  tft.setTextSize(1);
}
int tw(const String& s) { return tft.textWidth(s); }
// Font GLCD 8px ringkas untuk label kecil / teks padat
void useFontTiny() {
  tft.setFreeFont(NULL);
  tft.setTextDatum(TL_DATUM);
  tft.setTextSize(1);
}
void putText(int x, int y, const String& s, uint16_t c, uint16_t bg) {
  tft.setTextColor(c, bg);
  tft.drawString(s, x, y);
}
// Teks rata kanan (x2 = ujung kanan)
void putTextR(int x2, int y, const String& s, uint16_t c, uint16_t bg) {
  tft.setTextDatum(TL_DATUM);
  putText(x2 - tw(s), y, s, c, bg);
}
// Teks rata tengah horizontal (cx = pusat)
void putTextC(int cx, int y, const String& s, uint16_t c, uint16_t bg) {
  tft.setTextDatum(TL_DATUM);
  putText(cx - tw(s) / 2, y, s, c, bg);
}

#define MAX_WIFI_LIST 12
struct WiFiNet { char ssid[33]; int32_t rssi; int32_t authType; };
WiFiNet wifiList[MAX_WIFI_LIST];
int wifiCount = 0, wifiScrollOffset = 0;

// ==================== CHART (per interface) ====================
#define CHART_IFACES 2
#define CHART_SLOTS MAX_IFACES
int chart_rx[CHART_SLOTS][CHART_MAX_POINTS] = {{0}};
int chart_tx[CHART_SLOTS][CHART_MAX_POINTS] = {{0}};
unsigned long long lastDR[CHART_SLOTS] = {0}, lastDT[CHART_SLOTS] = {0};
int chart_idx = 0;
bool chartReady = false;
unsigned long lastFetchMs = 0;
unsigned long lastIntervalMs = 5000;
int trafficIfi = -1;   // interface terpilih di halaman Traffic (-1 = auto)

// ==================== PER-INTERFACE RATE (real-time) ====================
unsigned long long prevRXAll[MAX_IFACES] = {0}, prevTXAll[MAX_IFACES] = {0};
unsigned long long rateRXbps[MAX_IFACES] = {0}, rateTXbps[MAX_IFACES] = {0};
int pppScrollOffset = 0;

// ==================== HELPERS ====================
// Format kecepatan (bps) -> "780.0M"/"2.60G"/"560"/"1.07K"
String fmtRate(unsigned long long bps) {
  if (bps == 0) return String("0");
  if (bps >= 1000000000ULL) return String(bps / 1000000000.0, 2) + "G";
  if (bps >= 1000000ULL) return String(bps / 1000000.0, 1) + "M";
  if (bps >= 1000ULL) return String(bps / 1000.0, 2) + "K";
  return String(bps);
}

uint16_t levelColor(float v, float warn, float crit) {
  if (v >= crit) return COLOR_RED;
  if (v >= warn) return COLOR_AMBER;
  return COLOR_GREEN;
}

bool nameIsSFP(const char* n) {
  String s(n);
  s.toLowerCase();
  return (s.indexOf("sfp") >= 0 || s.indexOf("xgig") >= 0 || s.indexOf("10g") >= 0);
}

// Hanya interface ethernet (skip pppoe, bridge, wlan, dsb)
bool nameIsEthernet(const char* n) {
  String s(n);
  s.toLowerCase();
  if (s.indexOf("ether") >= 0) return true;
  if (s.indexOf("sfp") >= 0) return true;
  if (s.indexOf("xgig") >= 0) return true;
  if (s.indexOf("10g") >= 0) return true;
  return false;
}

// ==================== PILIH INTERFACE DASHBOARD ====================
// Kartu grafik Dashboard bisa dipilih dari halaman INTERFACES (kotak centang),
// disimpan sebagai NAMA interface di NVS supaya tetap valid walau urutan API
// berubah. Kosong = otomatis (ethernet running pertama yang belum terpakai).
int findIfaceByName(const char* nm) {
  if (!nm || !nm[0]) return -1;
  for (int i = 0; i < mtData.ifaceCount; i++)
    if (strcmp(mtData.interfaces[i].name, nm) == 0) return i;
  return -1;
}

bool dashSelected(const char* nm) {
  if (!nm || !nm[0]) return false;
  return (strcmp(storage.current.dashIface1, nm) == 0 ||
          strcmp(storage.current.dashIface2, nm) == 0);
}

// Toggle pilihan (maks 2 kartu). Pilihan terbaru selalu menempati slot 2;
// saat penuh, pilihan terlama (slot 1) yang dibuang.
void toggleDash(const char* nm) {
  char* d1 = storage.current.dashIface1;
  char* d2 = storage.current.dashIface2;
  if (strcmp(d1, nm) == 0) {          // hapus slot 1 → slot 2 naik
    strncpy(d1, d2, 19); d1[19] = '\0';
    d2[0] = '\0';
  } else if (strcmp(d2, nm) == 0) {   // hapus slot 2
    d2[0] = '\0';
  } else if (d1[0] == '\0') {
    strncpy(d1, nm, 19); d1[19] = '\0';
  } else if (d2[0] == '\0') {
    strncpy(d2, nm, 19); d2[19] = '\0';
  } else {                            // penuh → buang pilihan terlama
    strncpy(d1, d2, 19); d1[19] = '\0';
    strncpy(d2, nm, 19); d2[19] = '\0';
  }
  storage.save();
  needRedraw = true;
}

// Index kedua kartu Dashboard (pilihan tersimpan + auto-isi sisanya)
void resolveDashIfaces(int &c0, int &c1) {
  c0 = findIfaceByName(storage.current.dashIface1);
  c1 = findIfaceByName(storage.current.dashIface2);
  for (int k = 0; k < mtData.ifaceCount; k++) {
    MTInterface& f = mtData.interfaces[k];
    if (!f.running || !nameIsEthernet(f.name)) continue;
    if (k == c0 || k == c1) continue;
    if (c0 < 0) c0 = k; else if (c1 < 0) c1 = k;
    if (c0 >= 0 && c1 >= 0) break;
  }
}

void addChartData(int ifi, unsigned long long dr, unsigned long long dt, unsigned long intervalMs) {
  double secs = (intervalMs > 0) ? (double)intervalMs / 1000.0 : 5.0;
  unsigned long long rxps = (unsigned long long)((double)dr / secs);
  unsigned long long txps = (unsigned long long)((double)dt / secs);
  chart_rx[ifi][chart_idx] = (rxps > 2147483647ULL) ? 2147483647 : (int)rxps;
  chart_tx[ifi][chart_idx] = (txps > 2147483647ULL) ? 2147483647 : (int)txps;
}

// Campur dua warna RGB565: t=0 -> c1, t=255 -> c2 (dipakai efek fade/masking)
uint16_t blend565(uint16_t c1, uint16_t c2, int t) {
  if (t < 0) t = 0;
  if (t > 255) t = 255;
  int r1 = (c1 >> 11) & 0x1F, g1 = (c1 >> 5) & 0x3F, b1 = c1 & 0x1F;
  int r2 = (c2 >> 11) & 0x1F, g2 = (c2 >> 5) & 0x3F, b2 = c2 & 0x1F;
  int r = r1 + (((r2 - r1) * t) >> 8);
  int g = g1 + (((g2 - g1) * t) >> 8);
  int b = b1 + (((b2 - b1) * t) >> 8);
  return (r << 11) | (g << 5) | b;
}

// ==================== AREA CHART (gradient fade / masking) ====================
// Isi area memudar dari warna garis (tepat di bawah kurva) ke warna kartu
// di dasar chart — gaya masking modern. Baris berwarna sama digabung jadi
// satu drawFastVLine supaya tetap cepat di SPI.
void drawAreaChart(int* data, int x, int y, int w, int h, uint16_t color, uint16_t bg, long maxv, bool glow) {
  if (maxv < 1024) maxv = 1024; // floor 1KB/s supaya trafik kecil tidak melebar penuh
  int startIdx = (chart_idx + 1) % CHART_MAX_POINTS;
  int px[CHART_MAX_POINTS], py[CHART_MAX_POINTS];
  for (int i = 0; i < CHART_MAX_POINTS; i++) {
    int idx = (startIdx + i) % CHART_MAX_POINTS;
    px[i] = x + (long)i * w / (CHART_MAX_POINTS - 1);
    py[i] = y + h - 2 - (long)((long long)data[idx] * h / maxv);  // 64-bit: cegah overflow saat rate besar
    if (py[i] < y) py[i] = y;
    if (py[i] > y + h) py[i] = y + h;
  }
  int bottom = y + h - 1;
  for (int i = 0; i < CHART_MAX_POINTS; i++) {
    int n = bottom - py[i] + 1;                       // tinggi kolom
    if (n <= 0) continue;
    uint32_t inc = (n > 1) ? (uint32_t)(256 * 255) / (n - 1) : 0;
    uint32_t t8 = 0;                                  // t terskala 0..(255<<8)
    int runY = py[i], runLen = 0;
    uint16_t runC = color;
    for (int yy = py[i]; yy <= bottom; yy++) {
      uint16_t c = blend565(color, bg, (int)(t8 >> 8));
      t8 += inc;
      if (runLen > 0 && c == runC) { runLen++; continue; }
      tft.drawFastVLine(px[i], runY, runLen, runC);
      runY = yy; runLen = 1; runC = c;
    }
    if (runLen > 0) tft.drawFastVLine(px[i], runY, runLen, runC);
  }
  // Halo/glow redup mengelilingi garis (atas & bawah) bila aktif
  if (glow) {
    const int offs[4] = {-2, -1, 1, 2};
    const int tint[4] = {200, 130, 130, 200};
    for (int p = 0; p < 4; p++) {
      uint16_t hc = blend565(color, bg, tint[p]);
      for (int i = 1; i < CHART_MAX_POINTS; i++) {
        int y1 = py[i - 1] + offs[p], y2 = py[i] + offs[p];
        if (y1 < y || y2 < y) continue;      // jangan keluar dari kartu
        tft.drawLine(px[i - 1], y1, px[i], y2, hc);
      }
    }
  }
  // Garis kurva utama di atas fade (garis tepi abu lama dihapus)
  for (int i = 1; i < CHART_MAX_POINTS; i++) {
    tft.drawLine(px[i - 1], py[i - 1], px[i], py[i], color);
  }
}

// Bulatkan max ke step rapat agar label atas mepet peak (1..10)
long long niceMax(long long v) {
  if (v < 1024) v = 1024;
  long long p = 1;
  while (p * 10 <= v) p *= 10;
  long long m = (v + p - 1) / p;  // ceil
  const long long steps[] = {1, 2, 3, 4, 5, 6, 8, 10};
  for (int i = 0; i < 8; i++) if (m <= steps[i]) return steps[i] * p;
  return 10 * p;
}
String fmtAxis(long long v) {
  if (v >= 1000000000LL) return String(v / 1000000000.0, 1) + "G";  // cegah "10000.0M" pada link 10G
  if (v >= 1000000LL) return String(v / 1000000.0, 1) + "M";
  if (v < 1000LL) return String("0");
  return String(v / 1000.0, 1) + "K";
}
String fmtMbps(unsigned long long bps) {
  return String(bps / 1000000.0, 2) + " Mbps";
}

// Gambar TX & RX dengan skala sumbu-Y yang sama supaya tinggi keduanya sebanding
// Gambar TX & RX overlay dalam satu kotak dgn skala sumbu-Y sama
// axis=true: label sumbu Y + gridline (grafik besar)
void drawAreaChartPair(int ifi, int x, int y, int w, int h, bool axis = false) {
  bool glow = storage.current.chartGlow;   // efek glow neon (toggle di Settings)
  long maxv = 1024, maxRx = 0, maxTx = 0;
  for (int i = 0; i < CHART_MAX_POINTS; i++) {
    if (chart_rx[ifi][i] > maxv) maxv = chart_rx[ifi][i];
    if (chart_tx[ifi][i] > maxv) maxv = chart_tx[ifi][i];
    if (chart_rx[ifi][i] > maxRx) maxRx = chart_rx[ifi][i];
    if (chart_tx[ifi][i] > maxTx) maxTx = chart_tx[ifi][i];
  }
  drawGlassCard(x, y, w, h);
  int px0 = x + 1, pw = w - 2;
  if (axis) {
    long long maxBits = niceMax((long long)maxv * 8);  // samakan satuan bit dg legend
    px0 = x + 42; pw = w - 46;  // ruang label kiri: cukup utk 6 karakter @GLCD 6px (mis. "100.0M")
    useFontTiny();
    for (int g = 0; g <= 4; g++) {
      int gy = y + 1 + (h - 2) - (h - 2) * g / 4;
      if (g == 0) {
        tft.drawFastHLine(px0, gy, pw, CHART_GRID_COLOR);  // baseline solid
      } else {
        // gridline halus: putus-putus (3px garis / 3px kosong)
        for (int dx = 0; dx < pw; dx += 6) {
          int seg = (pw - dx) < 3 ? (pw - dx) : 3;
          tft.drawFastHLine(px0 + dx, gy, seg, CHART_GRID_COLOR);
        }
      }
      int ly = gy - 3;                        // label tidak boleh keluar dari kartu
      if (ly < y + 1) ly = y + 1;
      if (ly > y + h - 9) ly = y + h - 9;
      putTextR(px0 - 3, ly, fmtAxis(maxBits * g / 4), COLOR_TEXT_LABEL, COLOR_CARD);
    }
  }
  // Gambar yang terbesar dulu agar yang kecil tidak tertutup
  // Fade target = warna kartu (runtime-aware: ikut tema Dark/Light)
  if (maxTx >= maxRx) {
    drawAreaChart(chart_tx[ifi], px0, y + 1, pw, h - 2, CHART_TX_COLOR, COLOR_CARD, maxv, glow);
    drawAreaChart(chart_rx[ifi], px0, y + 1, pw, h - 2, CHART_RX_COLOR, COLOR_CARD, maxv, glow);
  } else {
    drawAreaChart(chart_rx[ifi], px0, y + 1, pw, h - 2, CHART_RX_COLOR, COLOR_CARD, maxv, glow);
    drawAreaChart(chart_tx[ifi], px0, y + 1, pw, h - 2, CHART_TX_COLOR, COLOR_CARD, maxv, glow);
  }
}

// ==================== SIDEBAR ====================
void drawSidebar(int active) {
  tft.fillRect(0, 0, SIDEBAR_W, SCREEN_HEIGHT, COLOR_HEADER);
  tft.drawFastVLine(SIDEBAR_W - 1, 0, SCREEN_HEIGHT, COLOR_CARD_BORDER);
  const uint8_t* icons[6] = {ICON_HOME, ICON_LAN, ICON_WIFI, ICON_GEAR, ICON_CHART, ICON_USERS};
  for (int i = 0; i < 6; i++) {
    int y = HEADER_H + 4 + i * 35;
    bool act = (i == active);
    if (act) {
      // Neon glow: 1px highlight di tepi aktif
      tft.fillRoundRect(1, y - 1, 22, 22, 4, 0x039C);  // glow abu-cyan gelap
      tft.fillRoundRect(2, y, 20, 20, 3, COLOR_ACCENT);
    } else {
      tft.fillRoundRect(2, y, 20, 20, 3, COLOR_CARD);
      tft.drawRoundRect(2, y, 20, 20, 3, COLOR_CARD_BORDER);
    }
    drawIcon(2 + 2, y + 2, icons[i], act ? TFT_BLACK : COLOR_TEXT_LABEL, act ? COLOR_ACCENT : COLOR_CARD);
  }
}

// ==================== HEADER ====================
void drawHeader() {
  tft.fillRect(0, 0, SCREEN_WIDTH, HEADER_H, COLOR_HEADER);
  tft.drawFastHLine(0, HEADER_H - 1, SCREEN_WIDTH, COLOR_CARD_BORDER);
  // Ikon gembok di ujung kiri (samping judul) = kunci / tanda layar terkunci
  drawIcon(5, 4, screenLocked ? ICON_LOCK : ICON_UNLOCK,
           screenLocked ? COLOR_RED : COLOR_TEXT_LABEL, COLOR_HEADER);
  // Judul header miring (satu font saja → garis dasar otomatis sejajar)
  useFont(FONT_ITAL);
  putText(30, 4, "MikroTik-Monitor", COLOR_TEXT_TITLE, COLOR_HEADER);

  String up;
  uint16_t upCol = COLOR_TEXT_LABEL;
  if (WiFi.status() == WL_CONNECTED && !serverOK) {
    up = "OFFLINE"; upCol = COLOR_RED;   // WiFi ok tapi server tak terjangkau
  } else {
    struct tm t;
    if (getLocalTime(&t, 5) && t.tm_year + 1900 >= 2024) {
      char buf[6]; sprintf(buf, "%02d:%02d", t.tm_hour, t.tm_min);
      up = String(buf);
    } else if (mtData.uptime > 0) {
      unsigned long d = mtData.uptime / 86400;
      unsigned long h = (mtData.uptime % 86400) / 3600;
      up = "Up:" + String(d) + "d " + String(h) + "h";
    } else up = "Up:--";
  }
  useFont(FONT_XS);
  int upW = tw(up);
  putTextR(SCREEN_WIDTH - 8, 8, up, upCol, COLOR_HEADER);
  int rssi = WiFi.RSSI();
  uint16_t wcol = (WiFi.status() == WL_CONNECTED) ? ((rssi > -70) ? COLOR_GREEN : COLOR_AMBER) : COLOR_RED;
  drawIcon(SCREEN_WIDTH - 8 - upW - 4 - MDI_ICON_W, 6, ICON_WIFI, wcol, COLOR_HEADER);
}

// ==================== LEFT STAT ROWS ====================
void drawStatRow(int y, const char* label, const char* value, uint16_t vcol, bool bar, float pct, uint16_t bcol, const uint8_t* icon = nullptr) {
  drawGlassCard(STATS_X, y, STATS_W, STATS_ROW_H - 4);
  int lx = STATS_X + (icon ? MDI_ICON_W + 4 : 5) + 1;
  if (icon) drawIcon(STATS_X + 3, y + 6, icon, COLOR_AMBER, COLOR_CARD);
  useFontTiny();
  putText(lx, y + 4, label, COLOR_TEXT_LABEL, COLOR_CARD);
  useFontTiny();
  putTextR(STATS_X + STATS_W - 4, y + 4, value, vcol, COLOR_CARD);
  if (bar) {
    int bx = lx, bw = STATS_W - (lx - STATS_X) - 5, by = y + STATS_ROW_H - 11;
    tft.fillRoundRect(bx, by, bw, 4, 2, 0x0928);  // track gelap
    int fw = (int)(bw * constrain(pct / 100.0, 0.0, 1.0));
    if (fw > 0) tft.fillRoundRect(bx, by, fw, 4, 2, bcol);
  }
}

// ==================== INTERFACE CARD (Gambar 3) ====================
void drawIfaceCard(int ifi, int y, int h) {
  int x = IFACE_X, w = IFACE_W;
  bool ok = (ifi >= 0);
  drawGlassCard(x, y, w, h);

  if (!ok) {
    useFont(FONT_XS);
    putText(x + 8, y + 8, "Tidak ada data", COLOR_TEXT_LABEL, COLOR_CARD);
    return;
  }
  MTInterface& f = mtData.interfaces[ifi];
  bool tenG = nameIsSFP(f.name);

  // Line 1: nama + status link (semua font tiny/GLCD 8px - turun 2 angka dari 9pt)
  tft.fillCircle(x + 10, y + 8, 4, f.running ? COLOR_GREEN : COLOR_AMBER);
  useFontTiny();
  String nm = String(f.name);
  if (nm.length() > 12) nm = nm.substring(0, 12);
  putText(x + 18, y + 5, nm, COLOR_TEXT_TITLE, COLOR_CARD);
  putText(x + 18 + tw(nm) + 5, y + 5, ">", COLOR_ACCENT, COLOR_CARD);  // penanda pintasan
  String st = String(f.running ? "Link UP " : "Link DOWN ") + String(tenG ? "10G" : "1G");
  putTextR(x + w - 4, y + 5, st, f.running ? COLOR_GREEN : COLOR_AMBER, COLOR_CARD);

  // Area chart (bawah 1 baris legend) - lebih besar tanpa baris utilization
  int chartTop = y + 21;
  int chartH = h - 21 - 16;
  int chx = x + 6, chw = w - 12;
  drawAreaChartPair(ifi, chx, chartTop, chw, chartH);

  // Legend Tx (kiri) & Rx (kanan) dalam satu baris
  int ly = chartTop + chartH + 2;
  unsigned long intervalMs = lastIntervalMs > 50 ? lastIntervalMs : 5000;
  // Blok Tx di kiri
  tft.fillRect(x + 8, ly + 2, 6, 3, CHART_TX_COLOR);
  String txv = fmtRate(lastDT[ifi] * 8000ULL / intervalMs);
  useFontTiny();
  int txLabX = x + 18;
  putText(txLabX, ly + 1, "Tx", COLOR_TEXT_LABEL, COLOR_CARD);
  putText(txLabX + tw("Tx") + 4, ly + 1, txv, CHART_TX_COLOR, COLOR_CARD);
  // Blok Rx di kanan (rata kanan): [Rx] [kotak] [nilai]
  String rxv = fmtRate(lastDR[ifi] * 8000ULL / intervalMs);
  int vx = x + w - 4 - tw(rxv);
  tft.fillRect(vx - 14, ly + 2, 6, 3, CHART_RX_COLOR);
  putText(vx - 30, ly + 1, "Rx", COLOR_TEXT_LABEL, COLOR_CARD);
  putText(vx, ly + 1, rxv, CHART_RX_COLOR, COLOR_CARD);
}

// ==================== DASHBOARD (PAGE 0) ====================
void drawDashboard() {
  fillScreenGradient(COLOR_BG, COLOR_BG2);
  drawSidebar(0);
  drawHeader();

  int dy = HEADER_H + 4;
  // CPU
  drawStatRow(dy, "CPU LOAD", (String(mtData.cpuLoad) + "%").c_str(), COLOR_TEXT_TITLE, true, mtData.cpuLoad, levelColor(mtData.cpuLoad, 60, 85), ICON_CPU);
  dy += STATS_ROW_H;
  // MEM
  {
    float memPct = mtData.totalMem > 0 ? ((float)(mtData.totalMem - mtData.freeMem) / mtData.totalMem) * 100.0 : 0;
    char mv[8]; sprintf(mv, "%d%%", (int)memPct);
    drawStatRow(dy, "MEM USED", mv, COLOR_TEXT_TITLE, true, memPct, COLOR_ACCENT, ICON_MEM);
  }
  dy += STATS_ROW_H;
  // TEMP + VOLT
  {
    drawGlassCard(STATS_X, dy, STATS_W, STATS_ROW_H - 4);
    drawIcon(STATS_X + 3, dy + 6, ICON_TEMP, COLOR_AMBER, COLOR_CARD);
    drawIcon(STATS_X + 57, dy + 6, ICON_VOLT, COLOR_AMBER, COLOR_CARD);
    useFontTiny();
    putText(STATS_X + MDI_ICON_W + 5, dy + 4, "Temp", COLOR_TEXT_LABEL, COLOR_CARD);
    useFontTiny();
    putText(STATS_X + MDI_ICON_W + 5, dy + 15, mtData.temp > 0 ? (String((int)mtData.temp) + "C") : "--C", COLOR_TEXT_TITLE, COLOR_CARD);
    useFontTiny();
    putText(STATS_X + 78, dy + 4, "Volt", COLOR_TEXT_LABEL, COLOR_CARD);
    useFontTiny();
    putText(STATS_X + 78, dy + 15, mtData.voltage > 0 ? (String(mtData.voltage, 1) + "V") : "--V", COLOR_ACCENT, COLOR_CARD);
  }
  dy += STATS_ROW_H;
  // Board + ROS version (pengganti ping)
  {
    drawGlassCard(STATS_X, dy, STATS_W, STATS_ROW_H - 4);
    drawIcon(STATS_X + 3, dy + 6, ICON_ROUTER, COLOR_AMBER, COLOR_CARD);
    useFontTiny();
    putText(STATS_X + MDI_ICON_W + 6, dy + 5, "BOARD", COLOR_TEXT_LABEL, COLOR_CARD);
    String bv = String(mtData.boardName);
    if (bv.length() == 0) bv = "--";
    if (bv.length() > 14) bv = bv.substring(0, 14);
    useFontTiny();
    putText(STATS_X + MDI_ICON_W + 6, dy + 15, bv, COLOR_TEXT_TITLE, COLOR_CARD);
  }
  dy += STATS_ROW_H;
  {
    drawGlassCard(STATS_X, dy, STATS_W, STATS_ROW_H - 4);
    drawIcon(STATS_X + 3, dy + 6, ICON_SCREEN, COLOR_AMBER, COLOR_CARD);
    useFontTiny();
    putText(STATS_X + MDI_ICON_W + 6, dy + 5, "UPTIME", COLOR_TEXT_LABEL, COLOR_CARD);
    String uv = "--";
    if (mtData.uptime > 0) {
      unsigned long s = mtData.uptime;
      unsigned long w = s / 604800; s %= 604800;
      unsigned long d = s / 86400; s %= 86400;
      unsigned long h = s / 3600;
      uv = "";
      if (w > 0) uv += String(w) + "w";
      if (d > 0) uv += String(d) + "d";
      uv += String(h) + "h";
    }
    if (uv.length() > 14) uv = uv.substring(0, 14);
    useFontTiny();
    putText(STATS_X + MDI_ICON_W + 6, dy + 15, uv, COLOR_TEXT_TITLE, COLOR_CARD);
  }
  dy += STATS_ROW_H;
  // Active Users
  {
    drawGlassCard(STATS_X, dy, STATS_W, STATS_ROW_H - 4);
    drawIcon(STATS_X + 3, dy + 6, ICON_USERS, COLOR_AMBER, COLOR_CARD);
    useFontTiny();
    putText(STATS_X + MDI_ICON_W + 6, dy + 5, "USERS", COLOR_TEXT_LABEL, COLOR_CARD);
    putText(STATS_X + MDI_ICON_W + 6 + tw("USERS") + 3, dy + 5, ">", COLOR_ACCENT, COLOR_CARD);  // penanda pintasan
    char av[8];
    sprintf(av, "%d", mtData.activeUsers);
    useFont(FONT_SM);
    putTextR(STATS_X + STATS_W - 4, dy + 8, av, COLOR_TEXT_TITLE, COLOR_CARD);
  }

  // Right interface cards: dua kartu ukuran sama
  int availH = SCREEN_HEIGHT - (HEADER_H + 4);
  int cardH = (availH - 12) / 2;   // bagi 2, sisakan 12px gap antar kartu
  int usrBottom = HEADER_H + 4 + 5 * STATS_ROW_H + (STATS_ROW_H - 4); // dasar kotak USERS
  int card1Y = usrBottom - cardH;   // Ether2 sejajar dasar USERS
  int dc0, dc1;
  resolveDashIfaces(dc0, dc1);
  drawIfaceCard(dc0, HEADER_H + 4, cardH);
  drawIfaceCard(dc1, card1Y, cardH);
}

// ==================== INTERFACES (PAGE 1) ====================
// Tiap baris punya kotak centang: pilih interface mana yang tampil di kartu
// grafik Dashboard (maks 2 = jumlah kartu). Daftar > 5 baris bisa di-scroll.
#define IFACE_ROWS   5
#define IFACE_ROW_Y  50
#define IFACE_ROW_H  30
#define IFACE_PG_Y   202
#define IFACE_FOOT_Y 230

int ifaceSelOffset = 0;   // halaman daftar (kelipatan IFACE_ROWS)

int ifaceEligibleCount() {
  int n = 0;
  for (int i = 0; i < mtData.ifaceCount; i++) {
    MTInterface& f = mtData.interfaces[i];
    if (f.running && nameIsEthernet(f.name)) n++;
  }
  return n;
}

void drawInterfaces() {
  fillScreenGradient(COLOR_BG, COLOR_BG2);
  drawSidebar(1);
  drawHeader();
  drawIcon(36, HEADER_H + 10, ICON_LAN, COLOR_ACCENT, COLOR_BG);
  useFont(FONT_XS);
  putText(56, HEADER_H + 6, "INTERFACES", COLOR_TEXT_TITLE, COLOR_BG);

  int total = ifaceEligibleCount();
  if (ifaceSelOffset >= total)
    ifaceSelOffset = (total > 0) ? ((total - 1) / IFACE_ROWS) * IFACE_ROWS : 0;

  int y = IFACE_ROW_Y;
  int seen = 0, drawn = 0;
  for (int i = 0; i < mtData.ifaceCount && drawn < IFACE_ROWS; i++) {
    MTInterface& f = mtData.interfaces[i];
    if (!f.running || !nameIsEthernet(f.name)) continue;
    if (seen++ < ifaceSelOffset) continue;
    drawGlassCard(30, y, 286, 28);
    tft.fillCircle(40, y + 14, 4, COLOR_GREEN);
    useFont(FONT_XS);
    String nm = String(f.name);
    if (nm.length() > 10) nm = nm.substring(0, 10);
    putText(50, y + 4, nm, COLOR_TEXT_TITLE, COLOR_CARD);
    useFont(FONT_SM);
    String rt = "Tx " + fmtRate(rateTXbps[i]) + "  Rx " + fmtRate(rateRXbps[i]);
    putTextR(284, y + 4, rt, COLOR_TEXT_LABEL, COLOR_CARD);
    // Kotak centang (tercentang = tampil di Dashboard)
    bool sel = dashSelected(f.name);
    int cbx = 292, cby = y + 6;
    tft.drawRoundRect(cbx, cby, 16, 16, 2, sel ? COLOR_ACCENT : COLOR_CARD_BORDER);
    if (sel) {
      tft.fillRoundRect(cbx + 3, cby + 3, 10, 10, 1, COLOR_ACCENT);
      tft.drawLine(cbx + 5, cby + 8, cbx + 7, cby + 11, TFT_BLACK);
      tft.drawLine(cbx + 7, cby + 11, cbx + 11, cby + 5, TFT_BLACK);
    }
    y += IFACE_ROW_H;
    drawn++;
  }
  if (total == 0) {
    useFont(FONT_XS);
    putText(80, 140, "Tidak ada interface aktif", COLOR_RED, COLOR_BG);
    return;
  }
  if (total > IFACE_ROWS) {   // navigasi halaman daftar
    int pg = ifaceSelOffset / IFACE_ROWS;
    int pages = (total + IFACE_ROWS - 1) / IFACE_ROWS;
    tft.fillRoundRect(34, IFACE_PG_Y, 60, 24, 3, COLOR_CARD);
    tft.drawRoundRect(34, IFACE_PG_Y, 60, 24, 3, COLOR_CARD_BORDER);
    useFontTiny();
    putTextC(64, IFACE_PG_Y + 8, "<<", COLOR_TEXT_TITLE, COLOR_CARD);
    tft.fillRoundRect(226, IFACE_PG_Y, 60, 24, 3, COLOR_CARD);
    tft.drawRoundRect(226, IFACE_PG_Y, 60, 24, 3, COLOR_CARD_BORDER);
    putTextC(256, IFACE_PG_Y + 8, ">>", COLOR_TEXT_TITLE, COLOR_CARD);
    putTextC(160, IFACE_PG_Y + 8, String(pg + 1) + "/" + String(pages), COLOR_TEXT_LABEL, COLOR_BG);
  }
  // Catatan sebagai footer — jangan di bawah judul, agar tidak menimpa teks lain
  useFontTiny();
  putTextC(160, IFACE_FOOT_Y, "Kotak = tampil di Dashboard (maks 2)", COLOR_TEXT_LABEL, COLOR_BG);
}

// ==================== WIFI INFO (PAGE 2) ====================
void drawWifiInfo() {
  fillScreenGradient(COLOR_BG, COLOR_BG2);
  drawSidebar(2);
  drawHeader();
  drawIcon(36, HEADER_H + 10, ICON_WIFI, COLOR_ACCENT, COLOR_BG);
  useFont(FONT_XS);
  putText(56, HEADER_H + 6, "WiFi INFO", COLOR_TEXT_TITLE, COLOR_BG);

  if (WiFi.status() == WL_CONNECTED) {
    int y = HEADER_H + 36;
    struct { const char* l; String v; } rows[6] = {
      {"SSID", String(WiFi.SSID())},
      {"RSSI", String(WiFi.RSSI()) + " dBm"},
      {"MAC", WiFi.macAddress()},
      {"IPv4", WiFi.localIP().toString()},
      {"GW", WiFi.gatewayIP().toString()},
      {"DNS", WiFi.dnsIP().toString()},
    };
    for (int i = 0; i < 6; i++) {
      drawGlassCard(30, y, 270, 25);
      useFont(FONT_XS);
      putText(36, y + 7, rows[i].l, COLOR_TEXT_LABEL, COLOR_CARD);
      useFont(FONT_SM);
      putTextR(294, y + 6, rows[i].v.length() > 24 ? rows[i].v.substring(0, 24) : rows[i].v, COLOR_TEXT_TITLE, COLOR_CARD);
      y += 27;
    }
  } else {
    useFont(FONT_XS);
    putText(80, 120, "Belum konek WiFi", COLOR_RED, COLOR_BG);
  }
}

// ==================== SETTINGS (PAGE 3) — 3 TAB ====================
// Tab 0 = NETWORK (MikroTik IP/API/SNMP), 1 = APPEARANCE, 2 = DEVICE
#define STAB_Y      (HEADER_H + 4)
#define STAB_H      20
#define STAB_X0     30
#define STAB_W      92
#define STAB_GAP    4
#define SROW_X      30
#define SROW_W      286
#define SROW_Y0     60
#define SROW_H      26      // 7 baris (APPEARANCE) masih pas di tinggi 240 px
#define SROW_CARD_H 23

// Bar tab: font GLCD 8px (fixed 6px/char) + ikon 16px + border tegas.
// Font FreeSans 9pt terlalu lebar → "APPEARANCE" tumpang ke tab sebelahnya.
// Password di baris Settings ditampilkan bertopeng
String maskPw(const char* p) {
  if (!p || !p[0]) return String("kosong");
  return String("****");
}

void drawSettingsTabs() {
  const char* labels[3] = {"NETWORK", "APPEARANCE", "DEVICE"};
  const uint8_t* icons[3] = {ICON_ROUTER, ICON_PALETTE, ICON_TOOLS};
  for (int i = 0; i < 3; i++) {
    int x = STAB_X0 + i * (STAB_W + STAB_GAP);
    bool sel = (settingsTab == i);
    uint16_t bg = sel ? COLOR_ACCENT : COLOR_CARD;
    tft.fillRoundRect(x, STAB_Y, STAB_W, STAB_H, 3, bg);
    tft.drawRoundRect(x, STAB_Y, STAB_W, STAB_H, 3, sel ? COLOR_ACCENT : COLOR_CARD_BORDER);
    drawIcon(x + 6, STAB_Y + 2, icons[i], sel ? TFT_BLACK : COLOR_TEXT_LABEL, bg);
    useFontTiny();
    putText(x + 25, STAB_Y + 6, labels[i], sel ? TFT_BLACK : COLOR_TEXT_LABEL, bg);
  }
}

// Satu baris pengaturan (label kiri, nilai rata kanan, panah chevron)
void settingsRow(int r, const char* label, const String& value, uint16_t vcol) {
  int y = SROW_Y0 + r * SROW_H;
  drawGlassCard(SROW_X, y, SROW_W, SROW_CARD_H);
  useFont(FONT_XS);
  putText(SROW_X + 10, y + 5, label, COLOR_TEXT_LABEL, COLOR_CARD);
  putTextR(SROW_X + SROW_W - 14, y + 5, value, vcol, COLOR_CARD);
  putTextR(SROW_X + SROW_W - 5, y + 5, ">", COLOR_ACCENT, COLOR_CARD);
}

void drawSettings() {
  fillScreenGradient(COLOR_BG, COLOR_BG2);
  drawSidebar(3);
  drawHeader();
  drawIcon(36, HEADER_H + 10, ICON_GEAR, COLOR_ACCENT, COLOR_BG);
  useFont(FONT_XS);
  putText(56, HEADER_H + 6, "SETTINGS", COLOR_TEXT_TITLE, COLOR_BG);

  drawSettingsTabs();

  if (settingsTab == 0) {                 // ---- NETWORK ----
    settingsRow(0, "MikroTik IP", String(storage.current.mikrotikIP), COLOR_TEXT_TITLE);
    settingsRow(1, "API Port", String(storage.current.apiPort), COLOR_TEXT_TITLE);
    settingsRow(2, "User", storage.current.mtUser[0] ? String(storage.current.mtUser) : "kosong", COLOR_TEXT_TITLE);
    settingsRow(3, "Password", maskPw(storage.current.mtPass), COLOR_TEXT_TITLE);
    settingsRow(4, "SNMP", String(storage.current.snmpCommunity), COLOR_TEXT_TITLE);
    settingsRow(5, "SNMP Port", String(storage.current.snmpPort), COLOR_TEXT_TITLE);
  } else if (settingsTab == 1) {          // ---- APPEARANCE ----
    String scr = storage.current.screenTimeout == 0 ? "Always ON"
               : (storage.current.screenTimeout == 60  ? "1 min"
               : (storage.current.screenTimeout == 300 ? "5 min"
               : (storage.current.screenTimeout == 600 ? "10 min"
               : String(storage.current.screenTimeout) + "s")));
    settingsRow(0, "Refresh", String(storage.current.refreshInterval) + " sec", COLOR_TEXT_TITLE);
    settingsRow(1, "Theme", darkMode ? "Dark" : "Light", COLOR_TEXT_TITLE);
    settingsRow(2, "Bright", String(storage.current.brightness) + "%", COLOR_TEXT_TITLE);
    settingsRow(3, "Screen", scr, COLOR_TEXT_TITLE);
    settingsRow(4, "LED", String(storage.current.ledBright) + "%", COLOR_TEXT_TITLE);
    settingsRow(5, "Glow", storage.current.chartGlow ? "ON" : "OFF", COLOR_ACCENT);
    settingsRow(6, "Auto Lock", storage.current.autoLock ? "ON" : "OFF", COLOR_ACCENT);
  } else {                                // ---- DEVICE ----
    settingsRow(0, "WiFi", storage.current.wifiSSID[0] ? String(storage.current.wifiSSID) : "none", COLOR_TEXT_TITLE);
    settingsRow(1, "Reset", "hapus semua data", COLOR_RED);
  }
}

// ==================== TRAFFIC (PAGE 4) ====================
// Interface traffic terpilih (hanya ethernet yg running); -1 = auto pertama
int resolveTrafficIfi() {
  if (trafficIfi >= 0 && trafficIfi < mtData.ifaceCount) {
    MTInterface& f = mtData.interfaces[trafficIfi];
    if (f.running && nameIsEthernet(f.name)) return trafficIfi;
  }
  for (int i = 0; i < mtData.ifaceCount; i++) {
    MTInterface& f = mtData.interfaces[i];
    if (f.running && nameIsEthernet(f.name)) return i;
  }
  return -1;
}
void stepTrafficIfi(int dir) {
  int cur = resolveTrafficIfi();
  if (cur < 0) return;
  int n = mtData.ifaceCount;
  for (int k = 1; k <= n; k++) {
    int i = (cur + dir * k + n * k) % n;
    MTInterface& f = mtData.interfaces[i];
    if (f.running && nameIsEthernet(f.name)) { trafficIfi = i; needRedraw = true; return; }
  }
}
void drawTraffic() {
  fillScreenGradient(COLOR_BG, COLOR_BG2);
  drawSidebar(4);
  drawHeader();
  drawIcon(36, HEADER_H + 10, ICON_CHART, COLOR_ACCENT, COLOR_BG);
  useFontTiny();
  putText(56, HEADER_H + 8, "TRAFFIC", COLOR_TEXT_TITLE, COLOR_BG);

  int ifi = resolveTrafficIfi();
  // Pilih interface sebaris judul (kanan): [<] nama [>]
  int sy = HEADER_H + 4;
  tft.fillRoundRect(182, sy, 36, 20, 3, COLOR_CARD);
  tft.drawRoundRect(182, sy, 36, 20, 3, COLOR_CARD_BORDER);
  useFont(FONT_XS);
  putTextC(200, sy + 4, "<", COLOR_ACCENT, COLOR_CARD);
  tft.fillRoundRect(276, sy, 40, 20, 3, COLOR_CARD);
  tft.drawRoundRect(276, sy, 40, 20, 3, COLOR_CARD_BORDER);
  putTextC(296, sy + 4, ">", COLOR_ACCENT, COLOR_CARD);
  useFontTiny();
  if (ifi >= 0) {
    String nm = String(mtData.interfaces[ifi].name);
    if (nm.length() > 8) nm = nm.substring(0, 8);
    putTextC(247, sy + 5, nm, COLOR_TEXT_TITLE, COLOR_BG);
  } else putTextC(247, sy + 5, "--", COLOR_TEXT_LABEL, COLOR_BG);

  // Grafik besar — memakai seluruh ruang sampai garis footer Tx/Rx
  int chx = 30, chw = 286, cht = HEADER_H + 30;
  int ftop = 214;                        // batas atas footer Tx/Rx (menempel dasar layar)
  int chh = ftop - cht - 1;
  if (ifi >= 0) {
    drawAreaChartPair(ifi, chx, cht, chw, chh, true);   // axis: label sumbu Y + gridline
    // Footer Tx/Rx: garis pemisah + baris teks di dasar layar
    tft.drawFastHLine(chx, ftop, chw, COLOR_CARD_BORDER);
    // Font GLCD 8px (satu tingkat lebih kecil dari 9pt) — footer tetap ringkas
    int ly = 226;
    useFontTiny();
    tft.fillRect(34, ly + 2, 6, 3, CHART_TX_COLOR);
    putText(44, ly, "Tx", COLOR_TEXT_LABEL, COLOR_BG);
    putText(44 + tw("Tx") + 4, ly, fmtMbps(rateTXbps[ifi]), CHART_TX_COLOR, COLOR_BG);
    String rxv = fmtMbps(rateRXbps[ifi]);
    int vx = 312 - tw(rxv);
    tft.fillRect(vx - 14, ly + 2, 6, 3, CHART_RX_COLOR);
    putText(vx - 30, ly, "Rx", COLOR_TEXT_LABEL, COLOR_BG);
    putText(vx, ly, rxv, CHART_RX_COLOR, COLOR_BG);
  } else {
    drawGlassCard(chx, cht, chw, chh);
    useFont(FONT_XS);
    putTextC(173, cht + chh / 2 - 6, "Tidak ada interface aktif", COLOR_TEXT_LABEL, COLOR_CARD);
  }
}

// ==================== PPP ACTIVE (PAGE 5) ====================
void drawPPP() {
  fillScreenGradient(COLOR_BG, COLOR_BG2);
  drawSidebar(5);
  drawHeader();
  drawIcon(36, HEADER_H + 10, ICON_USERS, COLOR_ACCENT, COLOR_BG);
  useFont(FONT_XS);
  putText(56, HEADER_H + 11, "PPP ACTIVE", COLOR_TEXT_TITLE, COLOR_BG);
  useFont(FONT_XS);
  putTextR(312, HEADER_H + 9, String(mtData.pppCount) + " user", COLOR_TEXT_LABEL, COLOR_BG);

  // Daftar user + durasi sesi (5 per layar, bisa scroll)
  if (pppScrollOffset > mtData.pppCount - 1) pppScrollOffset = 0;
  int y = HEADER_H + 30, shown = 0;
  for (int i = pppScrollOffset; i < mtData.pppCount && shown < 5; i++) {
    MTPPPUser& u = mtData.pppUsers[i];
    drawGlassCard(30, y, 286, 30);
    tft.fillCircle(40, y + 15, 4, COLOR_GREEN);
    useFont(FONT_XS);
    String nm = String(u.name);
    if (nm.length() > 16) nm = nm.substring(0, 16);
    putText(50, y + 9, nm, COLOR_TEXT_TITLE, COLOR_CARD);
    useFontTiny();
    putTextR(302, y + 10, String(u.uptime), COLOR_TEXT_LABEL, COLOR_CARD);
    y += 32;
    shown++;
  }
  if (shown == 0) {
    useFont(FONT_XS);
    putText(100, 150, "Tidak ada user aktif", COLOR_TEXT_LABEL, COLOR_BG);
  } else if (mtData.pppCount > 5) {
    // Tombol scroll + indikator halaman
    // <<< halaman pertama · << mundur · >> maju · >>> halaman akhir
    int by = 224;
    useFontTiny();
    tft.fillRoundRect(30, by, 46, 14, 2, COLOR_CARD);
    tft.drawRoundRect(30, by, 46, 14, 2, COLOR_CARD_BORDER);
    putTextC(53, by + 3, "<<<", COLOR_ACCENT, COLOR_CARD);
    tft.fillRoundRect(80, by, 46, 14, 2, COLOR_CARD);
    tft.drawRoundRect(80, by, 46, 14, 2, COLOR_CARD_BORDER);
    putTextC(103, by + 3, "<<", COLOR_ACCENT, COLOR_CARD);
    tft.fillRoundRect(220, by, 46, 14, 2, COLOR_CARD);
    tft.drawRoundRect(220, by, 46, 14, 2, COLOR_CARD_BORDER);
    putTextC(243, by + 3, ">>", COLOR_ACCENT, COLOR_CARD);
    tft.fillRoundRect(270, by, 46, 14, 2, COLOR_CARD);
    tft.drawRoundRect(270, by, 46, 14, 2, COLOR_CARD_BORDER);
    putTextC(293, by + 3, ">>>", COLOR_ACCENT, COLOR_CARD);
    putTextC(173, by + 3, String(pppScrollOffset + 1) + "-" + String(pppScrollOffset + shown) + "/" + String(mtData.pppCount), COLOR_TEXT_LABEL, COLOR_BG);
  }
}

// ==================== POPUP TRAFIK CLIENT PPP ====================
// Tap user di halaman PPP ACTIVE → popup live trafik interface <user>.
// Trafik diambil dari interface dinamis yang sudah dicocokkan di API (u.ifIdx).
#define PPPPOP_X 24
#define PPPPOP_Y 42
#define PPPPOP_W 272
#define PPPPOP_H 170

unsigned long lastPPPUpd = 0;
unsigned long pppOpened = 0;   // waktu popup dibuka (masa tenggang sentuh)

// Hanya area data yang digambar ulang (judul & tombol tutup tetap) → tanpa kedip
void drawPPPTrafficData() {
  if (pppSel < 0 || pppSel >= mtData.pppCount) return;
  MTPPPUser& u = mtData.pppUsers[pppSel];
  int ifi = u.ifIdx;

  tft.fillRect(30, 88, 260, 88, COLOR_CARD);
  useFontTiny();
  if (ifi < 0 || ifi >= mtData.ifaceCount) {
    putTextC(160, 120, "Tidak ada interface utk " + String(u.name), COLOR_AMBER, COLOR_CARD);
    return;
  }

  // Hanya nilai live Tx/Rx interface client (tanpa grafik)
  tft.fillRect(40, 100, 8, 4, CHART_TX_COLOR);
  useFontTiny();
  putText(54, 98, "Tx", COLOR_TEXT_LABEL, COLOR_CARD);
  useFont(FONT_MD);
  putTextR(292, 92, fmtRate(rateTXbps[ifi]) + " bps", CHART_TX_COLOR, COLOR_CARD);

  useFontTiny();
  tft.fillRect(40, 140, 8, 4, CHART_RX_COLOR);
  putText(54, 138, "Rx", COLOR_TEXT_LABEL, COLOR_CARD);
  useFont(FONT_MD);
  putTextR(292, 132, fmtRate(rateRXbps[ifi]) + " bps", CHART_RX_COLOR, COLOR_CARD);

  useFontTiny();
  putTextC(160, 160, "Sesi: " + String(u.uptime), COLOR_TEXT_LABEL, COLOR_CARD);
}

void drawPPPTrafficPopup() {
  if (pppSel < 0 || pppSel >= mtData.pppCount) { popupPPP = false; return; }
  MTPPPUser& u = mtData.pppUsers[pppSel];

  drawGlassCard(PPPPOP_X, PPPPOP_Y, PPPPOP_W, PPPPOP_H);
  tft.drawRoundRect(PPPPOP_X, PPPPOP_Y, PPPPOP_W, PPPPOP_H, 5, COLOR_ACCENT);

  useFont(FONT_XS);
  String nm = String(u.name);
  if (nm.length() > 20) nm = nm.substring(0, 20);
  putText(36, 50, nm, COLOR_ACCENT, COLOR_CARD);

  useFontTiny();
  int ifi = u.ifIdx;
  String ifn = (ifi >= 0 && ifi < mtData.ifaceCount)
             ? ("Interface: " + String(mtData.interfaces[ifi].name))
             : String("Interface: -");
  putText(36, 70, ifn, COLOR_TEXT_LABEL, COLOR_CARD);

  // Tombol TUTUP eksplisit: sentuhan lain tidak menutup, supaya popup tidak
  // langsung tertutup oleh laporan sentuh resistif yang berulang.
  tft.fillRoundRect(110, 180, 100, 26, 3, COLOR_CARD_BORDER);
  useFontTiny();
  putTextC(160, 187, "TUTUP", COLOR_TEXT_TITLE, COLOR_CARD_BORDER);

  drawPPPTrafficData();
}

// ==================== WIFI SELECT ====================
void drawWifiList() {
  fillScreenGradient(COLOR_BG, COLOR_BG2);
  drawSidebar(3);
  drawHeader();
  drawIcon(36, HEADER_H + 10, ICON_WIFI, COLOR_ACCENT, COLOR_BG);
  useFont(FONT_XS);
  putText(56, HEADER_H + 6, "SELECT WIFI", COLOR_TEXT_TITLE, COLOR_BG);
  int maxV = 6, start = HEADER_H + 34, rh = 26;
  for (int i = 0; i < maxV && (i + wifiScrollOffset) < wifiCount; i++) {
    int n = i + wifiScrollOffset;
    int y = start + i * rh;
    drawGlassCard(30, y, 286, rh - 3);
    String ss = String(wifiList[n].ssid);
    bool saved = storage.findProfile(wifiList[n].ssid) >= 0;
    if (saved) ss = "* " + ss;
    if (ss.length() > 20) ss = ss.substring(0, 20);
    useFontTiny();
    putText(36, y + 7, ss, saved ? COLOR_GREEN : COLOR_TEXT_TITLE, COLOR_CARD);
    String rss = String(wifiList[n].rssi) + "dBm";
    useFontTiny();
    putTextR(288, y + 7, rss, wifiList[n].rssi < -70 ? COLOR_RED : (wifiList[n].rssi < -55 ? COLOR_AMBER : COLOR_GREEN), COLOR_CARD);
    useFontTiny();
    putTextR(316, y + 7, wifiList[n].authType ? "Lk" : "Op", wifiList[n].authType ? COLOR_AMBER : COLOR_GREEN, COLOR_CARD);
  }
  if (wifiCount == 0) {
    useFont(FONT_XS);
    putText(120, 120, "Tidak ada WiFi", COLOR_TEXT_LABEL, COLOR_BG);
  }
  tft.fillRoundRect(30, 210, 70, 24, 3, COLOR_ACCENT);
  useFont(FONT_XS);
  putTextC(65, 214, "SCAN", TFT_BLACK, COLOR_ACCENT);
  tft.fillRoundRect(106, 210, 55, 24, 3, COLOR_CARD);
  putTextC(133, 214, "<<", COLOR_TEXT_TITLE, COLOR_CARD);
  tft.fillRoundRect(165, 210, 55, 24, 3, COLOR_CARD);
  putTextC(192, 214, ">>", COLOR_TEXT_TITLE, COLOR_CARD);
  tft.fillRoundRect(224, 210, 92, 24, 3, COLOR_RED);
  putTextC(270, 214, "CANCEL", TFT_WHITE, COLOR_RED);
}

int wifiScanRetries = 0;

// Simpan hasil scan terakhir ke wifiList (tanpa scan ulang)
void storeScanResults(int n) {
  wifiCount = 0; wifiScrollOffset = 0; wifiScanRetries = 0;
  wifiCount = (n > 0 && n > MAX_WIFI_LIST) ? MAX_WIFI_LIST : (n > 0 ? n : 0);
  for (int i = 0; i < wifiCount; i++) {
    strncpy(wifiList[i].ssid, WiFi.SSID(i).c_str(), 32);
    wifiList[i].ssid[32] = 0;
    wifiList[i].rssi = WiFi.RSSI(i);
    wifiList[i].authType = WiFi.encryptionType(i);
  }
  WiFi.scanDelete();
}

void scanWiFi() {
  wifiCount = 0; wifiScrollOffset = 0; wifiScanRetries = 0;
  fillScreenGradient(COLOR_BG, COLOR_BG2);
  drawSidebar(3);
  drawHeader();
  useFont(FONT_MD);
  putTextC(160, 100, "Scanning WiFi...", COLOR_TEXT_TITLE, COLOR_BG);
  WiFi.disconnect(false, true);   // lepas percobaan connect yang menggantung
  delay(1000);
  int n = WIFI_SCAN_FAILED;
  while (n <= 0 && wifiScanRetries < 8) {
    delay(2000);                     // jeda sama seperti pola uji scan yang berhasil
    n = WiFi.scanNetworks();         // blocking scan
    Serial.printf("[WiFi] scan percobaan %d -> %d\n", wifiScanRetries + 1, n);
    if (n <= 0) wifiScanRetries++;
  }
  storeScanResults(n);
  if (n < 0) {
    Serial.println("[WiFi] Scan gagal");
  } else {
    Serial.printf("[WiFi] Ditemukan %d jaringan\n", wifiCount);
  }
  drawWifiList();
}

bool onWiFiPassConfirm(const char* v) {
  strncpy(storage.current.wifiPass, v, 63);
  storage.current.wifiPass[63] = 0;
  triedSaved = false;
  tryWiFiConnect();
  return true;
}
void onWiFiCancel() {
  storage.syncLegacyWiFi();   // batalkan perubahan SSID/password sementara
  drawWifiList();
}

void tryWiFiConnect() {
  WiFi.begin(storage.current.wifiSSID, storage.current.wifiPass);
  wifiConnecting = true;
  wifiConnectStart = millis();
  fillScreenGradient(COLOR_BG, COLOR_BG2);
  drawSidebar(3);
  useFont(FONT_MD);
  putTextC(160, 80, "Connecting...", COLOR_TEXT_TITLE, COLOR_BG);
}

void updateWiFiConnecting() {
  if (WiFi.status() == WL_CONNECTED) {
    wifiConnecting = false;
    triedSaved = false;
    inWiFiScanMode = false;
    configTime(7 * 3600, 0, "pool.ntp.org", "time.nist.gov");
    storage.saveWiFi(storage.current.wifiSSID, storage.current.wifiPass);
    needRefresh = true;
    needRedraw = true;
    return;
  }
  if (millis() - wifiConnectStart > 8000) {
    wifiConnecting = false;
    if (triedSaved) {
      // Password tersimpan mungkin berubah → minta input, bukan rescan
      triedSaved = false;
      kbd.show("Password WiFi", storage.current.wifiPass, false, onWiFiPassConfirm, onWiFiCancel);
    } else {
      inWiFiScanMode = true;
      scanWiFi();
    }
  }
}

// ==================== CALLBACKS ====================
bool onIP(const char* v) {
  strncpy(storage.current.mikrotikIP, v, 31);
  storage.current.mikrotikIP[31] = 0;
  storage.save();
  needRedraw = true;
  return true;
}
bool onComm(const char* v) {
  strncpy(storage.current.snmpCommunity, v, 31);
  storage.current.snmpCommunity[31] = 0;
  storage.save();
  needRedraw = true;
  return true;
}
bool onApiPort(const char* v) {
  int n = String(v).toInt();
  if (n >= 1 && n <= 65535) {
    storage.current.apiPort = n;
    storage.save();
    if (mtapi.isConnected()) mtapi.disconnect();  // paksa reconnect dgn port baru
  }
  needRedraw = true;
  return true;
}
bool onMTUser(const char* v) {
  strncpy(storage.current.mtUser, v, 31);
  storage.current.mtUser[31] = 0;
  storage.save();
  if (mtapi.isConnected()) mtapi.disconnect();  // kredensial baru → login ulang
  needRedraw = true;
  return true;
}
bool onMTPass(const char* v) {
  strncpy(storage.current.mtPass, v, 63);
  storage.current.mtPass[63] = 0;
  storage.save();
  if (mtapi.isConnected()) mtapi.disconnect();
  needRedraw = true;
  return true;
}
bool onSnmpPort(const char* v) {
  int n = String(v).toInt();
  if (n >= 1 && n <= 65535) { storage.current.snmpPort = n; storage.save(); }
  needRedraw = true;
  return true;
}
bool onRefresh(const char* v) {
  int n = String(v).toInt();
  if (n >= 2 && n <= 60) { storage.current.refreshInterval = n; storage.save(); }
  needRedraw = true;
  return true;
}
void onCancel() { needRedraw = true; }

// Popup theme: pilih Dark/Light, diterapkan saat OK ditekan
void drawThemePopup() {
  drawGlassCard(50, 52, 220, 146);
  tft.drawRoundRect(50, 52, 220, 146, 5, COLOR_ACCENT);
  useFont(FONT_SM);
  putTextC(160, 60, "THEME", COLOR_TEXT_TITLE, COLOR_CARD);
  const char* labels[2] = {"Dark", "Light"};
  useFont(FONT_XS);
  for (int i = 0; i < 2; i++) {
    int by = 84 + i * 28;
    bool sel = (themeSel == i);
    tft.fillRoundRect(62, by, 196, 24, 3, sel ? COLOR_ACCENT : COLOR_CARD_BORDER);
    putTextC(160, by + 6, labels[i], sel ? TFT_BLACK : COLOR_TEXT_TITLE, sel ? COLOR_ACCENT : COLOR_CARD_BORDER);
  }
  tft.fillRoundRect(110, 150, 100, 28, 3, COLOR_ACCENT);
  putTextC(160, 156, "OK", TFT_BLACK, COLOR_ACCENT);
}

// ==================== TOUCH ====================
// ==================== KONFIRMASI SCAN WIFI ====================
void drawScanConfirm() {
  drawGlassCard(50, 70, 220, 120);
  tft.drawRoundRect(50, 70, 220, 120, 5, COLOR_ACCENT);
  useFont(FONT_SM);
  putTextC(160, 78, "SCAN WIFI?", COLOR_ACCENT, COLOR_CARD);
  useFont(FONT_XS);
  putTextC(160, 102, "Cari jaringan WiFi sekitar?", COLOR_TEXT_TITLE, COLOR_CARD);
  putTextC(160, 118, "Koneksi akan dihentikan sebentar", COLOR_TEXT_LABEL, COLOR_CARD);
  tft.fillRoundRect(60, 144, 98, 28, 3, COLOR_CARD_BORDER);
  putTextC(109, 150, "BATAL", COLOR_TEXT_TITLE, COLOR_CARD_BORDER);
  tft.fillRoundRect(162, 144, 98, 28, 3, COLOR_ACCENT);
  putTextC(211, 150, "OK", TFT_BLACK, COLOR_ACCENT);
}

// ==================== KONFIRMASI KUNCI LAYAR ====================
void drawLockConfirm() {
  drawGlassCard(50, 70, 220, 120);
  tft.drawRoundRect(50, 70, 220, 120, 5, COLOR_ACCENT);
  useFont(FONT_SM);
  putTextC(160, 78, "KUNCI LAYAR?", COLOR_ACCENT, COLOR_CARD);
  useFont(FONT_XS);
  putTextC(160, 102, "Kunci layar sekarang?", COLOR_TEXT_TITLE, COLOR_CARD);
  putTextC(160, 118, "Semua sentuhan dikunci", COLOR_TEXT_LABEL, COLOR_CARD);
  tft.fillRoundRect(60, 144, 98, 28, 3, COLOR_CARD_BORDER);
  putTextC(109, 150, "BATAL", COLOR_TEXT_TITLE, COLOR_CARD_BORDER);
  tft.fillRoundRect(162, 144, 98, 28, 3, COLOR_ACCENT);
  putTextC(211, 151, "TUTUP KUNCI", TFT_BLACK, COLOR_ACCENT);
}

// ==================== KONFIRMASI RESET ====================
void drawResetConfirm() {
  drawGlassCard(50, 70, 220, 120);
  tft.drawRoundRect(50, 70, 220, 120, 5, COLOR_RED);
  useFont(FONT_SM);
  putTextC(160, 78, "RESET?", COLOR_RED, COLOR_CARD);
  useFont(FONT_XS);
  putTextC(160, 102, "Hapus semua pengaturan?", COLOR_TEXT_TITLE, COLOR_CARD);
  putTextC(160, 118, "WiFi harus daftar ulang", COLOR_TEXT_LABEL, COLOR_CARD);
  tft.fillRoundRect(60, 144, 98, 28, 3, COLOR_CARD_BORDER);
  putTextC(109, 150, "BATAL", COLOR_TEXT_TITLE, COLOR_CARD_BORDER);
  tft.fillRoundRect(162, 144, 98, 28, 3, COLOR_RED);
  putTextC(211, 150, "YA, RESET", TFT_WHITE, COLOR_RED);
}

// Popup brightness: [-] nilai [+]
void drawBrightPopup() {
  drawGlassCard(50, 60, 220, 130);
  tft.drawRoundRect(50, 60, 220, 130, 5, COLOR_ACCENT);
  useFont(FONT_SM);
  putTextC(160, 68, "BRIGHTNESS", COLOR_TEXT_TITLE, COLOR_CARD);
  tft.fillRoundRect(66, 104, 56, 36, 3, COLOR_CARD_BORDER);
  putTextC(94, 110, "-", COLOR_TEXT_TITLE, COLOR_CARD_BORDER);
  tft.fillRoundRect(198, 104, 56, 36, 3, COLOR_CARD_BORDER);
  putTextC(226, 110, "+", COLOR_TEXT_TITLE, COLOR_CARD_BORDER);
  useFont(FONT_MD);
  putTextC(160, 108, String(storage.current.brightness) + "%", COLOR_ACCENT, COLOR_CARD);
  tft.fillRoundRect(110, 150, 100, 28, 3, COLOR_ACCENT);
  putTextC(160, 155, "OK", TFT_BLACK, COLOR_ACCENT);
}

// Popup screen time: pilih 1/5/10 menit / Always ON (highlight), OK untuk terapkan
void drawScreenPopup() {
  drawGlassCard(40, 36, 240, 178);
  tft.drawRoundRect(40, 36, 240, 178, 5, COLOR_ACCENT);
  useFont(FONT_SM);
  putTextC(160, 44, "SCREEN TIME", COLOR_TEXT_TITLE, COLOR_CARD);
  const char* labels[4] = {"1 minute", "5 minutes", "10 minutes", "Always ON"};
  useFont(FONT_XS);
  for (int i = 0; i < 4; i++) {
    int by = 70 + i * 27;
    bool sel = (screenSel == i);
    tft.fillRoundRect(54, by, 212, 24, 3, sel ? COLOR_ACCENT : COLOR_CARD_BORDER);
    putTextC(160, by + 6, labels[i], sel ? TFT_BLACK : COLOR_TEXT_TITLE, sel ? COLOR_ACCENT : COLOR_CARD_BORDER);
  }
  tft.fillRoundRect(110, 182, 100, 26, 3, COLOR_ACCENT);
  putTextC(160, 187, "OK", TFT_BLACK, COLOR_ACCENT);
}

// Popup LED brightness: [-] nilai [+]
void drawLEDPopup() {
  drawGlassCard(50, 60, 220, 130);
  tft.drawRoundRect(50, 60, 220, 130, 5, COLOR_ACCENT);
  useFont(FONT_SM);
  putTextC(160, 68, "LED BRIGHT", COLOR_TEXT_TITLE, COLOR_CARD);
  tft.fillRoundRect(66, 104, 56, 36, 3, COLOR_CARD_BORDER);
  putTextC(94, 110, "-", COLOR_TEXT_TITLE, COLOR_CARD_BORDER);
  tft.fillRoundRect(198, 104, 56, 36, 3, COLOR_CARD_BORDER);
  putTextC(226, 110, "+", COLOR_TEXT_TITLE, COLOR_CARD_BORDER);
  useFont(FONT_MD);
  putTextC(160, 108, String(storage.current.ledBright) + "%", COLOR_GREEN, COLOR_CARD);
  tft.fillRoundRect(110, 150, 100, 28, 3, COLOR_GREEN);
  putTextC(160, 155, "OK", TFT_BLACK, COLOR_GREEN);
}

// Popup glow: pilih ON/OFF (highlight), OK untuk terapkan
void drawGlowPopup() {
  drawGlassCard(50, 52, 220, 146);
  tft.drawRoundRect(50, 52, 220, 146, 5, COLOR_ACCENT);
  useFont(FONT_SM);
  putTextC(160, 60, "GLOW", COLOR_TEXT_TITLE, COLOR_CARD);
  const char* labels[2] = {"ON", "OFF"};
  useFont(FONT_XS);
  for (int i = 0; i < 2; i++) {
    int by = 84 + i * 28;
    bool sel = (glowSel == i);
    tft.fillRoundRect(62, by, 196, 24, 3, sel ? COLOR_ACCENT : COLOR_CARD_BORDER);
    putTextC(160, by + 6, labels[i], sel ? TFT_BLACK : COLOR_TEXT_TITLE, sel ? COLOR_ACCENT : COLOR_CARD_BORDER);
  }
  tft.fillRoundRect(110, 150, 100, 28, 3, COLOR_ACCENT);
  putTextC(160, 156, "OK", TFT_BLACK, COLOR_ACCENT);
}

// Buka popup dgn nilai saat ini sudah ter-highlight
void openScreenPopup() {
  const int v[4] = {60, 300, 600, 0};
  screenSel = 0;
  for (int i = 0; i < 4; i++) if (storage.current.screenTimeout == v[i]) screenSel = i;
  popupScreen = true;
  drawScreenPopup();
}
void openGlowPopup() {
  glowSel = storage.current.chartGlow ? 0 : 1;
  popupGlow = true;
  drawGlowPopup();
}

// Popup Auto Lock: pilih ON/OFF (highlight), OK untuk terapkan
void drawAutoLockPopup() {
  drawGlassCard(50, 52, 220, 146);
  tft.drawRoundRect(50, 52, 220, 146, 5, COLOR_ACCENT);
  useFont(FONT_SM);
  putTextC(160, 60, "AUTO LOCK", COLOR_TEXT_TITLE, COLOR_CARD);
  const char* labels[2] = {"ON", "OFF"};
  useFont(FONT_XS);
  for (int i = 0; i < 2; i++) {
    int by = 84 + i * 28;
    bool sel = (autoLockSel == i);
    tft.fillRoundRect(62, by, 196, 24, 3, sel ? COLOR_ACCENT : COLOR_CARD_BORDER);
    putTextC(160, by + 6, labels[i], sel ? TFT_BLACK : COLOR_TEXT_TITLE, sel ? COLOR_ACCENT : COLOR_CARD_BORDER);
  }
  tft.fillRoundRect(110, 150, 100, 28, 3, COLOR_ACCENT);
  putTextC(160, 156, "OK", TFT_BLACK, COLOR_ACCENT);
}

// ON = layar otomatis terkunci saat screen timeout habis
void openAutoLockPopup() {
  autoLockSel = storage.current.autoLock ? 0 : 1;
  popupAutoLock = true;
  drawAutoLockPopup();
}

// ==================== LAYAR TERKUNCI (LOCK SCREEN) ====================
// Ditutup overlay penuh: semua sentuhan diabaikan kecuali tombol BUKA KUNCI,
// supaya setting tidak bisa diubah tanpa sengaja.
void drawLockScreen() {
  tft.fillScreen(COLOR_BG);
  // Gembok besar: badan + lubang kunci, pengait melengkung di atasnya
  tft.fillRoundRect(140, 80, 40, 30, 14, COLOR_ACCENT);   // pengait
  tft.fillRoundRect(148, 88, 24, 24, 10, COLOR_BG);       // rongga pengait
  tft.fillRoundRect(128, 106, 64, 52, 8, COLOR_ACCENT);   // badan
  tft.fillCircle(160, 126, 7, COLOR_BG);                  // lubang kunci
  tft.fillRect(156, 126, 9, 18, COLOR_BG);
  useFont(FONT_SM);
  putTextC(160, 170, "LAYAR TERKUNCI", COLOR_TEXT_TITLE, COLOR_BG);
  useFont(FONT_XS);
  putTextC(160, 190, "Sentuh tombol untuk membuka", COLOR_TEXT_LABEL, COLOR_BG);
  tft.fillRoundRect(86, 200, 148, 32, 4, COLOR_ACCENT);
  useFont(FONT_SM);
  putTextC(160, 208, "BUKA KUNCI", TFT_BLACK, COLOR_ACCENT);
}

// ==================== POPUP CONNECT / LUPAKAN WIFI ====================
// Muncul saat SSID di halaman SELECT WIFI disentuh (hasil scan maupun profil
// tersimpan): pilih CONNECT, LUPAKAN (bila ada profil), atau BATAL.
void drawWifiActionPopup() {
  const char* ssid = (wifiActIdx >= 0 && wifiActIdx < wifiCount) ? wifiList[wifiActIdx].ssid : "";
  drawGlassCard(30, 40, 260, 160);
  tft.drawRoundRect(30, 40, 260, 160, 5, COLOR_ACCENT);
  useFont(FONT_SM);
  putTextC(160, 46, "JARINGAN WIFI", COLOR_TEXT_TITLE, COLOR_CARD);

  useFont(FONT_XS);
  String ss = String(ssid);
  if (ss.length() > 26) ss = ss.substring(0, 26);
  putTextC(160, 70, ss, COLOR_ACCENT, COLOR_CARD);

  String info = String(wifiList[wifiActIdx].rssi) + "dBm";
  info += wifiList[wifiActIdx].authType ? " - Terkunci" : " - Terbuka";
  if (wifiActSaved) info += " - Tersimpan";
  putTextC(160, 88, info, COLOR_TEXT_LABEL, COLOR_CARD);

  if (wifiActSaved) {
    tft.fillRoundRect(44, 108, 118, 30, 3, COLOR_GREEN);
    putTextC(103, 116, "CONNECT", TFT_BLACK, COLOR_GREEN);
    tft.fillRoundRect(170, 108, 106, 30, 3, COLOR_RED);
    putTextC(223, 116, "LUPAKAN", TFT_WHITE, COLOR_RED);
  } else {
    tft.fillRoundRect(44, 108, 232, 30, 3, COLOR_GREEN);
    putTextC(160, 116, "CONNECT", TFT_BLACK, COLOR_GREEN);
  }
  tft.fillRoundRect(110, 152, 100, 30, 3, COLOR_CARD_BORDER);
  putTextC(160, 160, "BATAL", COLOR_TEXT_TITLE, COLOR_CARD_BORDER);
}

void openWifiAction(int idx) {
  if (idx < 0 || idx >= wifiCount) return;
  wifiActIdx = idx;
  wifiActSaved = (storage.findProfile(wifiList[idx].ssid) >= 0);
  wifiAction = true;
  drawWifiActionPopup();
}

// CONNECT: profil tersimpan → langsung; SSID baru → minta password
void wifiDoConnect() {
  int idx = wifiActIdx;
  wifiAction = false;
  if (idx < 0 || idx >= wifiCount) { drawWifiList(); return; }
  strncpy(storage.current.wifiSSID, wifiList[idx].ssid, 31);
  storage.current.wifiSSID[31] = 0;
  int p = storage.findProfile(wifiList[idx].ssid);
  if (p >= 0) {
    strncpy(storage.current.wifiPass, storage.current.wifiPasses[p], 63);
    storage.current.wifiPass[63] = 0;
    triedSaved = true;
    tryWiFiConnect();
  } else {
    storage.current.wifiPass[0] = 0;   // SSID baru: jangan bawa password SSID lain
    kbd.show("Password WiFi", storage.current.wifiPass, false, onWiFiPassConfirm, onWiFiCancel);
  }
}

// LUPAKAN: hapus profil tersimpan untuk SSID ini (tetap di daftar scan)
void wifiDoForget() {
  int idx = wifiActIdx;
  wifiAction = false;
  if (idx >= 0 && idx < wifiCount && storage.removeProfile(wifiList[idx].ssid)) {
    Serial.printf("[WiFi] Profil dilupakan: %s\n", wifiList[idx].ssid);
  }
  drawWifiList();
}

void handleTouch() {
  if (kbd.isShowing()) { kbd.handleTouch(); return; }
  uint16_t x, y;
  if (!touch.getPoint(&x, &y)) return;
  if (millis() - lastTouch < 350) return;
  lastTouch = millis();
  lastActivity = millis();
  if (screenOff) {  // sentuh saat layar mati = nyalakan saja
    screenOff = false;
    applyBrightness();
    if (screenLocked) {          // timeout tadi mengunci layar → langsung tampilkan layar kunci
      lockOpened = millis();     // masa tenggang dari sentuhan yang membangunkan
      drawLockScreen();
    } else {
      needRedraw = true;
    }
    return;
  }
  Serial.printf("[Touch] x=%d y=%d\n", x, y);

  // Layar terkunci: abaikan semua sentuhan kecuali tombol BUKA KUNCI
  if (screenLocked) {
    if (millis() - lockOpened > 400 &&
        y >= 198 && y <= 234 && x >= 86 && x <= 234) {
      screenLocked = false;
      if (wifiConnecting) {          // lanjutkan tampilan "Connecting..."
        fillScreenGradient(COLOR_BG, COLOR_BG2);
        drawSidebar(3);
        useFont(FONT_MD);
        putTextC(160, 80, "Connecting...", COLOR_TEXT_TITLE, COLOR_BG);
      } else if (inWiFiScanMode) {
        drawWifiList();              // kembalikan daftar hasil scan
      } else {
        needRedraw = true;
      }
    }
    return;
  }

  // Popup konfirmasi scan WiFi (BATAL = kembali, OK = mulai scan)
  if (confirmScan) {
    if (y >= 142 && y <= 174) {
      if (x >= 60 && x <= 158) {
        confirmScan = false; needRedraw = true;
      } else if (x >= 162 && x <= 260) {
        confirmScan = false;
        inWiFiScanMode = true;
        scanWiFi();
      }
    }
    return;
  }

  // Popup konfirmasi kunci layar (BATAL = kembali, TUTUP KUNCI = kunci sekarang)
  if (confirmLock) {
    if (y >= 142 && y <= 174) {
      if (x >= 60 && x <= 158) {
        confirmLock = false; needRedraw = true;
      } else if (x >= 162 && x <= 260) {
        confirmLock = false;
        screenLocked = true;
        lockOpened = millis();
        drawLockScreen();
      }
    }
    return;
  }

  // Popup trafik client PPP: hanya tombol TUTUP yang menutup, dan hanya setelah
  // masa tenggang — laporan sentuh resistif berulang jangan sampai langsung
  // menutup popup yang baru saja dibuka.
  if (popupPPP) {
    if (millis() - pppOpened > 700 &&
        y >= 178 && y <= 208 && x >= 108 && x <= 212) {
      popupPPP = false;
      needRedraw = true;
    }
    return;
  }

  // Dialog konfirmasi reset (YA = lanjut reset, BATAL = kembali)
  if (confirmReset) {
    if (y >= 142 && y <= 174) {
      if (x >= 60 && x <= 158) { confirmReset = false; needRedraw = true; }
      else if (x >= 162 && x <= 260) { confirmReset = false; storage.reset(); needRedraw = true; }
    }
    return;
  }

  // Popup theme: pilih opsi (highlight saja), OK untuk terapkan
  if (popupTheme) {
    if (y >= 84 && y <= 108 && x >= 62 && x <= 258) { themeSel = 0; drawThemePopup(); }
    else if (y >= 112 && y <= 136 && x >= 62 && x <= 258) { themeSel = 1; drawThemePopup(); }
    else if (y >= 150 && y <= 178 && x >= 110 && x <= 210) {
      if (themeSel != (darkMode ? 0 : 1)) {
        darkMode = (themeSel == 0);
        theme = getTheme();
        storage.current.darkMode = darkMode;
        storage.save();
      }
      popupTheme = false; needRedraw = true;
    }
    return;
  }

  // Popup brightness: [-] nilai [+] [OK]
  if (popupBright) {
    if (y >= 104 && y <= 140) {
      if (x >= 66 && x <= 122) {
        storage.current.brightness = constrain(storage.current.brightness - 5, 10, 100);
        storage.save(); applyBrightness(); drawBrightPopup();
      } else if (x >= 198 && x <= 254) {
        storage.current.brightness = constrain(storage.current.brightness + 5, 10, 100);
        storage.save(); applyBrightness(); drawBrightPopup();
      }
    } else if (y >= 150 && y <= 178 && x >= 110 && x <= 210) {
      popupBright = false; needRedraw = true;
    }
    return;
  }

  // Popup screen time: pilih opsi (highlight), OK untuk terapkan
  if (popupScreen) {
    const int vals[4] = {60, 300, 600, 0};
    bool hit = false;
    for (int i = 0; i < 4; i++) {
      int by = 70 + i * 27;
      if (y >= by && y <= by + 24 && x >= 54 && x <= 266) {
        screenSel = i; hit = true; drawScreenPopup(); break;
      }
    }
    if (!hit && y >= 182 && y <= 208 && x >= 110 && x <= 210) {
      storage.current.screenTimeout = vals[screenSel];
      storage.save(); lastActivity = millis();
      popupScreen = false; needRedraw = true;
    }
    return;
  }

  // Popup LED brightness: [-] nilai [+] [OK]
  if (popupLED) {
    if (y >= 104 && y <= 140) {
      if (x >= 66 && x <= 122) {
        storage.current.ledBright = constrain(storage.current.ledBright - 5, 10, 100);
        storage.save(); applyLED(); drawLEDPopup();
      } else if (x >= 198 && x <= 254) {
        storage.current.ledBright = constrain(storage.current.ledBright + 5, 10, 100);
        storage.save(); applyLED(); drawLEDPopup();
      }
    } else if (y >= 150 && y <= 178 && x >= 110 && x <= 210) {
      popupLED = false; needRedraw = true;
    }
    return;
  }

  // Popup glow: pilih ON/OFF (highlight), OK untuk terapkan
  if (popupGlow) {
    if (y >= 84 && y <= 108 && x >= 62 && x <= 258) { glowSel = 0; drawGlowPopup(); }
    else if (y >= 112 && y <= 136 && x >= 62 && x <= 258) { glowSel = 1; drawGlowPopup(); }
    else if (y >= 150 && y <= 178 && x >= 110 && x <= 210) {
      storage.current.chartGlow = (glowSel == 0);
      storage.save();
      popupGlow = false; needRedraw = true;
    }
    return;
  }

  // Popup auto lock: pilih ON/OFF (highlight), OK untuk terapkan
  if (popupAutoLock) {
    if (y >= 84 && y <= 108 && x >= 62 && x <= 258) { autoLockSel = 0; drawAutoLockPopup(); }
    else if (y >= 112 && y <= 136 && x >= 62 && x <= 258) { autoLockSel = 1; drawAutoLockPopup(); }
    else if (y >= 150 && y <= 178 && x >= 110 && x <= 210) {
      storage.current.autoLock = (autoLockSel == 0);
      storage.save();
      popupAutoLock = false; needRedraw = true;
    }
    return;
  }

  // Popup Connect / Lupakan WiFi (konfirmasi sebelum konek atau menghapus profil)
  if (wifiAction) {
    if (y >= 108 && y <= 138) {
      if (wifiActSaved) {
        if (x >= 44 && x <= 162) wifiDoConnect();
        else if (x >= 170 && x <= 276) wifiDoForget();
      } else if (x >= 44 && x <= 276) {
        wifiDoConnect();
      }
    } else if (y >= 152 && y <= 182 && x >= 110 && x <= 210) {
      wifiAction = false;
      drawWifiList();                // BATAL: kembali ke daftar tanpa scan ulang
    }
    return;
  }

  // Ikon gembok di header (ujung kiri, samping judul) = kunci layar
  if (y < HEADER_H && x >= 3 && x <= 23) {
    confirmLock = true;
    drawLockConfirm();
    return;
  }

  // Sidebar navigation
  if (x < SIDEBAR_W) {
    int idx = (y - (HEADER_H + 4)) / 35;   // samakan dgn drawSidebar(): y = HEADER_H + 4 + i * 35
    if (idx >= 0 && idx < 6) {
      page = idx;
      inWiFiScanMode = false;
      needRedraw = true;
    }
    return;
  }

  if (inWiFiScanMode) {
    if (y > 208) {
      if (x < 100) scanWiFi();
      else if (x < 160) { if (wifiScrollOffset > 0) wifiScrollOffset -= 6; drawWifiList(); }
      else if (x < 220) { if (wifiScrollOffset + 6 < wifiCount) wifiScrollOffset += 6; drawWifiList(); }
      else { inWiFiScanMode = false; page = 3; needRedraw = true; }
      return;
    }
    int idx = (int)((y - HEADER_H - 34) / 26) + wifiScrollOffset;
    // Konfirmasi dulu: CONNECT / LUPAKAN (bila tersimpan) / BATAL
    if (idx >= 0 && idx < wifiCount) openWifiAction(idx);
    return;
  }

  // Dashboard: pintasan — kartu interface (kanan) → INTERFACES, kartu USERS → PPP ACTIVE
  if (page == 0) {
    int usrY = HEADER_H + 4 + 5 * STATS_ROW_H;
    if (x >= IFACE_X && y >= HEADER_H) {
      page = 1; ifaceSelOffset = 0; needRedraw = true;
    } else if (y >= usrY && y <= usrY + STATS_ROW_H - 4 && x >= STATS_X && x <= STATS_X + STATS_W) {
      page = 5; pppScrollOffset = 0; needRedraw = true;
    }
    return;
  }

  if (page == 1) {
    int total = ifaceEligibleCount();
    // Navigasi halaman daftar
    if (y >= IFACE_PG_Y && y <= IFACE_PG_Y + 24) {
      if (total > IFACE_ROWS) {
        if (x >= 34 && x <= 94) {
          ifaceSelOffset -= IFACE_ROWS;
          if (ifaceSelOffset < 0) ifaceSelOffset = 0;
          needRedraw = true;
        } else if (x >= 226 && x <= 286) {
          if (ifaceSelOffset + IFACE_ROWS < total) ifaceSelOffset += IFACE_ROWS;
          needRedraw = true;
        }
      }
      return;
    }
    // Sentuh baris = toggle kotak centang (pilih untuk Dashboard)
    int r = (y - IFACE_ROW_Y) / IFACE_ROW_H;
    if (r < 0 || r >= IFACE_ROWS) return;
    int seen = 0, target = -1;
    for (int i = 0; i < mtData.ifaceCount; i++) {
      MTInterface& f = mtData.interfaces[i];
      if (!f.running || !nameIsEthernet(f.name)) continue;
      if (seen++ >= ifaceSelOffset + r) { target = i; break; }
    }
    if (target >= 0) toggleDash(mtData.interfaces[target].name);
    return;
  }

  if (page == 3) {
    // Bar tab di bawah header: sentuh untuk pindah NETWORK / APPEARANCE / DEVICE
    if (y >= STAB_Y && y <= STAB_Y + STAB_H) {
      int t = (x - STAB_X0) / (STAB_W + STAB_GAP);
      int tx = STAB_X0 + t * (STAB_W + STAB_GAP);
      if (t >= 0 && t < 3 && x >= tx && x <= tx + STAB_W) {
        settingsTab = t;
        needRedraw = true;
      }
      return;
    }
    int r = (y - SROW_Y0) / SROW_H;
    if (r < 0) return;
    if (settingsTab == 0) {               // ---- NETWORK ----
      if (r == 0) kbd.show("MikroTik IP", storage.current.mikrotikIP, false, onIP, onCancel);
      else if (r == 1) { String v = String(storage.current.apiPort); kbd.show("API Port", v.c_str(), false, onApiPort, onCancel); }
      else if (r == 2) kbd.show("MikroTik User", storage.current.mtUser, false, onMTUser, onCancel);
      else if (r == 3) kbd.show("MikroTik Password", storage.current.mtPass, true, onMTPass, onCancel);
      else if (r == 4) kbd.show("SNMP Community", storage.current.snmpCommunity, false, onComm, onCancel);
      else if (r == 5) { String v = String(storage.current.snmpPort); kbd.show("SNMP Port", v.c_str(), false, onSnmpPort, onCancel); }
    } else if (settingsTab == 1) {        // ---- APPEARANCE ----
      if (r == 0) { String v = String(storage.current.refreshInterval); kbd.show("Refresh (sec)", v.c_str(), false, onRefresh, onCancel); }
      else if (r == 1) { popupTheme = true; themeSel = darkMode ? 0 : 1; drawThemePopup(); }
      else if (r == 2) { popupBright = true; drawBrightPopup(); }
      else if (r == 3) { openScreenPopup(); }
      else if (r == 4) { popupLED = true; drawLEDPopup(); }
      else if (r == 5) { openGlowPopup(); }
      else if (r == 6) { openAutoLockPopup(); }
    } else {                              // ---- DEVICE ----
      if (r == 0) { confirmScan = true; drawScanConfirm(); }
      else if (r == 1) { confirmReset = true; drawResetConfirm(); }
    }
    return;
  }

  if (page == 4) {
    int sy = HEADER_H + 4;
    if (y >= sy && y <= sy + 20) {
      if (x >= 182 && x <= 218) stepTrafficIfi(-1);
      else if (x >= 276 && x <= 316) stepTrafficIfi(1);
    }
    return;
  }

  if (page == 5) {
    if (y >= 224 && mtData.pppCount > 5) {
      if (x >= 30 && x <= 76) {
        pppScrollOffset = 0;                               // <<< ke halaman pertama
        needRedraw = true;
      } else if (x >= 80 && x <= 126) {
        pppScrollOffset -= 5;                              // << mundur satu halaman
        if (pppScrollOffset < 0) pppScrollOffset = 0;
        needRedraw = true;
      } else if (x >= 220 && x <= 266) {
        if (pppScrollOffset + 5 < mtData.pppCount) pppScrollOffset += 5;   // >> maju
        needRedraw = true;
      } else if (x >= 270 && x <= 316) {
        pppScrollOffset = ((mtData.pppCount - 1) / 5) * 5;  // >>> lompat ke halaman akhir
        needRedraw = true;
      }
    } else {
      // Tap baris user → popup live trafik interface client
      int r = (y - (HEADER_H + 30)) / 32;
      int idx = pppScrollOffset + r;
      Serial.printf("[PPP] tap r=%d idx=%d\n", r, idx);
      if (r >= 0 && r < 5 && idx >= 0 && idx < mtData.pppCount) {
        pppSel = idx;
        popupPPP = true;
        lastPPPUpd = millis();
        pppOpened = millis();   // abaikan sentuh susulan selama 700 ms
        drawPPPTrafficPopup();
      }
    }
    return;
  }
}

// ==================== SETUP ====================
void setup() {
  Serial.begin(115200);
  Serial.println("\n=== BOOT START ===");
  delay(100);
  storage.begin();
  if (storage.isGarbageIP(storage.current.mikrotikIP)) {
    Serial.println("[SETUP] Garbage IP, reset storage");
    storage.reset();
  }
  darkMode = storage.current.darkMode;
  theme = getTheme();
  tft.init(); tft.setRotation(3);
  tft.invertDisplay(false);  // panel ini non-inverted (tanpa ini W=hitam)
  touch.begin(&tft);
  pinMode(TFT_BL, OUTPUT);
  ledcAttach(TFT_BL, 5000, 8);   // PWM backlight (core 3.x)
  applyBrightness();
  lastActivity = millis();
  pinMode(LED_R, OUTPUT); pinMode(LED_G, OUTPUT); pinMode(LED_B, OUTPUT);
  ledcAttach(LED_R, 5000, 8); ledcAttach(LED_G, 5000, 8); ledcAttach(LED_B, 5000, 8);
  setLED(false, false, true);    // biru selama boot/connect
  kbd.init(&tft, &touch);
  fillScreenGradient(COLOR_BG, COLOR_BG2);
  useFont(FONT_MD);
  putTextC(160, 78, "MikroTik", COLOR_ACCENT, COLOR_BG);
  useFont(FONT_XS);
  putTextC(160, 102, "ver " APP_VER, COLOR_TEXT_TITLE, COLOR_BG);
  putTextC(160, 122, "created by clusternet", COLOR_TEXT_LABEL, COLOR_BG);
  putTextC(160, 156, "Loading...", COLOR_TEXT_LABEL, COLOR_BG);
  delay(700);

  WiFi.mode(WIFI_STA); WiFi.setSleep(false);
  WiFi.disconnect(false, true);  // bersihkan konfigurasi WiFi lama di driver
  delay(2000);      // beri waktu radio WiFi stabil
  int syncN = WiFi.scanNetworks();  // uji radio dengan scan sinkron
  Serial.printf("[WiFi] Uji scan: %d jaringan\n", syncN);
  if (syncN < 0) {  // radio tidak merespons
    Serial.println("[WiFi] Radio tidak merespons, restart radio");
    WiFi.mode(WIFI_OFF); delay(300);
    WiFi.mode(WIFI_STA); delay(1500);
  }
  delay(1000);
  // Simpan hasil uji scan, lalu otomatis ke profil dikenal dg sinyal terkuat
  bool haveScan = (syncN > 0);
  if (haveScan) storeScanResults(syncN);
  int best = -1, bestRssi = -1000;
  if (haveScan) {
    for (int i = 0; i < wifiCount; i++) {
      if (storage.findProfile(wifiList[i].ssid) >= 0 && wifiList[i].rssi > bestRssi) {
        bestRssi = wifiList[i].rssi; best = i;
      }
    }
  }
  if (best >= 0) {
    int p = storage.findProfile(wifiList[best].ssid);
    Serial.printf("[WiFi] Auto-connect %s (%d dBm)\n", wifiList[best].ssid, bestRssi);
    WiFi.begin(storage.current.wifiSSIDs[p], storage.current.wifiPasses[p]);
    int n = 0;
    while (WiFi.status() != WL_CONNECTED && n++ < 20) delay(500);
    if (WiFi.status() == WL_CONNECTED) {
      storage.saveWiFi(storage.current.wifiSSIDs[p], storage.current.wifiPasses[p]);
    } else {
      inWiFiScanMode = true; scanWiFi();
    }
  } else if (storage.current.wifiConfigured && strlen(storage.current.wifiSSID) > 0 && !haveScan) {
    // Fallback lama bila scan awal gagal total
    WiFi.begin(storage.current.wifiSSID, storage.current.wifiPass);
    int n = 0;
    while (WiFi.status() != WL_CONNECTED && n++ < 20) delay(500);
    if (WiFi.status() != WL_CONNECTED) { inWiFiScanMode = true; scanWiFi(); }
  } else {
    inWiFiScanMode = true;
    if (haveScan) {
      Serial.printf("[WiFi] Ditemukan %d jaringan\n", wifiCount);
      drawWifiList();
    } else {
      scanWiFi();
    }
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("[API] Connecting...");
    configTime(7 * 3600, 0, "pool.ntp.org", "time.nist.gov");  // sinkron jam WIB
    if (mtapi.connect(storage.current.mikrotikIP, storage.current.apiPort, storage.current.mtUser, storage.current.mtPass)) {
      Serial.println("[API] Connected to MikroTik");
      serverOK = mtapi.fetchAll(mtData);
      needRedraw = true;
    } else {
      Serial.println("[API] Gagal connect");
      serverOK = false;
    }
  }
  Serial.println("=== READY ===");
}

// ==================== LOOP ====================
void loop() {
  unsigned long now = millis();
  updateScreenTimeout(now);
  updateStatusLED();
  if (inWiFiScanMode || wifiConnecting) {
    if (wifiConnecting && !screenLocked) updateWiFiConnecting();
    handleTouch();
    delay(10);
    return;
  }

  handleTouch();

  if (needRefresh || now - lastRefresh >= (unsigned long)storage.current.refreshInterval * 1000UL) {
    if (WiFi.status() == WL_CONNECTED) {
      bool fresh = false;
      if (!mtapi.isConnected()) {
        // Throttle: jangan spam connect tiap refresh saat server down
        if (serverOK || now - lastApiRetry >= API_RETRY_MS) {
          lastApiRetry = now;
          if (mtapi.connect(storage.current.mikrotikIP, storage.current.apiPort, storage.current.mtUser, storage.current.mtPass)) {
            serverOK = mtapi.fetchAll(mtData);
            fresh = serverOK;
          } else {
            serverOK = false;
          }
          needRedraw = true;
        }
      } else {
        bool ok = mtapi.fetchAll(mtData);
        serverOK = ok;
        fresh = ok;
        if (ok) {
          needRedraw = true;
        } else {
          lastApiRetry = now;  // gagal di tengah jalan → mulai backoff
          needRedraw = true;
        }
      }
      if (fresh) {
      unsigned long fetchMs = (millis() - lastFetchMs) > 50 ? (millis() - lastFetchMs) : 5000;
      double secs = (fetchMs > 0) ? (double)fetchMs / 1000.0 : 5.0;
      // Rate real-time utk SEMUA interface (16 slot)
      for (int i = 0; i < mtData.ifaceCount; i++) {
        unsigned long long rx = mtData.interfaces[i].rxBytes;
        unsigned long long tx = mtData.interfaces[i].txBytes;
        if (chartReady) {
          unsigned long long dr = rx - prevRXAll[i];
          unsigned long long dt = tx - prevTXAll[i];
          prevRXAll[i] = rx; prevTXAll[i] = tx;
          rateRXbps[i] = (unsigned long long)((double)dr * 8.0 / secs);
          rateTXbps[i] = (unsigned long long)((double)dt * 8.0 / secs);
        } else {
          prevRXAll[i] = rx; prevTXAll[i] = tx;
        }
      }
      // Chart SEMUA interface (per-slot, dipakai dashboard + halaman Traffic)
      for (int i = 0; i < mtData.ifaceCount && i < CHART_SLOTS; i++) {
        if (chartReady) {
          lastDR[i] = (unsigned long long)((double)rateRXbps[i] * secs / 8.0);
          lastDT[i] = (unsigned long long)((double)rateTXbps[i] * secs / 8.0);
          addChartData(i, lastDR[i], lastDT[i], fetchMs);
        }
      }
      chartReady = true;
      lastIntervalMs = fetchMs;
      lastFetchMs = millis();
      chart_idx = (chart_idx + 1) % CHART_MAX_POINTS;
      }  // fresh
      needRefresh = false;
      lastRefresh = now;
    }
  }

  if (needRedraw && !kbd.isShowing() && !confirmReset && !popupTheme && !popupBright && !popupScreen && !popupLED && !popupGlow && !popupAutoLock && !popupPPP && !confirmScan && !confirmLock && !wifiAction && !screenLocked) {
    if (page == 0) drawDashboard();
    else if (page == 1) drawInterfaces();
    else if (page == 2) drawWifiInfo();
    else if (page == 4) drawTraffic();
    else if (page == 5) drawPPP();
    else drawSettings();  needRedraw = false;
  }

  // Popup trafik client PPP: segarkan angka/grafik live tiap 1 detik.
  // Bila user tersebut sudah tidak aktif, tutup popup-nya.
  if (popupPPP && !screenLocked) {
    if (pppSel < 0 || pppSel >= mtData.pppCount) {
      popupPPP = false; needRedraw = true;
    } else if (millis() - lastPPPUpd >= 1000) {
      lastPPPUpd = millis();
      drawPPPTrafficData();
    }
  }
  delay(10);
}

