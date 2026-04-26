/* linker.ld - flat kernel loaded by the boot sector at 0x7E00 */

ENTRY(start)

SECTIONS {
    . = 0x7E00;

    .text BLOCK(1) : {
        *(.text)
        *(.text.*)
    }

    .rodata BLOCK(1) : {
        *(.rodata)
        *(.rdata)
        *(.rdata$*)
    }

    .data BLOCK(1) : {
        *(.data)
        *(.data.*)
    }

    .bss BLOCK(1) : {
        *(.bss)
        *(COMMON)
    }

    /DISCARD/ : {
        *(.comment)
        *(.eh_frame)
    }
}
