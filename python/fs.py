# =============================================================================
#  fs.py — Virtual File System (VFS)
# =============================================================================
#
#  REAL OS CONCEPT:
#  Every OS needs a filesystem — a way to organize and persist data.
#  Real watch OSes use FAT32 or LittleFS (designed for flash memory).
#
#  The VFS layer is an abstraction above the actual storage format.
#  Apps call open("/data/steps.db") and the VFS figures out which
#  physical driver and filesystem format to use underneath.
#
#  Linux VFS: open() → sys_open() → vfs_open() → ext4_open() → disk
#  Our VFS:   open() → VFS.open() → MemFS.open() → dict in RAM
#
#  We implement a simple in-memory filesystem (like a RAM disk).
#  You could extend this to write to actual files on disk.
# =============================================================================

import time
import json


# ── Inode ────────────────────────────────────────────────────────────────────
#
#  REAL OS CONCEPT:
#  An inode (index node) stores metadata about a file:
#  size, permissions, timestamps, and pointer to data blocks.
#  The filename is stored in the directory, not the inode.
#  This is why you can have hard links — multiple names, one inode.

class Inode:
    _next_id = 1

    def __init__(self, name, is_dir=False):
        self.inode_id  = Inode._next_id
        Inode._next_id += 1
        self.name      = name
        self.is_dir    = is_dir
        self.data      = {} if is_dir else b""   # dir: {name→inode}, file: bytes
        self.size      = 0
        self.created   = time.time()
        self.modified  = time.time()
        self.mode      = 0o644   # Unix-style permissions (owner rw, others r)

    def __repr__(self):
        t = "DIR" if self.is_dir else "FILE"
        return f"<Inode {self.inode_id} {t} '{self.name}' {self.size}B>"


# ── File Descriptor ───────────────────────────────────────────────────────────
#
#  REAL OS CONCEPT:
#  When a process opens a file, the kernel gives it a file descriptor (fd) —
#  just an integer (0, 1, 2, 3...). The kernel maintains a table mapping
#  fd numbers to open file state (which inode, current position, read/write mode).
#  fd 0 = stdin, fd 1 = stdout, fd 2 = stderr (always reserved).

class FileDescriptor:
    def __init__(self, inode, mode="r"):
        self.inode    = inode
        self.mode     = mode
        self.position = 0     # like lseek position

    def read(self, size=-1) -> bytes:
        if self.inode.is_dir:
            raise OSError("Is a directory")
        data = self.inode.data
        if size == -1:
            result = data[self.position:]
        else:
            result = data[self.position:self.position + size]
        self.position += len(result)
        return result

    def write(self, data: bytes):
        if "r" == self.mode and "w" not in self.mode:
            raise PermissionError("File not open for writing")
        if self.inode.is_dir:
            raise OSError("Is a directory")
        # Insert at position (like real file write)
        old = self.inode.data
        self.inode.data = old[:self.position] + data + old[self.position + len(data):]
        self.position += len(data)
        self.inode.size     = len(self.inode.data)
        self.inode.modified = time.time()

    def seek(self, offset, whence=0):
        if whence == 0:   self.position = offset
        elif whence == 1: self.position += offset
        elif whence == 2: self.position = self.inode.size + offset

    def tell(self) -> int:
        return self.position


# ── In-Memory Filesystem ──────────────────────────────────────────────────────

class MemFS:
    """
    RAM-based filesystem. Like tmpfs on Linux.
    Organized as a tree of inodes rooted at '/'.
    """

    def __init__(self):
        self._root = Inode("/", is_dir=True)
        self._fd_table = {}    # fd_number → FileDescriptor
        self._next_fd  = 3     # 0,1,2 are reserved (stdin/stdout/stderr)

        # Pre-create standard directories (like mkfs + mkdir)
        self.mkdir("/sys")      # kernel system data
        self.mkdir("/data")     # app persistent data
        self.mkdir("/apps")     # installed applications
        self.mkdir("/tmp")      # temporary files (cleared on boot)
        self.mkdir("/logs")     # kernel + app logs

    def _resolve(self, path: str) -> Inode:
        """Walk the inode tree to find a path. Like namei() in Linux."""
        if path == "/":
            return self._root
        parts = [p for p in path.strip("/").split("/") if p]
        node  = self._root
        for part in parts:
            if not node.is_dir:
                raise FileNotFoundError(f"Not a directory: {part}")
            if part not in node.data:
                raise FileNotFoundError(f"No such file or directory: {path}")
            node = node.data[part]
        return node

    def _parent_and_name(self, path: str):
        parts = path.rstrip("/").rsplit("/", 1)
        parent_path = parts[0] or "/"
        name        = parts[1]
        return self._resolve(parent_path), name

    def mkdir(self, path: str):
        try:
            self._resolve(path)
            return  # already exists
        except FileNotFoundError:
            pass
        parent, name = self._parent_and_name(path)
        node = Inode(name, is_dir=True)
        parent.data[name] = node

    def open(self, path: str, mode: str = "r") -> int:
        """
        Returns an fd number. Like open(2) syscall.
        mode: "r" read, "w" write (creates/truncates), "a" append, "rw" read-write
        """
        try:
            inode = self._resolve(path)
            if "w" in mode:
                inode.data = b""    # truncate
                inode.size = 0
        except FileNotFoundError:
            if "r" == mode:
                raise
            # Create new file
            parent, name = self._parent_and_name(path)
            inode = Inode(name)
            parent.data[name] = inode

        fd  = self._next_fd
        self._next_fd += 1
        self._fd_table[fd] = FileDescriptor(inode, mode)
        return fd

    def read(self, fd: int, size: int = -1) -> bytes:
        return self._fd_table[fd].read(size)

    def write(self, fd: int, data):
        if isinstance(data, str):
            data = data.encode()
        self._fd_table[fd].write(data)

    def close(self, fd: int):
        if fd in self._fd_table:
            del self._fd_table[fd]

    def seek(self, fd: int, offset: int, whence: int = 0):
        self._fd_table[fd].seek(offset, whence)

    def listdir(self, path: str) -> list:
        node = self._resolve(path)
        if not node.is_dir:
            raise NotADirectoryError(path)
        return list(node.data.keys())

    def stat(self, path: str) -> dict:
        node = self._resolve(path)
        return {
            "inode":    node.inode_id,
            "size":     node.size,
            "is_dir":   node.is_dir,
            "created":  node.created,
            "modified": node.modified,
            "mode":     node.mode,
        }

    def exists(self, path: str) -> bool:
        try:
            self._resolve(path)
            return True
        except FileNotFoundError:
            return False

    def unlink(self, path: str):
        """Delete a file. Like unlink(2) — removes directory entry."""
        parent, name = self._parent_and_name(path)
        if name not in parent.data:
            raise FileNotFoundError(path)
        del parent.data[name]

    # ── Convenience helpers (higher-level than raw fd API) ────────────────────

    def write_text(self, path: str, text: str):
        fd = self.open(path, "w")
        self.write(fd, text.encode())
        self.close(fd)

    def read_text(self, path: str) -> str:
        fd = self.open(path, "r")
        data = self.read(fd)
        self.close(fd)
        return data.decode()

    def write_json(self, path: str, obj):
        self.write_text(path, json.dumps(obj))

    def read_json(self, path: str):
        return json.loads(self.read_text(path))

    def append_text(self, path: str, text: str):
        if not self.exists(path):
            self.write_text(path, "")
        fd = self.open(path, "a")
        self._fd_table[fd].seek(0, 2)   # seek to end
        self.write(fd, text.encode())
        self.close(fd)

    def tree(self, path="/", indent=0) -> str:
        """Print filesystem tree. For debugging."""
        out = ""
        try:
            node = self._resolve(path)
            name = path.split("/")[-1] or "/"
            out  = "  " * indent + ("📁 " if node.is_dir else "📄 ") + name + "\n"
            if node.is_dir:
                for child in node.data:
                    child_path = (path.rstrip("/") + "/" + child)
                    out += self.tree(child_path, indent + 1)
        except Exception as e:
            out = f"  " * indent + f"[err: {e}]\n"
        return out


# ── Global VFS instance (mounted at boot by kernel) ───────────────────────────
# In a real OS: mount() syscall attaches filesystems to the VFS tree.

vfs = MemFS()
