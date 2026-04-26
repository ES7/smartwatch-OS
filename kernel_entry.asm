[BITS 32]

section .text

extern _kernel_main

global start
start:
    mov esp, 0x90000
    mov word [0xB8000 + 168], 0x0A53
    call _kernel_main
    mov word [0xB8000 + 170], 0x0C58

.halt:
    cli
    hlt
    jmp .halt
