#!/usr/bin/env python3
"""Subnet Calculator: an IPv4 subnetting tool built for CCNA practice.

All the maths is done with plain bitwise operations on 32-bit integers
(no ``ipaddress`` module), so the code shows how subnetting really works.

Commands
    info   Full breakdown of one address/prefix
    split  Divide a network into equal-sized subnets
    vlsm   Allocate variable-length subnets from host requirements
"""

import argparse
import sys
from dataclasses import dataclass

MAX_INT = 0xFFFFFFFF


# --------------------------------------------------------------------------
# Conversion helpers
# --------------------------------------------------------------------------
def ip_to_int(ip: str) -> int:
    """Convert dotted-decimal '192.168.1.10' to a 32-bit integer."""
    parts = ip.strip().split(".")
    if len(parts) != 4:
        raise ValueError(f"Invalid IPv4 address: {ip!r}")
    value = 0
    for part in parts:
        if not part.isdigit() or not 0 <= int(part) <= 255:
            raise ValueError(f"Invalid IPv4 address: {ip!r}")
        value = (value << 8) | int(part)
    return value


def int_to_ip(value: int) -> str:
    """Convert a 32-bit integer to dotted-decimal."""
    return ".".join(str((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def int_to_binary(value: int) -> str:
    """Dotted binary, e.g. 11000000.10101000.00000001.00001010"""
    return ".".join(f"{(value >> shift) & 0xFF:08b}" for shift in (24, 16, 8, 0))


def prefix_to_mask(prefix: int) -> int:
    """/26 -> 255.255.255.192 (as an integer)."""
    if not 0 <= prefix <= 32:
        raise ValueError(f"Prefix length must be 0-32, got {prefix}")
    return (MAX_INT << (32 - prefix)) & MAX_INT


def mask_to_prefix(mask: int) -> int:
    """255.255.255.192 -> 26. Rejects non-contiguous masks."""
    inverted = ~mask & MAX_INT
    if inverted & (inverted + 1):  # wildcard must look like 0...01...1
        raise ValueError(f"Invalid subnet mask: {int_to_ip(mask)}")
    return bin(mask).count("1")


def parse_address(text: str) -> tuple[int, int]:
    """Parse '192.168.1.10/24' or '192.168.1.10 255.255.255.0'."""
    text = text.strip()
    if "/" in text:
        ip, _, pfx = text.partition("/")
        if not pfx.strip().isdigit():
            raise ValueError(f"Invalid prefix length: {pfx!r}")
        return ip_to_int(ip), int(pfx)
    parts = text.split()
    if len(parts) != 2:
        raise ValueError("Use CIDR (192.168.1.10/24) or 'IP MASK' in quotes")
    return ip_to_int(parts[0]), mask_to_prefix(ip_to_int(parts[1]))


# --------------------------------------------------------------------------
# Core model
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Subnet:
    """A subnet defined by any address inside it plus a prefix length."""

    address: int
    prefix: int

    @property
    def mask(self) -> int:
        return prefix_to_mask(self.prefix)

    @property
    def wildcard(self) -> int:
        return ~self.mask & MAX_INT

    @property
    def network(self) -> int:
        return self.address & self.mask

    @property
    def broadcast(self) -> int:
        return self.network | self.wildcard

    @property
    def total_addresses(self) -> int:
        return 2 ** (32 - self.prefix)

    @property
    def usable_hosts(self) -> int:
        if self.prefix == 32:
            return 1
        if self.prefix == 31:  # RFC 3021 point-to-point link
            return 2
        return self.total_addresses - 2

    @property
    def first_host(self) -> int:
        return self.network if self.prefix >= 31 else self.network + 1

    @property
    def last_host(self) -> int:
        return self.broadcast if self.prefix >= 31 else self.broadcast - 1

    @property
    def address_class(self) -> str:
        first = self.address >> 24
        if first < 128:
            return "A"
        if first < 192:
            return "B"
        if first < 224:
            return "C"
        if first < 240:
            return "D (multicast)"
        return "E (reserved)"

    @property
    def address_type(self) -> str:
        ip = self.address
        if ip >> 24 == 10:
            return "Private (RFC 1918)"
        if ip >> 20 == 0xAC1:  # 172.16.0.0/12
            return "Private (RFC 1918)"
        if ip >> 16 == 0xC0A8:  # 192.168.0.0/16
            return "Private (RFC 1918)"
        if ip >> 24 == 127:
            return "Loopback"
        if ip >> 16 == 0xA9FE:  # 169.254.0.0/16
            return "Link-local (APIPA)"
        if ip >> 28 == 0xE:
            return "Multicast"
        return "Public"

    def cidr(self) -> str:
        return f"{int_to_ip(self.network)}/{self.prefix}"


# --------------------------------------------------------------------------
# Features
# --------------------------------------------------------------------------
def split_equal(net: Subnet, count: int) -> list[Subnet]:
    """Split into equal subnets. Count is rounded up to a power of two."""
    if count < 1:
        raise ValueError("Number of subnets must be at least 1")
    borrowed = (count - 1).bit_length()
    new_prefix = net.prefix + borrowed
    if new_prefix > 32:
        raise ValueError(
            f"Cannot split {net.cidr()} into {count} subnets "
            f"(would need a /{new_prefix})"
        )
    size = 2 ** (32 - new_prefix)
    return [Subnet(net.network + i * size, new_prefix) for i in range(2**borrowed)]


def prefix_for_hosts(hosts: int) -> int:
    """Smallest subnet (largest prefix) that fits `hosts` usable addresses."""
    if hosts < 1:
        raise ValueError("Each subnet needs at least 1 host")
    host_bits = max((hosts + 2 - 1).bit_length(), 2)  # +2 for net/broadcast, min /30
    return 32 - host_bits


def vlsm(net: Subnet, requirements: list[tuple[str, int]]) -> list[tuple[str, int, Subnet]]:
    """Allocate subnets largest-first so every block stays aligned.

    requirements: [(label, hosts_needed), ...]
    returns:      [(label, hosts_needed, Subnet), ...] in allocation order
    """
    sized = [(label, hosts, prefix_for_hosts(hosts)) for label, hosts in requirements]
    sized.sort(key=lambda item: item[2])  # smallest prefix = biggest block first

    cursor = net.network
    end = net.broadcast
    result = []
    for label, hosts, prefix in sized:
        if prefix < net.prefix:
            raise ValueError(f"{label} needs a /{prefix}, which is larger than {net.cidr()}")
        block = Subnet(cursor, prefix)
        if block.broadcast > end:
            raise ValueError(f"Not enough address space in {net.cidr()} for {label}")
        result.append((label, hosts, block))
        cursor = block.broadcast + 1
    return result


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def show_info(net: Subnet, binary: bool = False) -> str:
    rows = [
        ("Address", int_to_ip(net.address)),
        ("Subnet mask", f"{int_to_ip(net.mask)} (/{net.prefix})"),
        ("Wildcard mask", int_to_ip(net.wildcard)),
        ("Network address", int_to_ip(net.network)),
        ("Broadcast address", int_to_ip(net.broadcast)),
        ("First usable host", int_to_ip(net.first_host)),
        ("Last usable host", int_to_ip(net.last_host)),
        ("Total addresses", f"{net.total_addresses:,}"),
        ("Usable hosts", f"{net.usable_hosts:,}"),
        ("Class", net.address_class),
        ("Type", net.address_type),
    ]
    if binary:
        rows[1:1] = [("Address (bin)", int_to_binary(net.address))]
        rows.insert(3, ("Mask (bin)", int_to_binary(net.mask)))
    width = max(len(label) for label, _ in rows)
    return "\n".join(f"{label:<{width}} : {value}" for label, value in rows)


def show_table(subnets: list[Subnet]) -> str:
    header = f"{'#':<3} {'Network':<18} {'Mask':<16} {'First host':<16} {'Last host':<16} {'Broadcast':<16} {'Hosts':>6}"
    lines = [header, "-" * len(header)]
    for i, s in enumerate(subnets, 1):
        lines.append(
            f"{i:<3} {s.cidr():<18} {int_to_ip(s.mask):<16} {int_to_ip(s.first_host):<16} "
            f"{int_to_ip(s.last_host):<16} {int_to_ip(s.broadcast):<16} {s.usable_hosts:>6}"
        )
    return "\n".join(lines)


def show_vlsm(allocation: list[tuple[str, int, Subnet]]) -> str:
    header = f"{'Name':<12} {'Needed':>6} {'Network':<18} {'Mask':<16} {'Range':<35} {'Usable':>6}"
    lines = [header, "-" * len(header)]
    for label, needed, s in allocation:
        host_range = f"{int_to_ip(s.first_host)} - {int_to_ip(s.last_host)}"
        lines.append(
            f"{label:<12} {needed:>6} {s.cidr():<18} {int_to_ip(s.mask):<16} "
            f"{host_range:<35} {s.usable_hosts:>6}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def parse_requirements(tokens: list[str]) -> list[tuple[str, int]]:
    reqs = []
    for i, token in enumerate(tokens, 1):
        label, sep, count = token.partition("=")
        if not sep:
            label, count = f"Subnet{i}", token
        if not count.isdigit():
            raise ValueError(f"Invalid host count in {token!r} (use 'Name=50' or '50')")
        reqs.append((label, int(count)))
    return reqs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="subnet_calc", description="IPv4 subnet calculator for CCNA practice"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_info = sub.add_parser("info", help="Show details for an address/prefix")
    p_info.add_argument("address", help="'192.168.1.77/26' or '192.168.1.77 255.255.255.192'")
    p_info.add_argument("-b", "--binary", action="store_true", help="Also show binary form")

    p_split = sub.add_parser("split", help="Split a network into equal subnets")
    p_split.add_argument("network", help="e.g. 192.168.10.0/24")
    p_split.add_argument("count", type=int, help="Number of subnets needed")

    p_vlsm = sub.add_parser("vlsm", help="Variable-length subnet allocation")
    p_vlsm.add_argument("network", help="e.g. 192.168.10.0/24")
    p_vlsm.add_argument("requirements", nargs="+", help="Hosts per subnet: Sales=60 Eng=28 10")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "info":
            addr, prefix = parse_address(args.address)
            print(show_info(Subnet(addr, prefix), binary=args.binary))
        elif args.command == "split":
            addr, prefix = parse_address(args.network)
            print(show_table(split_equal(Subnet(addr, prefix), args.count)))
        elif args.command == "vlsm":
            addr, prefix = parse_address(args.network)
            reqs = parse_requirements(args.requirements)
            print(show_vlsm(vlsm(Subnet(addr, prefix), reqs)))
    except ValueError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
