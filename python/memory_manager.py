# =============================================================================
#  memory_manager.py — Memory Manager
# =============================================================================
#
#  REAL OS CONCEPT:
#  Every OS needs to track RAM. When a process needs memory, it calls
#  malloc() — the kernel finds a free block and gives it. When done,
#  free() returns it. If a process dies without freeing, the kernel
#  reclaims it automatically (garbage collection at OS level).
#
#  Real watch RAM is tiny — 64KB to 512KB total. Every byte matters.
#  Our simulated RAM: 256KB, split into fixed-size blocks (like a real
#  embedded allocator). We use a bitmap to track which blocks are free.
#
#  Real embedded OSes use one of:
#    - First Fit   : give first block that's big enough
#    - Best Fit    : give smallest block that fits (reduces waste)
#    - Buddy System: split blocks in halves (Linux uses this)
#
#  We implement First Fit — simplest, fastest for small systems.
# =============================================================================

import threading
import time


# ── Constants ─────────────────────────────────────────────────────────────────

TOTAL_RAM_KB   = 256          # simulated RAM size
BLOCK_SIZE     = 64           # bytes per block (real: 8-32 bytes typically)
TOTAL_BLOCKS   = (TOTAL_RAM_KB * 1024) // BLOCK_SIZE   # 4096 blocks

# Memory regions — like real ARM Cortex-M memory map
REGION_KERNEL  = (0, 512)          # blocks 0-511    = kernel space (32KB)
REGION_STACK   = (512, 1024)       # blocks 512-1023 = process stacks (32KB)
REGION_HEAP    = (1024, 4096)      # blocks 1024-4095 = heap for malloc (192KB)


# ── Memory Block ──────────────────────────────────────────────────────────────

class MemBlock:
    """
    Represents one allocated chunk of memory.
    Like a malloc() return — tracks who owns it and how big.
    """
    _next_id = 1

    def __init__(self, pid, size, start_block, num_blocks, tag=""):
        self.alloc_id   = MemBlock._next_id
        MemBlock._next_id += 1
        self.pid        = pid          # which process owns this
        self.size       = size         # requested bytes
        self.start      = start_block  # first block index
        self.count      = num_blocks   # how many blocks used
        self.tag        = tag          # what it's for (debug label)
        self.allocated  = time.time()

    def __repr__(self):
        return (f"<MemBlock id={self.alloc_id} pid={self.pid} "
                f"tag='{self.tag}' size={self.size}B "
                f"blocks={self.start}-{self.start+self.count-1}>")


# ── Memory Manager ────────────────────────────────────────────────────────────

class MemoryManager:
    """
    Simulates an embedded memory allocator.

    Internally uses a bitmap — array of booleans where:
        False = block is FREE
        True  = block is USED

    Real OS: this bitmap itself lives in a protected kernel memory region.
    No user process can modify it directly — only kernel via malloc/free syscalls.
    """

    def __init__(self):
        # Bitmap: True = allocated, False = free
        # Only heap region is available for user allocation
        self._bitmap   = [False] * TOTAL_BLOCKS
        self._blocks   = {}    # alloc_id → MemBlock
        self._lock     = threading.Lock()
        self._pid_map  = {}    # pid → list of alloc_ids

        # Reserve kernel region permanently
        for i in range(REGION_KERNEL[0], REGION_KERNEL[1]):
            self._bitmap[i] = True

        # Reserve stack region permanently
        for i in range(REGION_STACK[0], REGION_STACK[1]):
            self._bitmap[i] = True

        self._heap_start = REGION_HEAP[0]
        self._heap_end   = REGION_HEAP[1]

    # ── malloc ────────────────────────────────────────────────────────────────
    #
    #  REAL OS CONCEPT:
    #  malloc(size) searches for a contiguous run of free blocks big enough.
    #  "First Fit" — scans from start, takes first gap that fits.
    #  Returns pointer to start of allocated region (we return alloc_id).

    def malloc(self, pid: int, size: int, tag: str = "") -> int:
        """
        Allocate `size` bytes for process `pid`.
        Returns alloc_id (like a pointer). Returns -1 if out of memory (OOM).
        """
        num_blocks = max(1, (size + BLOCK_SIZE - 1) // BLOCK_SIZE)  # ceiling div

        with self._lock:
            # First Fit search through heap region
            start = self._find_free_run(num_blocks)
            if start == -1:
                return -1   # OOM — Out of Memory

            # Mark blocks as used
            for i in range(start, start + num_blocks):
                self._bitmap[i] = True

            # Create block record
            block = MemBlock(pid, size, start, num_blocks, tag)
            self._blocks[block.alloc_id] = block

            # Track per-process allocations
            if pid not in self._pid_map:
                self._pid_map[pid] = []
            self._pid_map[pid].append(block.alloc_id)

            return block.alloc_id

    def _find_free_run(self, num_blocks: int) -> int:
        """
        First Fit algorithm.
        Scan bitmap for a contiguous run of `num_blocks` free blocks.
        Returns start index or -1.
        """
        count = 0
        start = -1
        for i in range(self._heap_start, self._heap_end):
            if not self._bitmap[i]:
                if start == -1:
                    start = i
                count += 1
                if count == num_blocks:
                    return start
            else:
                count = 0
                start = -1
        return -1

    # ── free ──────────────────────────────────────────────────────────────────
    #
    #  REAL OS CONCEPT:
    #  free(ptr) marks those blocks as available again.
    #  Real bug: "double free" — freeing same memory twice → corruption.
    #  Real bug: "use after free" — using memory after freeing → undefined behavior.

    def free(self, alloc_id: int) -> bool:
        """
        Free a previously allocated block.
        Returns True if freed, False if alloc_id not found (double-free protection).
        """
        with self._lock:
            if alloc_id not in self._blocks:
                return False   # double-free protection

            block = self._blocks.pop(alloc_id)

            # Mark blocks as free
            for i in range(block.start, block.start + block.count):
                self._bitmap[i] = False

            # Remove from pid map
            if block.pid in self._pid_map:
                self._pid_map[block.pid].discard(alloc_id) if hasattr(
                    self._pid_map[block.pid], 'discard') else None
                try:
                    self._pid_map[block.pid].remove(alloc_id)
                except ValueError:
                    pass

            return True

    # ── reclaim ───────────────────────────────────────────────────────────────
    #
    #  REAL OS CONCEPT:
    #  When a process is killed, kernel must reclaim ALL its memory.
    #  Otherwise dead processes leak memory forever — system eventually OOM.
    #  This is why even if your app crashes, your phone doesn't run out of RAM.

    def reclaim(self, pid: int) -> int:
        """
        Free all memory owned by a process. Called when process is killed.
        Returns total bytes reclaimed.
        """
        with self._lock:
            alloc_ids = list(self._pid_map.get(pid, []))

        total = 0
        for alloc_id in alloc_ids:
            block = self._blocks.get(alloc_id)
            if block:
                total += block.size
                self.free(alloc_id)

        if pid in self._pid_map:
            del self._pid_map[pid]

        return total

    # ── Stats & Inspection ────────────────────────────────────────────────────

    def stats(self) -> dict:
        """
        Memory usage statistics. Like /proc/meminfo in Linux.
        """
        with self._lock:
            heap_blocks = self._heap_end - self._heap_start
            used_blocks = sum(
                1 for i in range(self._heap_start, self._heap_end)
                if self._bitmap[i]
            )
            free_blocks = heap_blocks - used_blocks

        return {
            "total_kb":      TOTAL_RAM_KB,
            "kernel_kb":     (REGION_KERNEL[1] - REGION_KERNEL[0]) * BLOCK_SIZE // 1024,
            "stack_kb":      (REGION_STACK[1]  - REGION_STACK[0])  * BLOCK_SIZE // 1024,
            "heap_total_kb": heap_blocks  * BLOCK_SIZE // 1024,
            "heap_used_kb":  used_blocks  * BLOCK_SIZE // 1024,
            "heap_free_kb":  free_blocks  * BLOCK_SIZE // 1024,
            "used_pct":      round(used_blocks / heap_blocks * 100, 1),
            "alloc_count":   len(self._blocks),
        }

    def pid_usage(self, pid: int) -> dict:
        """How much memory is one process using?"""
        with self._lock:
            alloc_ids = self._pid_map.get(pid, [])
            blocks    = [self._blocks[a] for a in alloc_ids if a in self._blocks]

        return {
            "pid":        pid,
            "alloc_count": len(blocks),
            "total_bytes": sum(b.size for b in blocks),
            "allocations": [{"id": b.alloc_id, "size": b.size,
                             "tag": b.tag} for b in blocks],
        }

    def fragmentation(self) -> float:
        """
        Memory fragmentation percentage.
        High fragmentation = lots of small free gaps, can't fit large allocations
        even if total free memory is enough.
        Real OS: defragmentation or compaction fixes this.
        """
        with self._lock:
            # Count free runs
            runs = []
            count = 0
            for i in range(self._heap_start, self._heap_end):
                if not self._bitmap[i]:
                    count += 1
                else:
                    if count > 0:
                        runs.append(count)
                    count = 0
            if count > 0:
                runs.append(count)

        if not runs:
            return 0.0
        largest = max(runs)
        total   = sum(runs)
        # Fragmentation = 1 - (largest free run / total free)
        return round((1 - largest / total) * 100, 1) if total > 0 else 0.0

    def memmap(self, width: int = 64) -> str:
        """
        ASCII visualization of memory map. Like /proc/iomem.
        '.' = free, '#' = used, 'K' = kernel, 'S' = stack
        """
        out  = f"Memory Map ({TOTAL_RAM_KB}KB, each char = "
        out += f"{TOTAL_BLOCKS // width} blocks)\n"
        out += "┌" + "─" * width + "┐\n│"

        chars_per_cell = TOTAL_BLOCKS // width
        for col in range(width):
            start = col * chars_per_cell
            end   = start + chars_per_cell
            region_start = start

            if end <= REGION_KERNEL[1]:
                out += "K"
            elif end <= REGION_STACK[1]:
                out += "S"
            else:
                used = sum(1 for i in range(start, end) if self._bitmap[i])
                pct  = used / chars_per_cell
                out += "#" if pct > 0.5 else "░" if pct > 0 else "."

        out += "│\n└" + "─" * width + "┘\n"
        out += "K=kernel  S=stack  #=used  ░=partial  .=free\n"
        return out


# ── Global instance (initialized by kernel at boot) ───────────────────────────
mm = MemoryManager()
