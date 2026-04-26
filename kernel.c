#include "kernel.h"
#include "../drivers/gfx.h"

typedef enum {
    SCREEN_BOOT,
    SCREEN_HOME,
    SCREEN_FITNESS,
    SCREEN_HEART,
    SCREEN_NOTIFS,
    SCREEN_SETTINGS,
    SCREEN_APPS,
    SCREEN_STOPWATCH,
    SCREEN_MUSIC,
    SCREEN_WEATHER,
    SCREEN_MAPS,
    SCREEN_COUNT
} watch_screen_t;

typedef struct {
    int steps;
    int calories;
    int active_min;
    int distance_10m;
    int bpm;
    int battery;
    int brightness;
    int bluetooth;
    int wifi;
    int dnd;
    int aod;
    int stopwatch_ticks;
    int stopwatch_running;
    int music_playing;
    int music_pos;
    int music_track;
    unsigned int ticks;
    watch_screen_t screen;
} watch_state_t;

static watch_state_t os;

static void outb(unsigned short port, unsigned char value) {
    __asm__ volatile("outb %0, %1" : : "a"(value), "Nd"(port));
}

static unsigned char inb(unsigned short port) {
    unsigned char value;
    __asm__ volatile("inb %1, %0" : "=a"(value) : "Nd"(port));
    return value;
}

static void serial_init(void) {
    outb(0x3F8 + 1, 0x00);
    outb(0x3F8 + 3, 0x80);
    outb(0x3F8 + 0, 0x03);
    outb(0x3F8 + 1, 0x00);
    outb(0x3F8 + 3, 0x03);
    outb(0x3F8 + 2, 0xC7);
    outb(0x3F8 + 4, 0x0B);
}

static void serial_write(const char *text) {
    while (*text) {
        outb(0x3F8, (unsigned char)*text++);
    }
}

static void delay(void) {
    for (volatile unsigned int i = 0; i < 900000; i++) {
        __asm__ volatile("nop");
    }
}

static void itoa2(int value, char *out) {
    out[0] = (char)('0' + ((value / 10) % 10));
    out[1] = (char)('0' + (value % 10));
    out[2] = 0;
}

static void itoa_dec(int value, char *out) {
    char tmp[12];
    int i = 0;
    int j = 0;
    if (value == 0) {
        out[0] = '0';
        out[1] = 0;
        return;
    }
    if (value < 0) {
        out[j++] = '-';
        value = -value;
    }
    while (value && i < 11) {
        tmp[i++] = (char)('0' + value % 10);
        value /= 10;
    }
    while (i > 0) {
        out[j++] = tmp[--i];
    }
    out[j] = 0;
}

static void init_state(void) {
    os.steps = 7842;
    os.calories = 426;
    os.active_min = 38;
    os.distance_10m = 57;
    os.bpm = 72;
    os.battery = 87;
    os.brightness = 70;
    os.bluetooth = 1;
    os.wifi = 1;
    os.dnd = 0;
    os.aod = 0;
    os.stopwatch_ticks = 0;
    os.stopwatch_running = 0;
    os.music_playing = 0;
    os.music_pos = 41;
    os.music_track = 0;
    os.ticks = 0;
    os.screen = SCREEN_BOOT;
}

static void update_backend(void) {
    os.ticks++;
    if ((os.ticks % 18) == 0) {
        os.steps += 3;
        os.calories = 420 + (os.steps / 180);
        os.active_min = 38 + ((int)os.ticks / 180);
        os.distance_10m = 55 + (os.steps / 900);
        os.bpm = 70 + (int)((os.ticks / 9) % 9);
        if (os.battery > 15 && (os.ticks % 360) == 0) {
            os.battery--;
        }
    }
    if (os.stopwatch_running) {
        os.stopwatch_ticks++;
    }
    if (os.music_playing && (os.ticks % 6) == 0) {
        os.music_pos++;
        if (os.music_pos > 214) {
            os.music_pos = 0;
            os.music_track = (os.music_track + 1) % 4;
        }
    }
    if (os.screen == SCREEN_BOOT && os.ticks > 80) {
        os.screen = SCREEN_HOME;
    }
}

static void next_screen(void) {
    if (os.screen == SCREEN_BOOT) os.screen = SCREEN_HOME;
    else os.screen = (watch_screen_t)((os.screen + 1) % SCREEN_COUNT);
    if (os.screen == SCREEN_BOOT) os.screen = SCREEN_HOME;
}

static void prev_screen(void) {
    if (os.screen <= SCREEN_HOME) os.screen = SCREEN_MAPS;
    else os.screen = (watch_screen_t)(os.screen - 1);
}

static void handle_keyboard(void) {
    while (inb(0x64) & 1) {
        unsigned char sc = inb(0x60);
        if (sc & 0x80) {
            continue;
        }
        switch (sc) {
            case 0x4D: next_screen(); break;       /* right */
            case 0x4B: prev_screen(); break;       /* left */
            case 0x2E: os.screen = SCREEN_APPS; break;      /* c */
            case 0x10: os.screen = SCREEN_HOME; break;      /* q */
            case 0x1F: os.stopwatch_running = !os.stopwatch_running; break; /* s */
            case 0x19: os.music_playing = !os.music_playing; break;         /* p */
            case 0x31: os.music_track = (os.music_track + 1) % 4; os.music_pos = 0; break; /* n */
            case 0x30: os.music_track = (os.music_track + 3) % 4; os.music_pos = 0; break; /* b */
            case 0x49: if (os.brightness < 100) os.brightness += 5; break;  /* pgup */
            case 0x51: if (os.brightness > 0) os.brightness -= 5; break;    /* pgdn */
            default: break;
        }
    }
}

static void draw_watch_shell(const char *title) {
    gfx_clear(C_BG);
    gfx_disc(160, 100, 96, C_SURFACE);
    gfx_circle(160, 100, 98, C_BORDER);
    gfx_circle(160, 100, 94, C_SURFACE2);
    gfx_text_center(160, 8, title, C_DIM, 1);

    char bat[8];
    itoa_dec(os.battery, bat);
    gfx_text(20, 10, "10:09", C_DIM, 1);
    gfx_rect_outline(265, 9, 28, 10, C_DIM);
    gfx_rect(267, 11, (os.battery * 24) / 100, 6,
             os.battery > 30 ? C_GREEN : C_AMBER);
    gfx_text(296, 10, bat, C_DIM, 1);
}

static void draw_boot(void) {
    gfx_clear(C_BG);
    gfx_disc(160, 100, 92, C_SURFACE);
    gfx_circle(160, 100, 94, C_CYAN);
    gfx_text_center(160, 62, "AJX", C_CYAN, 4);
    gfx_text_center(160, 104, "OS", C_CYAN, 4);
    gfx_text_center(160, 142, "V1.0.0-ALPHA", C_DIM, 1);
    gfx_rect(70, 165, 180, 4, C_SURFACE2);
    gfx_rect(70, 165, ((int)os.ticks * 180) / 80, 4, C_CYAN);
}

static void draw_hand(int angle, int len, unsigned char color) {
    static const int sx[12] = {0,25,43,50,43,25,0,-25,-43,-50,-43,-25};
    static const int sy[12] = {-50,-43,-25,0,25,43,50,43,25,0,-25,-43};
    int idx = angle % 12;
    gfx_line(160, 92, 160 + (sx[idx] * len) / 50,
             92 + (sy[idx] * len) / 50, color);
}

static void draw_home(void) {
    char buf[16];
    draw_watch_shell("HOME");
    gfx_circle(160, 92, 60, C_SURFACE2);
    gfx_circle(160, 92, 64, C_CYAN);
    for (int i = 0; i < 12; i++) {
        draw_hand(i, 60, i % 3 == 0 ? C_CYAN : C_DIM);
    }
    draw_hand(10, 34, C_TEXT);
    draw_hand(2, 48, C_CYAN);
    draw_hand((os.ticks / 8) % 12, 55, C_AMBER);
    gfx_disc(160, 92, 5, C_BG);
    gfx_circle(160, 92, 6, C_CYAN);

    gfx_rect(126, 156, 52, 16, C_SURFACE2);
    gfx_text_center(152, 161, "SAT 25 APR", C_DIM, 1);

    gfx_rect_outline(34, 165, 70, 25, C_BORDER);
    itoa_dec(os.steps, buf);
    gfx_text_center(69, 169, buf, C_TEXT, 1);
    gfx_text_center(69, 180, "STEPS", C_DIM, 1);

    gfx_rect_outline(125, 165, 70, 25, C_BORDER);
    itoa_dec(os.bpm, buf);
    gfx_text_center(160, 169, buf, C_RED, 1);
    gfx_text_center(160, 180, "BPM", C_DIM, 1);

    gfx_rect_outline(216, 165, 70, 25, C_BORDER);
    itoa_dec(os.calories, buf);
    gfx_text_center(251, 169, buf, C_AMBER, 1);
    gfx_text_center(251, 180, "KCAL", C_DIM, 1);
}

static void draw_fitness(void) {
    char buf[16];
    draw_watch_shell("ACTIVITY");
    gfx_circle(160, 92, 62, C_SURFACE2);
    gfx_circle(160, 92, 48, C_SURFACE2);
    gfx_circle(160, 92, 34, C_SURFACE2);
    gfx_arc_progress(160, 92, 62, os.steps / 100, C_GREEN);
    gfx_arc_progress(160, 92, 48, (os.calories * 100) / 600, C_RED);
    gfx_arc_progress(160, 92, 34, (os.active_min * 100) / 60, C_CYAN);
    itoa_dec(os.steps, buf);
    gfx_text_center(160, 86, buf, C_TEXT, 2);
    gfx_text_center(160, 106, "STEPS", C_DIM, 1);

    gfx_rect_outline(40, 154, 105, 28, C_BORDER);
    itoa_dec(os.calories, buf);
    gfx_text_center(92, 158, buf, C_TEXT, 1);
    gfx_text_center(92, 170, "KCAL", C_DIM, 1);

    gfx_rect_outline(176, 154, 105, 28, C_BORDER);
    itoa_dec(os.active_min, buf);
    gfx_text_center(228, 158, buf, C_TEXT, 1);
    gfx_text_center(228, 170, "ACTIVE MIN", C_DIM, 1);
}

static void draw_heart(void) {
    char buf[16];
    draw_watch_shell("HEART RATE");
    itoa_dec(os.bpm, buf);
    gfx_text_center(160, 64, buf, C_RED, 5);
    gfx_text_center(160, 112, "BPM", C_DIM, 2);
    int base = 140;
    for (int x = 35; x < 285; x += 8) {
        int spike = ((x + (int)os.ticks) % 48);
        int y = base;
        if (spike > 18 && spike < 24) y = base - 32;
        else if (spike >= 24 && spike < 28) y = base + 15;
        gfx_line(x, base, x + 7, y, C_RED);
    }
    gfx_rect_outline(30, 166, 58, 20, os.bpm < 60 ? C_RED : C_BORDER);
    gfx_text_center(59, 172, "REST", C_DIM, 1);
    gfx_rect_outline(95, 166, 58, 20, os.bpm < 80 ? C_RED : C_BORDER);
    gfx_text_center(124, 172, "FAT", C_DIM, 1);
    gfx_rect_outline(160, 166, 58, 20, os.bpm < 100 ? C_RED : C_BORDER);
    gfx_text_center(189, 172, "CARDIO", C_DIM, 1);
    gfx_rect_outline(225, 166, 58, 20, C_BORDER);
    gfx_text_center(254, 172, "PEAK", C_DIM, 1);
}

static void draw_settings(void) {
    char buf[16];
    draw_watch_shell("SETTINGS");
    gfx_rect_outline(45, 48, 90, 42, os.bluetooth ? C_CYAN : C_BORDER);
    gfx_text_center(90, 56, os.bluetooth ? "ON" : "OFF", C_CYAN, 2);
    gfx_text_center(90, 78, "BLUETOOTH", C_DIM, 1);
    gfx_rect_outline(185, 48, 90, 42, os.wifi ? C_CYAN : C_BORDER);
    gfx_text_center(230, 56, os.wifi ? "ON" : "OFF", C_CYAN, 2);
    gfx_text_center(230, 78, "WI-FI", C_DIM, 1);
    gfx_rect_outline(45, 102, 90, 42, os.dnd ? C_CYAN : C_BORDER);
    gfx_text_center(90, 110, os.dnd ? "ON" : "OFF", C_DIM, 2);
    gfx_text_center(90, 132, "DND", C_DIM, 1);
    gfx_rect_outline(185, 102, 90, 42, os.aod ? C_CYAN : C_BORDER);
    gfx_text_center(230, 110, os.aod ? "ON" : "OFF", C_DIM, 2);
    gfx_text_center(230, 132, "ALWAYS ON", C_DIM, 1);
    itoa_dec(os.brightness, buf);
    gfx_text_center(160, 158, "BRIGHTNESS", C_DIM, 1);
    gfx_rect(70, 174, 180, 6, C_SURFACE2);
    gfx_rect(70, 174, (os.brightness * 180) / 100, 6, C_AMBER);
    gfx_text(256, 171, buf, C_TEXT, 1);
}

static void draw_apps(void) {
    static const char *apps[9] = {
        "CLOCK", "FIT", "HEART", "MUSIC", "TIMER", "NOTIF", "SET", "WEATH", "MAPS"
    };
    draw_watch_shell("APPS");
    for (int i = 0; i < 9; i++) {
        int col = i % 3;
        int row = i / 3;
        int cx = 82 + col * 78;
        int cy = 54 + row * 44;
        gfx_disc(cx, cy, 18, C_SURFACE2);
        gfx_circle(cx, cy, 19, C_CYAN);
        gfx_text_center(cx, cy - 3, apps[i], C_TEXT, 1);
    }
    gfx_text_center(160, 181, "LEFT/RIGHT NAV  Q HOME", C_DIM, 1);
}

static void draw_weather(void) {
    draw_watch_shell("WEATHER");
    gfx_disc(160, 76, 28, C_AMBER);
    gfx_disc(179, 82, 18, C_SURFACE2);
    gfx_disc(143, 95, 18, C_SURFACE2);
    gfx_disc(164, 98, 24, C_SURFACE2);
    gfx_text_center(160, 122, "32 C", C_AMBER, 4);
    gfx_text_center(160, 155, "PARTLY CLOUDY", C_DIM, 1);
    gfx_text_center(160, 170, "NEW DELHI", C_TEXT, 1);
}

static void draw_maps(void) {
    draw_watch_shell("MAPS");
    gfx_rect_outline(48, 45, 224, 112, C_BORDER);
    for (int x = 78; x < 260; x += 36) gfx_line(x, 45, x, 156, C_SURFACE2);
    for (int y = 66; y < 150; y += 22) gfx_line(48, y, 271, y, C_SURFACE2);
    gfx_line(48, 122, 272, 78, C_CYAN);
    gfx_line(94, 45, 170, 156, C_DIM);
    gfx_disc(160, 101, 6, C_CYAN);
    gfx_circle(160, 101, 14, C_CYAN);
    gfx_text_center(160, 169, "CONNAUGHT PLACE", C_TEXT, 1);
    gfx_text_center(160, 182, "NEW DELHI", C_DIM, 1);
}

static void draw_music(void) {
    static const char *tracks[4] = {"MIDNIGHT", "LO-FI", "NEON", "SPACE"};
    draw_watch_shell("MUSIC");
    gfx_rect_outline(125, 48, 70, 55, C_BORDER);
    gfx_text_center(160, 66, "MUSIC", C_AMBER, 1);
    gfx_text_center(160, 86, tracks[os.music_track], C_TEXT, 1);
    gfx_text_center(160, 117, os.music_playing ? "PAUSE" : "PLAY", C_AMBER, 3);
    gfx_rect(60, 150, 200, 4, C_SURFACE2);
    gfx_rect(60, 150, (os.music_pos * 200) / 214, 4, C_AMBER);
    gfx_text_center(160, 174, "P PLAY  N NEXT  B PREV", C_DIM, 1);
}

static void draw_stopwatch(void) {
    char mm[4], ss[4];
    int total = os.stopwatch_ticks / 18;
    draw_watch_shell("STOPWATCH");
    itoa2((total / 60) % 60, mm);
    itoa2(total % 60, ss);
    gfx_text_center(126, 80, mm, C_TEXT, 5);
    gfx_text_center(160, 86, ":", C_CYAN, 4);
    gfx_text_center(194, 80, ss, C_TEXT, 5);
    gfx_disc(120, 145, 24, C_SURFACE2);
    gfx_circle(120, 145, 25, C_BORDER);
    gfx_text_center(120, 141, "LAP", C_DIM, 1);
    gfx_disc(200, 145, 24, C_SURFACE2);
    gfx_circle(200, 145, 25, os.stopwatch_running ? C_RED : C_GREEN);
    gfx_text_center(200, 141, os.stopwatch_running ? "STOP" : "START", C_TEXT, 1);
    gfx_text_center(160, 181, "S START/STOP", C_DIM, 1);
}

static void draw_notifs(void) {
    draw_watch_shell("NOTIFICATIONS");
    gfx_rect_outline(45, 54, 230, 30, C_BORDER);
    gfx_text(60, 62, "MSG  PROJECT BUILD OK", C_TEXT, 1);
    gfx_rect_outline(45, 94, 230, 30, C_BORDER);
    gfx_text(60, 102, "FIT  GOAL 78 PERCENT", C_GREEN, 1);
    gfx_rect_outline(45, 134, 230, 30, C_BORDER);
    gfx_text(60, 142, "BAT  87 PERCENT", C_AMBER, 1);
}

static void render(void) {
    switch (os.screen) {
        case SCREEN_BOOT: draw_boot(); break;
        case SCREEN_HOME: draw_home(); break;
        case SCREEN_FITNESS: draw_fitness(); break;
        case SCREEN_HEART: draw_heart(); break;
        case SCREEN_NOTIFS: draw_notifs(); break;
        case SCREEN_SETTINGS: draw_settings(); break;
        case SCREEN_APPS: draw_apps(); break;
        case SCREEN_STOPWATCH: draw_stopwatch(); break;
        case SCREEN_MUSIC: draw_music(); break;
        case SCREEN_WEATHER: draw_weather(); break;
        case SCREEN_MAPS: draw_maps(); break;
        default: draw_home(); break;
    }
}

void kernel_main(void) {
    serial_init();
    serial_write("AJXOS: graphics watch kernel reached\r\n");
    gfx_init_palette();
    init_state();

    for (;;) {
        handle_keyboard();
        update_backend();
        render();
        delay();
    }
}
