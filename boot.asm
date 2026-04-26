; =============================================================================
;  boot.asm — AJXOS Bootloader
;  Kernel packed right after boot sector at 0x7E00. No disk read needed.
; =============================================================================

%ifndef KERNEL_SECTORS
%define KERNEL_SECTORS 16
%endif

[BITS 16]
[ORG 0x7C00]

start:
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7C00
    cld

    mov ah, 0x00          ; set 320x200 256-color graphics mode
    mov al, 0x13
    int 0x10

    mov [boot_drive], dl
    mov si, msg_boot
    call print_string

    mov al, 'L'
    mov bx, 160
    call mark_real_mode

    xor ax, ax
    mov es, ax
    mov bx, 0x7E00
    mov ah, 0x02          ; BIOS read sectors
    mov al, KERNEL_SECTORS
    mov ch, 0             ; cylinder 0
    mov cl, 2             ; sector 2
    mov dh, 0             ; head 0
    mov dl, [boot_drive]  ; boot drive
    int 0x13
    jc disk_error

    mov al, 'R'
    mov bx, 162
    call mark_real_mode

    cmp byte [0x7E00], 0xBC
    jne kernel_check_failed
    mov al, 'B'
    mov bx, 164
    call mark_real_mode

    cli
    mov al, 0xFF          ; mask all PIC interrupts
    out 0x21, al
    out 0xA1, al
    lgdt [gdt_desc]
    lidt [idt_desc]
    mov eax, cr0
    or  eax, 1
    mov cr0, eax
    jmp 0x08:protected_mode

print_string:
    mov ax, 0xB800
    mov es, ax
    xor di, di
.print_loop:
    lodsb
    or al, al
    jz .print_done
    mov ah, 0x0F
    mov [es:di], ax
    add di, 2
    jmp .print_loop
.print_done:
    ret

mark_real_mode:
    push ax
    push es
    mov ah, 0x0A
    push ax
    mov ax, 0xB800
    mov es, ax
    pop ax
    mov [es:bx], ax
    pop es
    pop ax
    ret

disk_error:
    mov si, msg_error
    call print_string
    hlt

kernel_check_failed:
    mov al, 'E'
    mov bx, 164
    call mark_real_mode
    hlt

msg_boot db 'AJXOS Bootloader v1.0', 0x0D, 0x0A, 0
msg_error db 'Error: failed to load kernel', 0x0D, 0x0A, 0
boot_drive db 0

gdt_start:
    dq 0x0000000000000000
    dw 0xFFFF, 0x0000
    db 0x00, 10011010b, 11001111b, 0x00
    dw 0xFFFF, 0x0000
    db 0x00, 10010010b, 11001111b, 0x00
gdt_end:

gdt_desc:
    dw gdt_end - gdt_start - 1
    dd gdt_start

idt_start:
    times 8*8 db 0          ; entries 0-7 empty
    dw int8_handler
    dw 0x0008
    db 0
    db 10001110b            ; present, DPL=0, 32-bit interrupt gate
    dw 0
idt_end:

idt_desc:
    dw idt_end - idt_start - 1
    dd idt_start

[BITS 32]
protected_mode:
    mov ax, 0x10
    mov ds, ax
    mov ss, ax
    mov es, ax
    mov fs, ax
    mov gs, ax
    mov esp, 0x90000
    mov word [0xB8000 + 166], 0x0A50
    cli
    jmp 0x08:0x7E00

int8_handler:
    cli
.halt_loop:
    hlt
    jmp .halt_loop

times 510-($-$$) db 0
dw 0xAA55
