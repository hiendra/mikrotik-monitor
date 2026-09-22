// ============================================================
// config.h - MikroTik Monitor
// ESP32-024 + ST7789 2.4 inch, landscape 320x240
// ============================================================

#ifndef CONFIG_H
#define CONFIG_H

// ==================== KREDENSIAL ====================
// Nilai rahasia TIDAK ditulis di file ini. Semuanya dipindah ke secrets.h
// yang sudah masuk .gitignore. Salin secrets.h.example -> secrets.h, lalu isi.
#if __has_include("secrets.h")
  #include "secrets.h"
#endif

// Fallback bila secrets.h belum dibuat: build tetap jalan, tetapi perangkat
// tidak bisa konek (WiFi/IP/user/password/SNMP kosong) sampai diisi lewat
// Settings. Sengaja dibiarkan kosong: nilai asli tidak boleh ikut ter-commit.
#ifndef WIFI_SSID
  #define WIFI_SSID       ""
#endif
#ifndef WIFI_PASSWORD
  #define WIFI_PASSWORD   ""
#endif
#ifndef SNMP_COMMUNITY
  #define SNMP_COMMUNITY  ""
#endif
#ifndef SNMP_PORT
  #define SNMP_PORT       161
#endif
#ifndef MIKROTIK_IP
  #define MIKROTIK_IP     ""
#endif
#ifndef MT_USER
  #define MT_USER         ""
#endif
#ifndef MT_PASS
  #define MT_PASS         ""
#endif

#define MT_API_PORT     8728

#define DEFAULT_REFRESH_INTERVAL 5

// TFT_eSPI rotation 3 = landscape 320x240 (ST7789)
#define SCREEN_WIDTH    320
#define SCREEN_HEIGHT   240

// LCD ST7789
#define TFT_MOSI    13
#define TFT_MISO    12
#define TFT_SCLK    14
#define TFT_CS      15
#define TFT_DC       2
#define TFT_RST     -1
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
#define TOUCH_IRQ_PIN   36
#define TOUCH_SCLK      14
#define TOUCH_MOSI      13
#define TOUCH_MISO      12

// ==================== LAYOUT CONSTANTS ====================
#define HEADER_HEIGHT       30      // ~13% dari 240
#define FOOTER_HEIGHT       24      // 10% dari 240
#define BODY_HEIGHT         (SCREEN_HEIGHT - HEADER_HEIGHT - FOOTER_HEIGHT)  // 186px
#define BODY_Y              HEADER_HEIGHT
#define FOOTER_Y            (SCREEN_HEIGHT - FOOTER_HEIGHT)

// Grid 12 kolom
#define COL_W               (SCREEN_WIDTH / 12)  // ~26.67px
#define COL_LEFT_W          (3 * COL_W)          // 25% = 3 kolom = 80px
#define COL_MID_W           (6 * COL_W)          // 50% = 6 kolom = 160px
#define COL_RIGHT_W         (3 * COL_W)          // 25% = 3 kolom = 80px

#define COL_LEFT_X          0
#define COL_MID_X           COL_LEFT_W
#define COL_RIGHT_X         (COL_LEFT_W + COL_MID_W)

// Card spacing
#define CARD_MARGIN         4
#define CARD_PADDING        4
#define CARD_RADIUS         4

// Chart
#define CHART_HEIGHT        100
#define CHART_Y             (BODY_Y + 4)
#define CHART_W             (COL_MID_W - 8)
#define CHART_X             (COL_MID_X + 4)

// ==================== COLOR PALETTE ====================
// Dark Cyber Network Dashboard
// Deep navy-purple + neon blue/cyan accent + glassmorphism panels
#define COLOR_BG            0x1108      // = kartu glass (senada)
#define COLOR_BG2           0x1108      // = kartu glass (gradient flat)
#define COLOR_CARD          0x1108      // #182449 - kartu glass dark navy
#define COLOR_CARD_BORDER   0x29ED      // #2a3f6e - border biru halus (glass edge)
#define COLOR_HEADER        0x1108      // = kartu glass (senada)
#define COLOR_FOOTER        0x1108

// Text Colors
#define COLOR_TEXT_TITLE    0xFFFF      // #FFFFFF - Putih judul
#define COLOR_TEXT_VALUE    0xEFFF      // #E8FFFE - putih kecyan
#define COLOR_TEXT_LABEL    0x84D7      // #8a9cc0 - abu kebiruan
#define COLOR_TEXT_MUTED    0x5331      // #54668c - abu gelap

// Status Colors
#define COLOR_GREEN         0x07E0      // #00E676 - hijau neon (Up/sehat)
#define COLOR_AMBER         0xFCC0      // #FF9800 - amber (warning)
#define COLOR_RED           0xF800      // #FF1744 - merah neon (kritis)
#define COLOR_ACCENT        0x07FF      // #00E5FF - ELECTRIC CYAN (aksen utama)
#define COLOR_ACCENT2       0x7800      // #F000 - neon magenta (aksen sekunder)
#define COLOR_NEON_BLUE     0x001F      // #0039CB - neon biru tua

// Chart Colors
#define CHART_TX_COLOR      0xFFE0      // kuning (TX)
#define CHART_TX_FILL       0x9420      // olive redup (isi area TX)
#define CHART_RX_COLOR      0xF800      // merah (RX)
#define CHART_RX_FILL       0x9000      // marun redup (isi area RX)
#define CHART_EDGE_COLOR    0x4A69      // abu tua (garis tepi)

// Chart Grid
#define CHART_GRID_COLOR    0x0928      // #102848 - grid gelap

// Card Status Colors (sama, neon variants)
#define CARD_CPU_NORMAL     0x07E0
#define CARD_CPU_WARN       0xFCC0
#define CARD_CPU_CRIT       0xF800
#define CARD_MEM_NORMAL     0x07E0
#define CARD_MEM_WARN       0xFCC0
#define CARD_MEM_CRIT       0xF800

// ==================== FONT SIZES ====================
#define FONT_SIZE_LABEL     1      // 12pt equivalent (size 1 = 8px base)
#define FONT_SIZE_VALUE     3      // ~24pt equivalent (size 3 = 24px)
#define FONT_SIZE_BUTTON    2      // ~16pt equivalent
#define FONT_SIZE_CHART_LABEL 1    // 12pt

// Chart data points
#define CHART_MAX_POINTS    60     // 60 points = 60 seconds at 1s interval

// Touch
#define TOUCH_DEBOUNCE_MS   350
#define SWIPE_THRESHOLD     30

// ==================== THEME TYPE ====================
struct Theme {
  uint16_t bg, header, card, text, dim, border, bg2;
};

#endif