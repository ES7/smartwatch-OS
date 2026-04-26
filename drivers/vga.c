// =============================================================================
//  vga.c — VGA Text Mode Driver
// =============================================================================

#include "vga.h"

static unsigned short *vga_buf = (unsigned short *)VGA_ADDRESS;
static int cursor_x = 0;
static int cursor_y = 0;

void vga_init() {
    vga_clear(VGA_COLOR(VGA_BLACK, VGA_WHITE));
    cursor_x = 0;
    cursor_y = 0;
}

void vga_clear(unsigned char color) {
    unsigned short blank = (color << 8) | ' ';
    for (int i = 0; i < VGA_COLS * VGA_ROWS; i++) {
        vga_buf[i] = blank;
    }
    cursor_x = 0;
    cursor_y = 0;
}

void vga_putchar(char c, unsigned char color, int x, int y) {
    if (x < 0 || x >= VGA_COLS || y < 0 || y >= VGA_ROWS) {
        return;
    }
    vga_buf[y * VGA_COLS + x] = (color << 8) | (unsigned char)c;
}

void vga_print_at(const char *str, unsigned char color, int x, int y) {
    int cx = x;
    while (*str) {
        if (*str == '\n') {
            y++;
            cx = x;
        } else {
            if (cx >= VGA_COLS) {
                y++;
                cx = x;
            }
            vga_putchar(*str, color, cx, y);
            cx++;
        }
        str++;
    }
}

void vga_print(const char *str, unsigned char color, int x, int *y) {
    int cx = x;
    while (*str) {
        if (*str == '\n') {
            (*y)++;
            cx = x;
        } else {
            if (cx >= VGA_COLS) {
                (*y)++;
                cx = x;
            }
            vga_putchar(*str, color, cx, *y);
            cx++;
        }
        str++;
    }
}
