#!/usr/bin/env python3
"""
IPv4 subnet calculator.

Run with no arguments for the desktop window:
    python3 subnet_calc.py

Run with an address for a one-shot answer in the terminal:
    python3 subnet_calc.py 192.168.10.130/26
    python3 subnet_calc.py 10.0.0.5 255.255.255.0

Plan a set of variable-length subnets inside a parent block:
    python3 subnet_calc.py --vlsm 10.0.0.0/24 sales:50 engineering:25 wan:2
    add --p2p to use /31 links for the two-host entries

Only the standard library is used. The window needs tkinter; if that is
missing the program drops into an interactive terminal prompt instead.
"""

from __future__ import annotations

import os
import sys

# --------------------------------------------------------------------------
# colour - a VS Code Dark+ flavoured palette for the terminal
# --------------------------------------------------------------------------

class Palette:
    """Wraps text in 256-colour ANSI codes, or passes it through untouched."""

    CODES = {
        "label": 245,    # grey, for row names
        "value": 252,    # near-white, for ordinary values
        "net": 81,       # light blue, network bits and addresses
        "host": 240,     # dim grey, host bits
        "name": 79,      # teal, subnet names
        "num": 114,      # green, counts
        "warn": 179,     # amber, separators and notes
        "bad": 203,      # red, errors
        "head": 186,     # pale yellow, headings
    }

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def __getattr__(self, role: str):
        code = self.CODES.get(role)
        if code is None:
            raise AttributeError(role)
        if not self.enabled:
            return lambda text: text
        return lambda text: f"\x1b[38;5;{code}m{text}\x1b[0m"


PLAIN = Palette(False)


def colour_enabled(argv: list[str]) -> bool:
    """Colour when we are writing to a real terminal, unless told otherwise."""
    if "--no-color" in argv or os.environ.get("NO_COLOR"):
        return False
    if "--color" in argv:
        return True
    return sys.stdout.isatty() and os.environ.get("TERM", "") != "dumb"


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
# VLSM planning
# --------------------------------------------------------------------------

class Allocation:
    """One named subnet handed out by the planner."""

    def __init__(self, name: str, requested: int, subnet: Subnet):
        self.name = name
        self.requested = requested
        self.subnet = subnet

    @property
    def spare(self) -> int:
        return self.subnet.usable - self.requested


def prefix_for_hosts(hosts: int, point_to_point: bool = False) -> int:
    """Smallest prefix that still leaves room for `hosts` usable addresses."""
    if hosts < 1:
        raise ValueError("a subnet needs at least one host")
    if point_to_point and hosts <= 2:
        return 31
    for prefix in range(30, -1, -1):
        if (1 << (32 - prefix)) - 2 >= hosts:
            return prefix
    raise ValueError(f"{hosts:,} hosts will not fit in IPv4")


def cidr_blocks(start: int, end: int) -> list[Subnet]:
    """Cover the range start..end with the fewest properly aligned blocks."""
    blocks: list[Subnet] = []
    while start <= end:
        align = (start & -start) if start else (1 << 32)
        size = min(align, 1 << (end - start + 1).bit_length() - 1)
        blocks.append(Subnet(start, 32 - size.bit_length() + 1))
        start += size
    return blocks


def parse_requirements(lines: list[str]) -> list[tuple[str, int]]:
    """Read 'sales: 50' or 'sales 50' or bare '50' into (name, hosts) pairs."""
    reqs: list[tuple[str, int]] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, count = line.rpartition(":" if ":" in line else " ")
        if not sep:
            name, count = f"subnet {len(reqs) + 1}", line
        count = count.strip()
        if not count.isdigit():
            raise ValueError(f"'{raw.strip()}' needs a host count, e.g. sales: 50")
        reqs.append((name.strip() or f"subnet {len(reqs) + 1}", int(count)))
    if not reqs:
        raise ValueError("no subnets requested")
    return reqs


def vlsm_plan(parent: Subnet, requirements: list[tuple[str, int]],
              point_to_point: bool = False) -> tuple[list[Allocation], list[Subnet]]:
    """Allocate the biggest subnets first, packed from the start of the parent.

    Returns the allocations in the order they were requested, plus whatever
    address space is left over, expressed as aligned CIDR blocks.
    """
    ordered = sorted(enumerate(requirements), key=lambda item: -item[1][1])
    cursor = parent.network
    placed: list[tuple[int, Allocation]] = []
    for index, (name, hosts) in ordered:
        prefix = prefix_for_hosts(hosts, point_to_point)
        size = 1 << (32 - prefix)
        cursor = (cursor + size - 1) & ~(size - 1) & FULL  # round up to a boundary
        if cursor + size - 1 > parent.broadcast:
            raise ValueError(
                f"'{name}' needs a /{prefix} ({size} addresses) and there is no "
                f"room left in {fmt_ip(parent.network)}/{parent.prefix}"
            )
        placed.append((index, Allocation(name, hosts, Subnet(cursor, prefix))))
        cursor += size

    used = sorted((a.subnet.network, a.subnet.broadcast) for _, a in placed)
    free: list[Subnet] = []
    edge = parent.network
    for start, stop in used:
        if start > edge:
            free.extend(cidr_blocks(edge, start - 1))
        edge = stop + 1
    if edge <= parent.broadcast:
        free.extend(cidr_blocks(edge, parent.broadcast))

    return [a for _, a in sorted(placed, key=lambda item: item[0])], free


def format_plan(parent: Subnet, allocations: list[Allocation],
                free: list[Subnet], pal: Palette = PLAIN) -> list[str]:
    """Turn a plan into monospaced lines for the terminal or the window."""
    width = max([len(a.name) for a in allocations] + [4])
    lines = [
        pal.head(f"{fmt_ip(parent.network)}/{parent.prefix}") + "  " +
        pal.label(f"({parent.total:,} addresses, {parent.usable:,} usable)"),
        "",
        pal.label(f"{'name':<{width}}  {'network':<18} {'range':<33} "
                  f"{'mask':<15} {'hosts':>7} {'spare':>6}"),
    ]
    for a in allocations:
        sn = a.subnet
        lines.append(
            pal.name(f"{a.name:<{width}}") + "  " +
            pal.net(f"{fmt_ip(sn.network) + '/' + str(sn.prefix):<18}") + " " +
            pal.value(f"{fmt_ip(sn.first) + ' - ' + fmt_ip(sn.last):<33}") + " " +
            pal.host(f"{fmt_ip(sn.mask):<15}") + " " +
            pal.num(f"{a.requested:>7}") + " " +
            (pal.warn if a.spare == 0 else pal.host)(f"{a.spare:>6}")
        )
    assigned = sum(a.subnet.total for a in allocations)
    lines += ["", pal.value(f"assigned {assigned:,} of {parent.total:,} addresses "
                            f"({assigned * 100 // parent.total}%)")]
    if free:
        lines.append(pal.label("free blocks:"))
        for block in free:
            lines.append("  " + pal.net(f"{fmt_ip(block.network)}/{block.prefix}") +
                         pal.label(f"   {block.total:,} addresses"))
    else:
        lines.append(pal.label("no space left over"))
    return lines


# --------------------------------------------------------------------------
# terminal output
# --------------------------------------------------------------------------

def print_report(sn: Subnet, pal: Palette = PLAIN) -> None:
    print()
    for label, value in sn.rows():
        tint = pal.net if value.count(".") == 3 else pal.value
        print(f"  {pal.label(f'{label:<20}')} {tint(value)}")
    print()
    for label, value in sn.binary_rows():
        cut, seen = 0, 0
        for cut, char in enumerate(value, start=1):
            if char != ".":
                seen += 1
            if seen == sn.prefix:
                break
        else:
            cut = 0 if sn.prefix == 0 else len(value)
        head, tail = value[:cut], value[cut:]
        bar = pal.warn("|") if 0 < sn.prefix < 32 else ""
        print(f"  {pal.label(f'{label:<20}')} {pal.net(head)}{bar}{pal.host(tail)}")
    print(f"  {' ' * 20} {pal.label('^ network bits to the left of the bar')}")
    print()


def do_vlsm(args: list[str], point_to_point: bool = False,
            pal: Palette = PLAIN) -> None:
    """args looks like ['10.0.0.0/24', 'sales:50', 'wan:2']."""
    if len(args) < 2:
        raise ValueError("usage: --vlsm 10.0.0.0/24 sales:50 engineering:25 wan:2")
    parent = from_text(args[0])
    allocations, free = vlsm_plan(parent, parse_requirements(args[1:]), point_to_point)
    print()
    for line in format_plan(parent, allocations, free, pal):
        print(f"  {line}")
    print()


def run_cli(args: list[str]) -> int:
    pal = Palette(colour_enabled(args))
    args = [a for a in args if a not in ("--color", "--no-color")]
    if args:
        try:
            if args[0] in ("--vlsm", "-v"):
                do_vlsm([a for a in args[1:] if a != "--p2p"], "--p2p" in args, pal)
            else:
                print_report(from_text(args[0], args[1] if len(args) > 1 else None), pal)
        except ValueError as exc:
            print(pal.bad(f"error: {exc}"), file=sys.stderr)
            return 1
        return 0

    print(pal.head("IPv4 subnet calculator.") + " Enter an address like 192.168.10.130/26.")
    print(pal.label("Type 'split 4' after a calculation to divide it up, 'q' to quit, or"))
    print(pal.label("plan with: vlsm 10.0.0.0/24 sales:50 engineering:25 wan:2") + "\n")
    current: Subnet | None = None
    while True:
        try:
            line = input(pal.net("> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line.lower() in {"q", "quit", "exit"}:
            return 0
        if not line:
            continue
        if line.lower().startswith("vlsm"):
            try:
                do_vlsm(line.split()[1:], pal=pal)
            except ValueError as exc:
                print(pal.bad(f"error: {exc}"))
            continue
        if line.lower().startswith("split"):
            if current is None:
                print(pal.bad("calculate a subnet first"))
                continue
            bits_ = line.split()
            try:
                for part in current.split(int(bits_[1]) if len(bits_) > 1 else 2):
                    print("  " + pal.net(f"{fmt_ip(part.network)}/{part.prefix:<4}") +
                          pal.value(f"  {fmt_ip(part.first)} - {fmt_ip(part.last)}") +
                          pal.label(f"   {part.usable:,} hosts"))
            except (ValueError, IndexError) as exc:
                print(pal.bad(f"error: {exc}"))
            continue
        try:
            current = from_text(line)
        except ValueError as exc:
            print(pal.bad(f"error: {exc}"))
            continue
        print_report(current, pal)


# --------------------------------------------------------------------------
# desktop window
# --------------------------------------------------------------------------

def run_gui() -> int:
    import tkinter as tk
    from tkinter import ttk

    BG, PANEL, FIELD = "#1e1e1e", "#252526", "#3c3c3c"
    FG, MUTED, LINE = "#d4d4d4", "#858585", "#3c3c3c"
    BLUE, SEL, TEAL, RED = "#9cdcfe", "#264f78", "#4ec9b0", "#f44747"

    root = tk.Tk()
    root.title("IPv4 subnet toolkit")
    root.minsize(700, 620)
    root.configure(background=BG)

    style = ttk.Style()
    try:
        style.theme_use("clam")  # aqua and vista ignore most colour options
    except tk.TclError:
        pass
    style.configure(".", background=BG, foreground=FG, fieldbackground=PANEL,
                    bordercolor=LINE, lightcolor=BG, darkcolor=BG, focuscolor=BG)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("TCheckbutton", background=BG, foreground=FG)
    style.map("TCheckbutton", background=[("active", BG)])
    style.configure("TButton", background=FIELD, foreground=FG, borderwidth=0, padding=6)
    style.map("TButton", background=[("active", "#0e639c")])
    style.configure("TEntry", fieldbackground=PANEL, foreground=FG,
                    insertcolor=FG, bordercolor=LINE, padding=4)
    style.configure("TSpinbox", fieldbackground=PANEL, foreground=FG,
                    arrowcolor=FG, bordercolor=LINE)
    style.configure("TCombobox", fieldbackground=PANEL, foreground=FG, arrowcolor=FG)
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(16, 8))
    style.map("TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", BLUE)])
    style.configure("TScale", background=BG, troughcolor=PANEL)
    style.configure("TSeparator", background=LINE)
    style.configure("Horizontal.TScrollbar", background=FIELD, troughcolor=BG, arrowcolor=FG)
    root.option_add("*TCombobox*Listbox.background", PANEL)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", SEL)

    book = ttk.Notebook(root)
    book.pack(fill="both", expand=True, padx=8, pady=8)

    frame = ttk.Frame(book, padding=16)
    book.add(frame, text="Calculator")
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

    error_label = ttk.Label(frame, textvariable=error_var, foreground=RED)
    error_label.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 8))

    results = ttk.Frame(frame)
    results.grid(row=3, column=0, columnspan=3, sticky="ew")
    results.columnconfigure(1, weight=1)
    value_labels: dict[str, ttk.Label] = {}
    labels = ["Network address", "Broadcast address", "Usable range", "Usable hosts",
              "Total addresses", "Subnet mask", "Wildcard mask", "Block size", "Scope"]
    for i, name in enumerate(labels):
        ttk.Label(results, text=name, foreground=MUTED).grid(row=i, column=0, sticky="w", pady=2)
        val = ttk.Label(results, text="-", font=mono)
        val.grid(row=i, column=1, sticky="e", pady=2)
        value_labels[name] = val

    ttk.Separator(frame).grid(row=4, column=0, columnspan=3, sticky="ew", pady=12)

    text = tk.Text(frame, height=8, font=("Courier New", 10), borderwidth=0,
                   highlightthickness=0, background=BG, foreground=FG)
    text.grid(row=5, column=0, columnspan=3, sticky="ew")
    text.tag_configure("net", background=SEL, foreground=BLUE)
    text.tag_configure("host", background=PANEL, foreground=MUTED)
    text.tag_configure("label", foreground=TEAL)
    text.configure(state="disabled")

    split_box = ttk.Frame(frame)
    split_box.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(12, 0))
    split_var = tk.StringVar(value="4")
    ttk.Label(split_box, text="Split into").pack(side="left")
    ttk.Combobox(split_box, textvariable=split_var, width=4, state="readonly",
                 values=("2", "4", "8", "16", "32")).pack(side="left", padx=6)
    split_out = tk.Text(frame, height=7, font=("Courier New", 10), borderwidth=0,
                        highlightthickness=0, background=BG, foreground=BLUE,
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

    # ---- VLSM planner tab -------------------------------------------------
    plan = ttk.Frame(book, padding=16)
    book.add(plan, text="VLSM planner")
    plan.columnconfigure(0, weight=1)
    plan.rowconfigure(6, weight=1)

    ttk.Label(plan, text="Parent network").grid(row=0, column=0, sticky="w")
    parent_var = tk.StringVar(value="192.168.1.0/24")
    ttk.Entry(plan, textvariable=parent_var, font=mono).grid(row=1, column=0, sticky="ew", pady=(2, 10))

    ttk.Label(plan, text="One subnet per line, written as  name: hosts").grid(row=2, column=0, sticky="w")
    req_text = tk.Text(plan, height=6, font=mono, background=PANEL, foreground=FG,
                       insertbackground=FG, selectbackground=SEL, borderwidth=0,
                       highlightthickness=1, highlightbackground=LINE, highlightcolor=BLUE)
    req_text.insert("1.0", "sales: 50\nengineering: 25\nwifi: 10\nwan link: 2\n")
    req_text.grid(row=3, column=0, sticky="ew", pady=(2, 8))

    controls = ttk.Frame(plan)
    controls.grid(row=4, column=0, sticky="ew")
    p2p_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(controls, text="use /31 for two-host links", variable=p2p_var).pack(side="left")
    plan_error = tk.StringVar(value="")
    ttk.Label(plan, textvariable=plan_error, foreground=RED).grid(row=5, column=0, sticky="w", pady=(6, 4))

    plan_out = tk.Text(plan, height=16, font=("Courier New", 10), wrap="none",
                       borderwidth=0, highlightthickness=0,
                       background=BG, foreground=FG, state="disabled")
    plan_out.grid(row=6, column=0, sticky="nsew")
    bar = ttk.Scrollbar(plan, orient="horizontal", command=plan_out.xview)
    bar.grid(row=7, column=0, sticky="ew")
    plan_out.configure(xscrollcommand=bar.set)

    def build_plan(*_args) -> None:
        plan_out.configure(state="normal")
        plan_out.delete("1.0", "end")
        try:
            parent = from_text(parent_var.get())
            reqs = parse_requirements(req_text.get("1.0", "end").splitlines())
            allocations, free = vlsm_plan(parent, reqs, p2p_var.get())
        except ValueError as exc:
            plan_error.set(str(exc))
            plan_out.configure(state="disabled")
            return
        plan_error.set("")
        plan_out.insert("end", "\n".join(format_plan(parent, allocations, free)))
        plan_out.configure(state="disabled")

    def copy_plan() -> None:
        root.clipboard_clear()
        root.clipboard_append(plan_out.get("1.0", "end").strip())

    ttk.Button(controls, text="Plan", command=build_plan).pack(side="right")
    ttk.Button(controls, text="Copy", command=copy_plan).pack(side="right", padx=6)
    req_text.bind("<KeyRelease>", build_plan)
    parent_var.trace_add("write", build_plan)
    p2p_var.trace_add("write", build_plan)
    build_plan()

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
        if sys.platform == "darwin":
            print("On macOS with Homebrew Python: brew install python-tk\n")
        elif sys.platform.startswith("win"):
            print("Re-run the python.org installer and tick 'tcl/tk and IDLE'.\n")
        else:
            print("On Debian/Ubuntu: sudo apt install python3-tk\n")
    except Exception as exc:  # no display, e.g. over SSH
        print(f"could not open a window ({exc}), falling back to the terminal.\n")
    return run_cli([])


if __name__ == "__main__":
    raise SystemExit(main())
