#!/usr/bin/env python3
"""
IPv4 subnet calculator.

Run with no arguments for the desktop window:
    python3 subnet_calc.py

Run with an address for a one-shot answer in the terminal:
    python3 subnet_calc.py 192.168.10.130/26
    python3 subnet_calc.py 10.0.0.5 255.255.255.0

Only the standard library is used. The window needs tkinter; if that is
missing the program drops into an interactive terminal prompt instead.
"""

from __future__ import annotations

import sys

# --------------------------------------------------------------------------
# core maths - no tkinter needed for any of this
# --------------------------------------------------------------------------

FULL = 0xFFFFFFFF


def parse_ip(text: str) -> int:
    """Turn '192.168.1.1' into a 32-bit integer."""
    parts = text.strip().split(".")
    if len(parts) != 4:
        raise ValueError("an address needs four octets, e.g. 192.168.10.130")
    value = 0
    for part in parts:
        if not part.isdigit():
            raise ValueError(f"'{part}' is not a number")
        octet = int(part)
        if octet > 255:
            raise ValueError(f"{octet} is bigger than 255")
        value = (value << 8) | octet
    return value


def fmt_ip(value: int) -> str:
    """Turn a 32-bit integer back into dotted decimal."""
    value &= FULL
    return ".".join(str((value >> shift) & 255) for shift in (24, 16, 8, 0))


def mask_to_prefix(text: str) -> int:
    """Accept '255.255.255.192' or '/26' or '26' and return the prefix length."""
    text = text.strip().lstrip("/")
    if "." in text:
        value = parse_ip(text)
        binary = f"{value:032b}"
        if "01" in binary:
            raise ValueError(f"{text} is not a contiguous subnet mask")
        return binary.count("1")
    if not text.isdigit() or not 0 <= int(text) <= 32:
        raise ValueError("prefix must be a number from 0 to 32")
    return int(text)


def scope(network: int) -> str:
    """Rough description of which special range an address falls in."""
    a, b = (network >> 24) & 255, (network >> 16) & 255
    if a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168):
        return "Private (RFC 1918)"
    if a == 127:
        return "Loopback"
    if a == 169 and b == 254:
        return "Link-local (APIPA)"
    if a == 100 and 64 <= b <= 127:
        return "Carrier-grade NAT"
    if 224 <= a <= 239:
        return "Multicast"
    if a >= 240:
        return "Reserved"
    if a == 0:
        return "This network"
    return "Public"


class Subnet:
    """Everything derived from one address plus one prefix length."""

    def __init__(self, ip: int, prefix: int):
        if not 0 <= prefix <= 32:
            raise ValueError("prefix must be from 0 to 32")
        self.ip = ip & FULL
        self.prefix = prefix
        self.mask = 0 if prefix == 0 else (FULL << (32 - prefix)) & FULL
        self.wildcard = (~self.mask) & FULL
        self.network = self.ip & self.mask
        self.broadcast = self.network | self.wildcard
        self.total = 1 << (32 - prefix)
        if prefix == 32:
            self.usable = 1
            self.first = self.last = self.network
        elif prefix == 31:
            self.usable = 2
            self.first, self.last = self.network, self.broadcast
        else:
            self.usable = self.total - 2
            self.first, self.last = self.network + 1, self.broadcast - 1

    @property
    def block_size(self) -> int:
        """The step between consecutive subnets in the interesting octet."""
        if self.prefix == 32:
            return 1
        return 1 << ((32 - self.prefix) % 8) if self.prefix % 8 else 256

    def split(self, count: int) -> list["Subnet"]:
        """Divide this block into `count` equal subnets (count must be a power of 2)."""
        if count < 1 or count & (count - 1):
            raise ValueError("split count must be a power of two")
        extra = count.bit_length() - 1
        if self.prefix + extra > 32:
            raise ValueError(f"cannot fit {count} subnets inside a /{self.prefix}")
        step = 1 << (32 - self.prefix - extra)
        return [Subnet(self.network + i * step, self.prefix + extra) for i in range(count)]

    def rows(self) -> list[tuple[str, str]]:
        """Label/value pairs, ready to print or drop into a table."""
        no_bcast = self.prefix >= 31
        return [
            ("Address", f"{fmt_ip(self.ip)}/{self.prefix}"),
            ("Network address", fmt_ip(self.network)),
            ("Broadcast address", "n/a" if no_bcast else fmt_ip(self.broadcast)),
            ("Usable range", f"{fmt_ip(self.first)} - {fmt_ip(self.last)}"),
            ("Usable hosts", f"{self.usable:,}"),
            ("Total addresses", f"{self.total:,}"),
            ("Subnet mask", fmt_ip(self.mask)),
            ("Wildcard mask", fmt_ip(self.wildcard)),
            ("Block size", str(self.block_size)),
            ("Scope", scope(self.network)),
        ]

    def binary_rows(self) -> list[tuple[str, str]]:
        """Dotted binary for each value, so you can see where the mask cuts."""
        def dotted(value: int) -> str:
            b = f"{value & FULL:032b}"
            return ".".join(b[i:i + 8] for i in range(0, 32, 8))

        rows = [
            ("address", dotted(self.ip)),
            ("mask", dotted(self.mask)),
            ("network", dotted(self.network)),
        ]
        if self.prefix < 31:
            rows.append(("broadcast", dotted(self.broadcast)))
        return rows


def from_text(address: str, mask: str | None = None) -> Subnet:
    """Build a Subnet from '10.0.0.1/24', or from an address and a separate mask."""
    address = address.strip()
    if mask is None:
        if "/" not in address:
            raise ValueError("give a prefix, e.g. 192.168.1.10/24")
        address, mask = address.split("/", 1)
    return Subnet(parse_ip(address), mask_to_prefix(mask))


# --------------------------------------------------------------------------
# terminal output
# --------------------------------------------------------------------------

def print_report(sn: Subnet) -> None:
    print()
    for label, value in sn.rows():
        print(f"  {label:<20} {value}")
    print()
    for label, value in sn.binary_rows():
        # the dots in the binary sit at positions 8, 17 and 26
        cut = sn.prefix + sn.prefix // 8 - (1 if sn.prefix and sn.prefix % 8 == 0 else 0)
        marked = value[:cut] + "|" + value[cut:] if 0 < sn.prefix < 32 else value
        print(f"  {label:<20} {marked}")
    print(f"  {'':<20} {'^ network bits to the left of the bar':}")
    print()


def run_cli(args: list[str]) -> int:
    if args:
        try:
            sn = from_text(args[0], args[1] if len(args) > 1 else None)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print_report(sn)
        return 0

    print("IPv4 subnet calculator. Enter an address like 192.168.10.130/26.")
    print("Type 'split 4' after a calculation to divide it up, or 'q' to quit.\n")
    current: Subnet | None = None
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line.lower() in {"q", "quit", "exit"}:
            return 0
        if not line:
            continue
        if line.lower().startswith("split"):
            if current is None:
                print("calculate a subnet first")
                continue
            bits_ = line.split()
            try:
                for part in current.split(int(bits_[1]) if len(bits_) > 1 else 2):
                    print(f"  {fmt_ip(part.network)}/{part.prefix}"
                          f"   {fmt_ip(part.first)} - {fmt_ip(part.last)}"
                          f"   ({part.usable:,} hosts)")
            except (ValueError, IndexError) as exc:
                print(f"error: {exc}")
            continue
        try:
            current = from_text(line)
        except ValueError as exc:
            print(f"error: {exc}")
            continue
        print_report(current)


# --------------------------------------------------------------------------
# desktop window
# --------------------------------------------------------------------------

def run_gui() -> int:
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("IPv4 subnet calculator")
    root.minsize(620, 560)

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)

    mono = ("Courier New", 11)

    ip_var = tk.StringVar(value="192.168.10.130")
    prefix_var = tk.IntVar(value=26)
    error_var = tk.StringVar(value="")

    ttk.Label(frame, text="Address").grid(row=0, column=0, sticky="w", pady=4)
    ip_entry = ttk.Entry(frame, textvariable=ip_var, font=mono)
    ip_entry.grid(row=0, column=1, sticky="ew", padx=8, pady=4)
    spin = ttk.Spinbox(frame, from_=0, to=32, textvariable=prefix_var, width=5, font=mono)
    spin.grid(row=0, column=2, pady=4)

    ttk.Label(frame, text="Prefix").grid(row=1, column=0, sticky="w", pady=4)
    slider = ttk.Scale(frame, from_=0, to=32, orient="horizontal")
    slider.set(26)
    slider.grid(row=1, column=1, sticky="ew", padx=8, pady=4)
    prefix_label = ttk.Label(frame, text="/26", font=mono, width=5)
    prefix_label.grid(row=1, column=2, pady=4)

    error_label = ttk.Label(frame, textvariable=error_var, foreground="#b00020")
    error_label.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 8))

    results = ttk.Frame(frame)
    results.grid(row=3, column=0, columnspan=3, sticky="ew")
    results.columnconfigure(1, weight=1)
    value_labels: dict[str, ttk.Label] = {}
    labels = ["Network address", "Broadcast address", "Usable range", "Usable hosts",
              "Total addresses", "Subnet mask", "Wildcard mask", "Block size", "Scope"]
    for i, name in enumerate(labels):
        ttk.Label(results, text=name, foreground="#555555").grid(row=i, column=0, sticky="w", pady=2)
        val = ttk.Label(results, text="-", font=mono)
        val.grid(row=i, column=1, sticky="e", pady=2)
        value_labels[name] = val

    ttk.Separator(frame).grid(row=4, column=0, columnspan=3, sticky="ew", pady=12)

    text = tk.Text(frame, height=8, font=("Courier New", 10), borderwidth=0,
                   highlightthickness=0, background=root.cget("background"))
    text.grid(row=5, column=0, columnspan=3, sticky="ew")
    text.tag_configure("net", background="#cfe3fb", foreground="#0c447c")
    text.tag_configure("host", background="#e8e8e6", foreground="#5f5e5a")
    text.tag_configure("label", foreground="#555555")
    text.configure(state="disabled")

    split_box = ttk.Frame(frame)
    split_box.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(12, 0))
    split_var = tk.StringVar(value="4")
    ttk.Label(split_box, text="Split into").pack(side="left")
    ttk.Combobox(split_box, textvariable=split_var, width=4, state="readonly",
                 values=("2", "4", "8", "16", "32")).pack(side="left", padx=6)
    split_out = tk.Text(frame, height=7, font=("Courier New", 10), borderwidth=0,
                        highlightthickness=0, background=root.cget("background"),
                        state="disabled")
    split_out.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(8, 0))

    current: dict[str, Subnet] = {}

    def show_split() -> None:
        sn = current.get("sn")
        split_out.configure(state="normal")
        split_out.delete("1.0", "end")
        if sn is not None:
            try:
                for part in sn.split(int(split_var.get())):
                    split_out.insert("end",
                                     f"{fmt_ip(part.network)}/{part.prefix}"
                                     f"   {fmt_ip(part.first)} - {fmt_ip(part.last)}"
                                     f"   {part.usable:,} hosts\n")
            except ValueError as exc:
                split_out.insert("end", str(exc))
        split_out.configure(state="disabled")

    ttk.Button(split_box, text="Show", command=show_split).pack(side="left")

    def refresh(*_args) -> None:
        try:
            sn = Subnet(parse_ip(ip_var.get()), int(prefix_var.get()))
        except (ValueError, tk.TclError) as exc:
            error_var.set(str(exc) if isinstance(exc, ValueError) else "prefix must be 0-32")
            return
        error_var.set("")
        current["sn"] = sn
        prefix_label.configure(text=f"/{sn.prefix}")
        lookup = dict(sn.rows())
        for name, widget in value_labels.items():
            widget.configure(text=lookup[name])

        text.configure(state="normal")
        text.delete("1.0", "end")
        for label, value in sn.binary_rows():
            text.insert("end", f"{label:>10}  ", "label")
            bit_index = 0
            for char in value:
                if char == ".":
                    text.insert("end", ".")
                else:
                    text.insert("end", char, "net" if bit_index < sn.prefix else "host")
                    bit_index += 1
            text.insert("end", "\n")
        text.configure(state="disabled")
        show_split()

    def on_slide(value: str) -> None:
        prefix_var.set(int(float(value)))

    slider.configure(command=on_slide)
    ip_var.trace_add("write", refresh)
    prefix_var.trace_add("write", lambda *_: (slider.set(prefix_var.get()), refresh()))

    refresh()
    root.mainloop()
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args:
        return run_cli(args)
    try:
        return run_gui()
    except ImportError:
        print("tkinter is not installed, falling back to the terminal.")
        print("On Debian/Ubuntu: sudo apt install python3-tk\n")
    except Exception as exc:  # no display, e.g. over SSH
        print(f"could not open a window ({exc}), falling back to the terminal.\n")
    return run_cli([])


if __name__ == "__main__":
    raise SystemExit(main())
