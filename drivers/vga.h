#ifndef VGA_H
#define VGA_H

// =============================================================================
//  vga.h — VGA Text Mode Driver
//  Writes directly to VGA framebuffer at 0xB8000
//  Each character = 2 bytes: [char][color]
//  Color byte: high nibble = background, low nibble = foreground
// =============================================================================

#define VGA_ADDRESS  0xB8000
#define VGA_COLS     80
#define VGA_ROWS     25

// Colors
#define VGA_BLACK        0x0
#define VGA_BLUE         0x1
#define VGA_GREEN        0x2
#define VGA_CYAN         0x3
#define VGA_RED          0x4
#define VGA_MAGENTA      0x5
#define VGA_BROWN        0x6
#define VGA_WHITE        0x7
#define VGA_BRIGHT_WHITE 0xF
#define VGA_BRIGHT_CYAN  0xB
#define VGA_BRIGHT_GREEN 0xA
#define VGA_YELLOW       0xE

#define VGA_COLOR(bg, fg) ((bg << 4) | fg)

void vga_init();
void vga_clear(unsigned char color);
void vga_putchar(char c, unsigned char color, int x, int y);
void vga_print(const char *str, unsigned char color, int x, int *y);
void vga_print_at(const char *str, unsigned char color, int x, int y);

#endif
