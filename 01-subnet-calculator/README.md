# IPv4 Subnet Calculator

A command-line IPv4 subnetting tool written in pure Python (no dependencies), built while studying for the **Cisco CCNA**. All calculations use bitwise operations on 32-bit integers, so the code mirrors how subnetting works on paper and on real network devices.

## Features

| Command | What it does |
|---------|--------------|
| `info`  | Full breakdown of an address: network, broadcast, host range, masks, wildcard, class, address type, optional binary view |
| `split` | Divide a network into equal-sized subnets |
| `vlsm`  | Allocate variable-length subnets from per-department host requirements (largest first, no overlaps) |

Also handles:
- CIDR (`/26`) and dotted-mask input (`"192.168.1.77 255.255.255.192"`)
- Rejection of invalid or non-contiguous masks
- `/31` point-to-point links (RFC 3021) and `/32` host routes
- Private (RFC 1918), loopback, link-local (APIPA) and multicast detection

## Requirements

Python 3.10 or newer. No third-party packages.

## Usage

### Address details

```
$ python3 subnet_calc.py info 192.168.1.77/26 --binary
Address           : 192.168.1.77
Address (bin)     : 11000000.10101000.00000001.01001101
Subnet mask       : 255.255.255.192 (/26)
Mask (bin)        : 11111111.11111111.11111111.11000000
Wildcard mask     : 0.0.0.63
Network address   : 192.168.1.64
Broadcast address : 192.168.1.127
First usable host : 192.168.1.65
Last usable host  : 192.168.1.126
Total addresses   : 64
Usable hosts      : 62
Class             : C
Type              : Private (RFC 1918)
```

### Split into equal subnets

```
$ python3 subnet_calc.py split 192.168.10.0/24 4
#   Network            Mask             First host       Last host        Broadcast         Hosts
-------------------------------------------------------------------------------------------------
1   192.168.10.0/26    255.255.255.192  192.168.10.1     192.168.10.62    192.168.10.63        62
2   192.168.10.64/26   255.255.255.192  192.168.10.65    192.168.10.126   192.168.10.127       62
3   192.168.10.128/26  255.255.255.192  192.168.10.129   192.168.10.190   192.168.10.191       62
4   192.168.10.192/26  255.255.255.192  192.168.10.193   192.168.10.254   192.168.10.255       62
```

### VLSM

```
$ python3 subnet_calc.py vlsm 192.168.10.0/24 Sales=60 Eng=28 Mgmt=10 WAN=2
Name         Needed Network            Mask             Range                               Usable
--------------------------------------------------------------------------------------------------
Sales            60 192.168.10.0/26    255.255.255.192  192.168.10.1 - 192.168.10.62            62
Eng              28 192.168.10.64/27   255.255.255.224  192.168.10.65 - 192.168.10.94           30
Mgmt             10 192.168.10.96/28   255.255.255.240  192.168.10.97 - 192.168.10.110          14
WAN               2 192.168.10.112/30  255.255.255.252  192.168.10.113 - 192.168.10.114          2
```

Requirements can be named (`Sales=60`) or just numbers (`60`).

## How it works

- **Network address** = IP AND mask
- **Wildcard mask** = NOT mask (the format used in Cisco ACLs and OSPF `network` statements)
- **Broadcast address** = network OR wildcard
- **Usable hosts** = 2^(host bits) - 2
- **VLSM** sorts requirements from largest to smallest and places each block back-to-back. This keeps every block correctly aligned on its boundary and wastes the least space.

## CCNA topics covered

- IPv4 addressing and classes
- Subnet masks, CIDR notation and wildcard masks
- Subnetting and VLSM
- Private vs public addressing (RFC 1918), APIPA
- Point-to-point links (/30 and /31)

## Testing

```
python3 -m unittest -v
```

The test suite cross-checks results against Python's built-in `ipaddress` module (used for verification only) and covers edge cases such as `/0`, `/31`, `/32`, invalid masks and VLSM overflow.

## Ideas for future improvements

- IPv6 support
- Export results to CSV
- Interactive quiz mode for subnetting practice

## Author

Nathan Stephen Onyango: IT professional | Cisco networking (CCNA 1-3), CompTIA Security+, CCD Level 1

## License

MIT
