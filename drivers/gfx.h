#ifndef GFX_H
#define GFX_H

#define GFX_WIDTH  320
#define GFX_HEIGHT 200
#define GFX_BUFFER 0xA0000

#define C_BG       0x00
#define C_SURFACE  0x01
#define C_SURFACE2 0x08
#define C_BORDER   0x09
#define C_CYAN     0x0B
#define C_AMBER    0x0E
#define C_RED      0x0C
#define C_GREEN    0x0A
#define C_TEXT     0x0F
#define C_DIM      0x07
#define C_WHITE    0x0F

void gfx_clear(unsigned char color);
void gfx_init_palette(void);
void gfx_pixel(int x, int y, unsigned char color);
void gfx_line(int x0, int y0, int x1, int y1, unsigned char color);
void gfx_rect(int x, int y, int w, int h, unsigned char color);
void gfx_rect_outline(int x, int y, int w, int h, unsigned char color);
void gfx_circle(int cx, int cy, int r, unsigned char color);
void gfx_disc(int cx, int cy, int r, unsigned char color);
void gfx_arc_progress(int cx, int cy, int r, int percent, unsigned char color);
void gfx_char(int x, int y, char ch, unsigned char color, int scale);
void gfx_text(int x, int y, const char *text, unsigned char color, int scale);
void gfx_text_center(int cx, int y, const char *text, unsigned char color, int scale);

#endif
