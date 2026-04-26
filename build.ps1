param(
    [switch]$Run,
    [switch]$Headless,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$BuildDir = "build"
$Image = "ajxos.img"

if ($Clean) {
    if (Test-Path $BuildDir) {
        Remove-Item -Recurse -Force $BuildDir
    }
    if (Test-Path $Image) {
        Remove-Item -Force $Image
    }
    exit 0
}

New-Item -ItemType Directory -Force $BuildDir | Out-Null

$gccFlags = @(
    "-m32",
    "-ffreestanding",
    "-fno-stack-protector",
    "-fno-builtin",
    "-fno-pic",
    "-fno-asynchronous-unwind-tables",
    "-nostdlib",
    "-nostdinc",
    "-Wall",
    "-Wextra",
    "-c"
)

nasm -f win32 boot/kernel_entry.asm -o "$BuildDir/kernel_entry.o"
gcc @gccFlags kernel/kernel.c -o "$BuildDir/kernel.o"
gcc @gccFlags drivers/vga.c -o "$BuildDir/vga.o"
gcc @gccFlags drivers/gfx.c -o "$BuildDir/gfx.o"
ld -m i386pe -T linker.ld "$BuildDir/kernel_entry.o" "$BuildDir/kernel.o" "$BuildDir/vga.o" "$BuildDir/gfx.o" -o "$BuildDir/kernel.pe"
objcopy -O binary "$BuildDir/kernel.pe" "$BuildDir/kernel.bin"

$kernelSize = (Get-Item "$BuildDir/kernel.bin").Length
$kernelSectors = [Math]::Ceiling($kernelSize / 512)
if ($kernelSectors -gt 127) {
    throw "Kernel is $kernelSectors sectors; this tiny bootloader supports up to 127 sectors."
}

nasm -f bin "-DKERNEL_SECTORS=$kernelSectors" boot/boot.asm -o "$BuildDir/boot.bin"

$bootBytes = [IO.File]::ReadAllBytes((Resolve-Path "$BuildDir/boot.bin"))
$kernelBytes = [IO.File]::ReadAllBytes((Resolve-Path "$BuildDir/kernel.bin"))
$paddedKernelSize = $kernelSectors * 512
$paddedKernel = New-Object byte[] $paddedKernelSize
[Array]::Copy($kernelBytes, $paddedKernel, $kernelBytes.Length)
$imageBytes = $bootBytes + $paddedKernel
$floppySize = 1474560
if ($imageBytes.Length -lt $floppySize) {
    $floppyImage = New-Object byte[] $floppySize
    [Array]::Copy($imageBytes, $floppyImage, $imageBytes.Length)
    $imageBytes = $floppyImage
}
[IO.File]::WriteAllBytes((Join-Path (Get-Location) $Image), $imageBytes)

Write-Host "Build complete: $Image"
Write-Host "Kernel size: $kernelSize bytes ($kernelSectors sectors)"

if ($Run) {
    if ($Headless) {
        qemu-system-i386 -drive "file=$Image,format=raw,if=floppy" -boot a -m 32M -display none -serial file:serial.log -no-reboot -no-shutdown
    } else {
        qemu-system-i386 -drive "file=$Image,format=raw,if=floppy" -boot a -m 32M -serial file:serial.log
    }
}
