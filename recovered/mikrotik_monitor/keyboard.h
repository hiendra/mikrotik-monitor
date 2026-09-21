// ============================================================
// keyboard.h - On-Screen Keyboard untuk Touchscreen
// Menggunakan touch bawaan TFT_eSPI (bukan XPT2046_Touchscreen)
// Layout landscape 320x240
// ============================================================

#ifndef KEYBOARD_H
#define KEYBOARD_H

#include <TFT_eSPI.h>
#include "fonts.h"
#include "touch.h"

#define KB_MAX 63

struct KBKey {
  int16_t x, y, w, h;
  char value;
  const char* label;
  int type; // 0=char, 1=BACK, 2=OK, 3=CANCEL, 4=CLEAR
};

class Keyboard {
private:
  TFT_eSPI* tft;
  XPT2046* touch;
  bool visible = false;
  char buf[KB_MAX + 1];
  int len = 0;
  char title[40];
  bool isPassword = false;
  KBKey keys[60];
  int keyCount = 0;
  bool (*onOK)(const char*) = nullptr;
  void (*onCancel)() = nullptr;
  int kbY = 56;

  void addKey(int16_t x, int16_t y, int16_t w, int16_t h,
              char v, const char* l, int t) {
    if (keyCount >= 60) return;
    keys[keyCount] = {x, y, w, h, v, l, t};
    keyCount++;
  }

  void buildKeys() {
    keyCount = 0;
    int kw = 27, kh = 30, pad = 1, rowStep = 32;

    // Numbers row
    const char* nums = "1234567890.";
    for (unsigned int i = 0; i < strlen(nums); i++) {
      addKey(2 + i * (kw + pad), kbY, kw, kh, nums[i], "", 0);
    }

    // Row 1: qwertyuiop
    const char* r1 = "qwertyuiop";
    for (unsigned int i = 0; i < strlen(r1); i++) {
      addKey(2 + i * (kw + pad), kbY + rowStep, kw, kh, r1[i], "", 0);
    }

    // Row 2: asdfghjkl_
    const char* r2 = "asdfghjkl_";
    for (unsigned int i = 0; i < strlen(r2); i++) {
      addKey(2 + i * (kw + pad), kbY + rowStep * 2, kw, kh, r2[i], "", 0);
    }

    // Row 3: zxcvbnm -/@
    const char* r3 = "zxcvbnm-/@";
    for (unsigned int i = 0; i < strlen(r3); i++) {
      addKey(2 + i * (kw + pad), kbY + rowStep * 3, kw, kh, r3[i], "", 0);
    }

    // Action buttons
    addKey(2,    kbY + rowStep * 4, 60, kh, 0, "CLR",    4);
    addKey(66,   kbY + rowStep * 4, 60, kh, 0, "<-",     1);
    addKey(130,  kbY + rowStep * 4, 95, kh, 0, "CANCEL", 3);
    addKey(229,  kbY + rowStep * 4, 89, kh, 0, "OK",     2);
  }

  void draw() {
    tft->fillRect(0, 0, 320, 240, 0x0821);

    // Title
    tft->setFreeFont(FONT_XS);
    tft->setTextDatum(TL_DATUM);
    tft->setTextColor(0x07FF, 0x0821);
    tft->drawString(title, 4, 4);

    // Input field
    tft->fillRect(4, 18, 312, 26, 0x0000);
    tft->drawRect(4, 18, 312, 26, 0x07FF);
    tft->setFreeFont(FONT_MD);
    tft->setTextColor(0xFFFF, 0x0000);
    String disp;
    for (int i = 0; i < len; i++) disp += (isPassword ? "*" : String(buf[i]));
    tft->drawString(disp, 8, 21);
    int cw = tft->textWidth(disp);
    int cx = 8 + cw + 2;
    if (cx < 310) tft->fillRect(cx, 22, 2, 18, 0x07FF);

    tft->setFreeFont(FONT_XS);
    tft->setTextColor(0x8410, 0x0821);
    tft->drawString(String(len) + "/" + String(KB_MAX), 280, 48);

    // Draw keys
    for (int i = 0; i < keyCount; i++) {
      KBKey& k = keys[i];
      uint16_t bg, fg;
      if (k.type == 2)      { bg = 0x07E0; fg = 0x0000; }
      else if (k.type == 1) { bg = 0xF800; fg = 0xFFFF; }
      else if (k.type == 3) { bg = 0xFD20; fg = 0xFFFF; }
      else if (k.type == 4) { bg = 0xFFE0; fg = 0x0000; }
      else                  { bg = 0x3186; fg = 0xFFFF; }

      tft->fillRoundRect(k.x, k.y, k.w, k.h, 2, bg);

      tft->setFreeFont(FONT_MD);
      tft->setTextColor(fg, bg);
      String lab = (k.type == 0) ? String(k.value) : String(k.label);
      int twd = tft->textWidth(lab);
      int thh = tft->fontHeight();
      tft->drawString(lab, k.x + (k.w - twd) / 2, k.y + (k.h - thh) / 2);
    }
  }

  void refreshField() {
    tft->fillRect(4, 18, 312, 26, 0x0000);
    tft->drawRect(4, 18, 312, 26, 0x07FF);
    tft->setFreeFont(FONT_MD);
    tft->setTextColor(0xFFFF, 0x0000);
    String disp;
    for (int i = 0; i < len; i++) disp += (isPassword ? "*" : String(buf[i]));
    tft->drawString(disp, 8, 21);
    int cw = tft->textWidth(disp);
    int cx = 8 + cw + 2;
    if (cx < 310) tft->fillRect(cx, 22, 2, 18, 0x07FF);

    tft->setFreeFont(FONT_XS);
    tft->setTextColor(0x8410, 0x0821);
    tft->drawString(String(len) + "/" + String(KB_MAX), 280, 48);
  }

public:
  void init(TFT_eSPI* d, XPT2046* t) {
    tft = d;
    touch = t;
  }

  void show(const char* t, const char* cur, bool pwd,
            bool (*ok)(const char*), void (*cn)()) {
    strncpy(title, t, 39);
    title[39] = '\0';
    isPassword = pwd;
    onOK = ok;
    onCancel = cn;
    if (cur) {
      strncpy(buf, cur, KB_MAX);
      len = strlen(buf);
    } else {
      buf[0] = '\0';
      len = 0;
    }
    buildKeys();
    visible = true;
    draw();
  }

  // Panggil dari loop() — pakai tft.getTouch bawaan
  bool handleTouch() {
    if (!visible) return false;

    uint16_t x, y;
    if (!touch->getPoint(&x, &y)) return false;

    for (int i = 0; i < keyCount; i++) {
      KBKey& k = keys[i];
      if (x >= k.x && x <= k.x + k.w && y >= k.y && y <= k.y + k.h) {
        delay(80);

        if (k.type == 1) { // BACK
          if (len > 0) { len--; buf[len] = '\0'; refreshField(); }
        }
        else if (k.type == 2) { // OK
          buf[len] = '\0';
          visible = false;
          if (onOK) onOK(buf);
        }
        else if (k.type == 3) { // CANCEL
          visible = false;
          if (onCancel) onCancel();
        }
        else if (k.type == 4) { // CLEAR
          len = 0; buf[0] = '\0'; refreshField();
        }
        else if (k.type == 0 && len < KB_MAX) {
          buf[len++] = k.value;
          buf[len] = '\0';
          refreshField();
        }
        return true;
      }
    }
    return false;
  }

  bool isShowing() { return visible; }
};

#endif
