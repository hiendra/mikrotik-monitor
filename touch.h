// ============================================================
// touch.h - XPT2046 touch reader bypassing TFT_eSPI buggy
// getTouch()/getTouchRawZ() (which use transfer16).
// Uses 8-bit SPI transfers only - proven working on this board.
// Shared bus: SCLK=14, MISO=12, MOSI=13, CS=33.
//
// Calibration derived from 3x3 grid (tftdiag12):
//   screenX = -0.0900*rawX + 343.96
//   screenY = -0.0659*rawY + 256.34
// Max error: 4.5px X, 7.3px Y on 320x240.
// ============================================================
#ifndef TOUCH_H
#define TOUCH_H

#include <TFT_eSPI.h>

#define TOUCH_CS_PIN 33
#define TS_SPI_SPEED 2000000
#define TOUCH_Z_THRESHOLD 350

class XPT2046 {
public:
  void begin(TFT_eSPI *d) {
    tft = d;
    pinMode(TOUCH_CS_PIN, OUTPUT);
    digitalWrite(TOUCH_CS_PIN, HIGH);
  }

  // Raw pressure (Z). Pressed when greater than ~350.
  uint16_t readZ() {
    SPIClass &spi = tft->getSPIinstance();
    int16_t tz = 0xFFF;
    digitalWrite(TOUCH_CS_PIN, LOW);
    spi.beginTransaction(SPISettings(TS_SPI_SPEED, MSBFIRST, SPI_MODE0));
    spi.transfer(0xb0);
    uint16_t v1 = ((uint16_t)spi.transfer(0x00) << 8) | spi.transfer(0xc0);
    uint16_t v2 = ((uint16_t)spi.transfer(0x00) << 8) | spi.transfer(0x00);
    tz += (int16_t)(v1 >> 3);
    tz -= (int16_t)(v2 >> 3);
    spi.endTransaction();
    digitalWrite(TOUCH_CS_PIN, HIGH);
    if (tz == 4095) tz = 0;
    return (uint16_t)tz;
  }

  // Raw X/Y (mirror of TFT_eSPI getTouchRaw, 8-bit transfers)
  void readRawXY(uint16_t *x, uint16_t *y) {
    SPIClass &spi = tft->getSPIinstance();
    digitalWrite(TOUCH_CS_PIN, LOW);
    spi.beginTransaction(SPISettings(TS_SPI_SPEED, MSBFIRST, SPI_MODE0));
    spi.transfer(0xd0); spi.transfer(0);
    spi.transfer(0xd0); spi.transfer(0);
    spi.transfer(0xd0); spi.transfer(0);
    spi.transfer(0xd0);
    uint16_t tmp = (uint16_t)spi.transfer(0) << 8;
    tmp |= spi.transfer(0x90);
    *x = (tmp >> 3) & 0x0FFF;
    spi.transfer(0); spi.transfer(0x90);
    spi.transfer(0); spi.transfer(0x90);
    spi.transfer(0); spi.transfer(0x90);
    tmp = (uint16_t)spi.transfer(0) << 8;
    tmp |= spi.transfer(0);
    *y = (tmp >> 3) & 0x0FFF;
    spi.endTransaction();
    digitalWrite(TOUCH_CS_PIN, HIGH);
  }

  // Affine mapping to screen coords (calibrated)
  void convert(uint16_t *x, uint16_t *y) {
    *x = (uint16_t)constrain((int)(-0.0900f * *x + 343.96f), 0, 319);
    *y = (uint16_t)constrain((int)(-0.0659f * *y + 256.34f), 0, 239);
  }

  // Pressed? If true, x/y are screen coordinates.
  bool getPoint(uint16_t *x, uint16_t *y, uint16_t threshold = TOUCH_Z_THRESHOLD) {
    if (readZ() <= threshold) return false;
    readRawXY(x, y);
    convert(x, y);
    return true;
  }

private:
  TFT_eSPI *tft = nullptr;
};

#endif