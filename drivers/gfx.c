#include "gfx.h"

static unsigned char *fb = (unsigned char *)GFX_BUFFER;

static void outb(unsigned short port, unsigned char value) {
    __asm__ volatile("outb %0, %1" : : "a"(value), "Nd"(port));
}

static void pal(unsigned char idx, unsigned char r, unsigned char g, unsigned char b) {
    outb(0x3C8, idx);
    outb(0x3C9, r);
    outb(0x3C9, g);
    outb(0x3C9, b);
}

void gfx_init_palette(void) {
    pal(C_BG,       2,  3,  4);
    pal(C_SURFACE,  4,  7, 11);
    pal(C_SURFACE2, 7, 10, 17);
    pal(C_BORDER,  12, 18, 25);
    pal(C_CYAN,     0, 57, 63);
    pal(C_AMBER,   63, 44,  0);
    pal(C_RED,     63, 18, 28);
    pal(C_GREEN,    0, 58, 30);
    pal(C_TEXT,    58, 62, 63);
    pal(C_DIM,     26, 31, 39);
}

void gfx_clear(unsigned char color) {
    for (int i = 0; i < GFX_WIDTH * GFX_HEIGHT; i++) {
        fb[i] = color;
    }
}

void gfx_pixel(int x, int y, unsigned char color) {
    if (x < 0 || x >= GFX_WIDTH || y < 0 || y >= GFX_HEIGHT) {
        return;
    }
    fb[y * GFX_WIDTH + x] = color;
}

void gfx_line(int x0, int y0, int x1, int y1, unsigned char color) {
    int dx = x1 > x0 ? x1 - x0 : x0 - x1;
    int sx = x0 < x1 ? 1 : -1;
    int dy = y1 > y0 ? y0 - y1 : y1 - y0;
    int sy = y0 < y1 ? 1 : -1;
    int err = dx + dy;

    for (;;) {
        gfx_pixel(x0, y0, color);
        if (x0 == x1 && y0 == y1) {
            break;
        }
        int e2 = err * 2;
        if (e2 >= dy) {
            err += dy;
            x0 += sx;
        }
        if (e2 <= dx) {
            err += dx;
            y0 += sy;
        }
    }
}

void gfx_rect(int x, int y, int w, int h, unsigned char color) {
    for (int yy = 0; yy < h; yy++) {
        for (int xx = 0; xx < w; xx++) {
            gfx_pixel(x + xx, y + yy, color);
        }
    }
}

void gfx_rect_outline(int x, int y, int w, int h, unsigned char color) {
    gfx_line(x, y, x + w - 1, y, color);
    gfx_line(x, y + h - 1, x + w - 1, y + h - 1, color);
    gfx_line(x, y, x, y + h - 1, color);
    gfx_line(x + w - 1, y, x + w - 1, y + h - 1, color);
}

void gfx_circle(int cx, int cy, int r, unsigned char color) {
    int x = r;
    int y = 0;
    int err = 0;

    while (x >= y) {
        gfx_pixel(cx + x, cy + y, color);
        gfx_pixel(cx + y, cy + x, color);
        gfx_pixel(cx - y, cy + x, color);
        gfx_pixel(cx - x, cy + y, color);
        gfx_pixel(cx - x, cy - y, color);
        gfx_pixel(cx - y, cy - x, color);
        gfx_pixel(cx + y, cy - x, color);
        gfx_pixel(cx + x, cy - y, color);
        y++;
        if (err <= 0) {
            err += 2 * y + 1;
        }
        if (err > 0) {
            x--;
            err -= 2 * x + 1;
        }
    }
}

void gfx_disc(int cx, int cy, int r, unsigned char color) {
    for (int y = -r; y <= r; y++) {
        for (int x = -r; x <= r; x++) {
            if (x * x + y * y <= r * r) {
                gfx_pixel(cx + x, cy + y, color);
            }
        }
    }
}

void gfx_arc_progress(int cx, int cy, int r, int percent, unsigned char color) {
    if (percent < 0) percent = 0;
    if (percent > 100) percent = 100;
    int points = (percent * 64) / 100;
    int x = 0;
    int y = -r;
    for (int i = 0; i <= points; i++) {
        int px = cx + x;
        int py = cy + y;
        gfx_disc(px, py, 2, color);

        int nx = x - (y / 8);
        int ny = y + (x / 8);
        x = nx;
        y = ny;
        int mag = x * x + y * y;
        if (mag > 0) {
            while (x * x + y * y > r * r + r) {
                if (x > 0) x--; else if (x < 0) x++;
                if (y > 0) y--; else if (y < 0) y++;
            }
        }
    }
}

static const unsigned char *glyph_for(char ch) {
    static const unsigned char space[7] = {0,0,0,0,0,0,0};
    static const unsigned char colon[7] = {0,4,4,0,4,4,0};
    static const unsigned char dash[7] = {0,0,0,31,0,0,0};
    static const unsigned char slash[7] = {1,2,2,4,8,8,16};
    static const unsigned char dot[7] = {0,0,0,0,0,12,12};
    static const unsigned char pct[7] = {17,18,4,8,19,19,0};
    static const unsigned char zero[7] = {14,17,19,21,25,17,14};
    static const unsigned char one[7] = {4,12,4,4,4,4,14};
    static const unsigned char two[7] = {14,17,1,2,4,8,31};
    static const unsigned char three[7] = {30,1,1,14,1,1,30};
    static const unsigned char four[7] = {2,6,10,18,31,2,2};
    static const unsigned char five[7] = {31,16,30,1,1,17,14};
    static const unsigned char six[7] = {6,8,16,30,17,17,14};
    static const unsigned char seven[7] = {31,1,2,4,8,8,8};
    static const unsigned char eight[7] = {14,17,17,14,17,17,14};
    static const unsigned char nine[7] = {14,17,17,15,1,2,12};
    static const unsigned char A[7] = {14,17,17,31,17,17,17};
    static const unsigned char B[7] = {30,17,17,30,17,17,30};
    static const unsigned char C[7] = {14,17,16,16,16,17,14};
    static const unsigned char D[7] = {30,17,17,17,17,17,30};
    static const unsigned char E[7] = {31,16,16,30,16,16,31};
    static const unsigned char F[7] = {31,16,16,30,16,16,16};
    static const unsigned char G[7] = {14,17,16,23,17,17,15};
    static const unsigned char H[7] = {17,17,17,31,17,17,17};
    static const unsigned char I[7] = {14,4,4,4,4,4,14};
    static const unsigned char J[7] = {7,2,2,2,18,18,12};
    static const unsigned char K[7] = {17,18,20,24,20,18,17};
    static const unsigned char L[7] = {16,16,16,16,16,16,31};
    static const unsigned char M[7] = {17,27,21,21,17,17,17};
    static const unsigned char N[7] = {17,25,21,19,17,17,17};
    static const unsigned char O[7] = {14,17,17,17,17,17,14};
    static const unsigned char P[7] = {30,17,17,30,16,16,16};
    static const unsigned char Q[7] = {14,17,17,17,21,18,13};
    static const unsigned char R[7] = {30,17,17,30,20,18,17};
    static const unsigned char S[7] = {15,16,16,14,1,1,30};
    static const unsigned char T[7] = {31,4,4,4,4,4,4};
    static const unsigned char U[7] = {17,17,17,17,17,17,14};
    static const unsigned char V[7] = {17,17,17,17,17,10,4};
    static const unsigned char W[7] = {17,17,17,21,21,21,10};
    static const unsigned char X[7] = {17,17,10,4,10,17,17};
    static const unsigned char Y[7] = {17,17,10,4,4,4,4};
    static const unsigned char Z[7] = {31,1,2,4,8,16,31};

    if (ch >= 'a' && ch <= 'z') ch -= 32;
    switch (ch) {
        case '0': return zero; case '1': return one; case '2': return two;
        case '3': return three; case '4': return four; case '5': return five;
        case '6': return six; case '7': return seven; case '8': return eight;
        case '9': return nine; case 'A': return A; case 'B': return B;
        case 'C': return C; case 'D': return D; case 'E': return E;
        case 'F': return F; case 'G': return G; case 'H': return H;
        case 'I': return I; case 'J': return J; case 'K': return K;
        case 'L': return L; case 'M': return M; case 'N': return N;
        case 'O': return O; case 'P': return P; case 'Q': return Q;
        case 'R': return R; case 'S': return S; case 'T': return T;
        case 'U': return U; case 'V': return V; case 'W': return W;
        case 'X': return X; case 'Y': return Y; case 'Z': return Z;
        case ':': return colon; case '-': return dash; case '/': return slash;
        case '.': return dot; case '%': return pct; default: return space;
    }
}

void gfx_char(int x, int y, char ch, unsigned char color, int scale) {
    const unsigned char *g = glyph_for(ch);
    for (int row = 0; row < 7; row++) {
        for (int col = 0; col < 5; col++) {
            if (g[row] & (1 << (4 - col))) {
                gfx_rect(x + col * scale, y + row * scale, scale, scale, color);
            }
        }
    }
}

void gfx_text(int x, int y, const char *text, unsigned char color, int scale) {
    int cx = x;
    while (*text) {
        gfx_char(cx, y, *text, color, scale);
        cx += 6 * scale;
        text++;
    }
}

static int text_width(const char *text, int scale) {
    int n = 0;
    while (text[n]) n++;
    return n * 6 * scale;
}

void gfx_text_center(int cx, int y, const char *text, unsigned char color, int scale) {
    gfx_text(cx - text_width(text, scale) / 2, y, text, color, scale);
}
