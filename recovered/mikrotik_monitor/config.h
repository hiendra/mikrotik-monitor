// ============================================================
// config.h - MikroTik Monitor
// ESP32-024 + ST7789 2.4 inch, landscape 320x240
// ============================================================

#ifndef CONFIG_H
#define CONFIG_H

// ==================== KREDENSIAL ====================
// Nilai rahasia TIDAK ditulis di file ini. Semuanya ada di secrets.h yang
// sudah masuk .gitignore. Salin secrets.h.example -> secrets.h, lalu isi.
#if __has_include("secrets.h")
  #include "secrets.h"
#endif

// Fallback bila secrets.h belum dibuat: build tetap jalan, tetapi perangkat
// tidak bisa konek (WiFi/IP/password kosong) sampai diisi lewat Settings.
#ifndef WIFI_SSID
  #define WIFI_SSID       ""
#endif
#ifndef WIFI_PASSWORD
  #define WIFI_PASSWORD   ""
#endif
#ifndef SNMP_COMMUNITY
  #define SNMP_COMMUNITY  "monitoring"
#endif
#ifndef MIKROTIK_IP
  #define MIKROTIK_IP     ""
#endif
#ifndef MT_USER
  #define MT_USER         "admin"
#endif
#ifndef MT_PASS
  #define MT_PASS         ""
#endif

#define MT_API_PORT     8728

// Versi firmware — ditampilkan di layar boot ("ver 1.1")
#define APP_VER         "1.1"

// TFT_eSPI rotation 3 = landscape 320x240 (ST7789)
#define SCREEN_WIDTH    320
#define SCREEN_HEIGHT   240

// LCD ST7789 — pin SPI/CS/DC/RST diatur di User_Setup.h TFT_eSPI.
// Satu-satunya pin yang dipakai kode di sini adalah backlight (PWM).
#define TFT_BL      27

// LED RGB onboard (CYD 2.4"): common anode, ACTIVE LOW
// Catatan: G/B tertukar di sebagian board → G=17, B=16
#define LED_R       4
#define LED_G       17
#define LED_B       16

// ==================== TOUCHSCREEN XPT2046 ====================
// Touch berbagi jalur SPI LCD: SCK=14, MISO=12, MOSI=13.
// Hanya CS touchscreen yang berbeda.
#define TOUCH_CS_PIN    33

// Layout (sidebar, header, kartu, area chart) didefinisikan di
// mikrotik_monitor.ino, karena sudah disesuaikan dengan tata letak yang
// benar-benar dipakai. Blok konstanta layout lama di sini tidak pernah
// dirujuk dan sudah dihapus.

// ==================== COLOR PALETTE ====================
// Dark Cyber Network Dashboard
// Deep navy-purple + neon blue/cyan accent + glassmorphism panels
#define COLOR_BG            0x1108      // = kartu glass (senada)
#define COLOR_BG2           0x1108      // = kartu glass (gradient flat)
#define COLOR_CARD          0x1108      // #182449 - kartu glass dark navy
#define COLOR_CARD_BORDER   0x29ED      // #2a3f6e - border biru halus (glass edge)
#define COLOR_HEADER        0x1108      // = kartu glass (senada)

// Text Colors
#define COLOR_TEXT_TITLE    0xFFFF      // #FFFFFF - Putih judul
#define COLOR_TEXT_LABEL    0x84D7      // #8a9cc0 - abu kebiruan

// Status Colors
#define COLOR_GREEN         0x07E0      // #00E676 - hijau neon (Up/sehat)
#define COLOR_AMBER         0xFCC0      // #FF9800 - amber (warning)
#define COLOR_RED           0xF800      // #FF1744 - merah neon (kritis)
#define COLOR_ACCENT        0x07FF      // #00E5FF - ELECTRIC CYAN (aksen utama)

// Chart Colors (isi area pakai gradient fade otomatis dari warna garis
// ke warna kartu — lihat drawAreaChart di .ino, tidak perlu warna fill lagi)
#define CHART_TX_COLOR      0xFFE0      // kuning (TX)
#define CHART_RX_COLOR      0xF800      // merah (RX)

// Chart Grid (halus: nyaris senada dgn kartu 0x1108, hanya sedikit lebih terang)
#define CHART_GRID_COLOR    0x1129

// Chart data points
#define CHART_MAX_POINTS    60     // 60 points = 60 seconds at 1s interval

// ==================== THEME TYPE ====================
struct Theme {
  uint16_t bg, header, card, text, dim, border, bg2;
};

#endif