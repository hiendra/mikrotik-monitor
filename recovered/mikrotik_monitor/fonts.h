// ============================================================
// fonts.h - Font FreeSans proportional untuk semua menu
// Include guard wajib karena dipakai dari .ino dan keyboard.h
// Catatan: gfxfont.h (via TFT_eSPI.h + LOAD_GFXFF) sudah
// meng-include semua font FreeSans — di sini cukup deklarasikan.
// ============================================================
#ifndef FONTS_H
#define FONTS_H

#include <TFT_eSPI.h>

const GFXfont* FONT_XS = &FreeSans9pt7b;          // label halus
const GFXfont* FONT_SM = &FreeSans9pt7b;          // teks kecil (non-bold)
const GFXfont* FONT_MD = &FreeSans12pt7b;         // nilai statistik
const GFXfont* FONT_LG = &FreeSans18pt7b;         // judul halaman
const GFXfont* FONT_ITAL = &FreeSansOblique9pt7b; // judul header (miring)

#endif