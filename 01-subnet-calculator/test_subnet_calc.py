"""Tests for subnet_calc. Results are cross-checked against the stdlib
``ipaddress`` module, which is used here only for verification."""

import ipaddress
import unittest

from subnet_calc import (
    Subnet,
    int_to_ip,
    ip_to_int,
    mask_to_prefix,
    parse_address,
    parse_requirements,
    prefix_for_hosts,
    prefix_to_mask,
    split_equal,
    vlsm,
)


class TestConversions(unittest.TestCase):
    def test_round_trip(self):
        for ip in ("0.0.0.0", "192.168.1.10", "255.255.255.255", "10.0.0.1"):
            self.assertEqual(int_to_ip(ip_to_int(ip)), ip)

    def test_invalid_addresses(self):
        for bad in ("256.1.1.1", "1.2.3", "a.b.c.d", "1.2.3.4.5", ""):
            with self.assertRaises(ValueError):
                ip_to_int(bad)

    def test_prefix_mask_round_trip(self):
        for prefix in range(33):
            self.assertEqual(mask_to_prefix(prefix_to_mask(prefix)), prefix)

    def test_non_contiguous_mask_rejected(self):
        with self.assertRaises(ValueError):
            mask_to_prefix(ip_to_int("255.0.255.0"))

    def test_parse_formats(self):
        self.assertEqual(parse_address("192.168.1.10/24"), (ip_to_int("192.168.1.10"), 24))
        self.assertEqual(parse_address("192.168.1.10 255.255.255.0"), (ip_to_int("192.168.1.10"), 24))
        with self.assertRaises(ValueError):
            parse_address("192.168.1.10/33")
            Subnet(*parse_address("192.168.1.10/33")).mask


class TestSubnetAgainstStdlib(unittest.TestCase):
    CASES = [
        "192.168.1.77/26", "10.1.2.3/8", "172.16.5.9/20", "192.168.0.0/24",
        "10.0.0.0/30", "8.8.8.8/32", "100.64.0.1/31", "0.0.0.0/0", "203.0.113.200/25",
    ]

    def test_matches_ipaddress(self):
        for text in self.CASES:
            with self.subTest(text):
                addr, prefix = parse_address(text)
                mine = Subnet(addr, prefix)
                ref = ipaddress.ip_network(text, strict=False)
                self.assertEqual(int_to_ip(mine.network), str(ref.network_address))
                self.assertEqual(int_to_ip(mine.broadcast), str(ref.broadcast_address))
                self.assertEqual(int_to_ip(mine.mask), str(ref.netmask))
                self.assertEqual(int_to_ip(mine.wildcard), str(ref.hostmask))
                self.assertEqual(mine.total_addresses, ref.num_addresses)
                if prefix <= 30:
                    hosts = list(ref.hosts()) if prefix >= 16 else None
                    self.assertEqual(mine.usable_hosts, ref.num_addresses - 2)
                    if hosts:
                        self.assertEqual(int_to_ip(mine.first_host), str(hosts[0]))
                        self.assertEqual(int_to_ip(mine.last_host), str(hosts[-1]))

    def test_special_prefixes(self):
        self.assertEqual(Subnet(ip_to_int("10.0.0.0"), 31).usable_hosts, 2)
        self.assertEqual(Subnet(ip_to_int("10.0.0.5"), 32).usable_hosts, 1)

    def test_class_and_type(self):
        self.assertEqual(Subnet(ip_to_int("10.1.1.1"), 8).address_class, "A")
        self.assertEqual(Subnet(ip_to_int("172.16.1.1"), 12).address_class, "B")
        self.assertEqual(Subnet(ip_to_int("192.168.1.1"), 24).address_class, "C")
        self.assertEqual(Subnet(ip_to_int("192.168.1.1"), 24).address_type, "Private (RFC 1918)")
        self.assertEqual(Subnet(ip_to_int("172.32.0.1"), 16).address_type, "Public")
        self.assertEqual(Subnet(ip_to_int("169.254.3.4"), 16).address_type, "Link-local (APIPA)")
        self.assertEqual(Subnet(ip_to_int("127.0.0.1"), 8).address_type, "Loopback")


class TestSplit(unittest.TestCase):
    def test_split_matches_stdlib(self):
        net = Subnet(ip_to_int("192.168.10.0"), 24)
        mine = [s.cidr() for s in split_equal(net, 4)]
        ref = [str(n) for n in ipaddress.ip_network("192.168.10.0/24").subnets(prefixlen_diff=2)]
        self.assertEqual(mine, ref)

    def test_rounds_up_to_power_of_two(self):
        net = Subnet(ip_to_int("10.0.0.0"), 24)
        self.assertEqual(len(split_equal(net, 5)), 8)

    def test_too_many_subnets(self):
        with self.assertRaises(ValueError):
            split_equal(Subnet(ip_to_int("10.0.0.0"), 30), 8)


class TestVLSM(unittest.TestCase):
    def test_prefix_for_hosts(self):
        self.assertEqual(prefix_for_hosts(2), 30)
        self.assertEqual(prefix_for_hosts(1), 30)
        self.assertEqual(prefix_for_hosts(30), 27)
        self.assertEqual(prefix_for_hosts(31), 26)
        self.assertEqual(prefix_for_hosts(60), 26)
        self.assertEqual(prefix_for_hosts(254), 24)

    def test_classic_allocation(self):
        net = Subnet(ip_to_int("192.168.10.0"), 24)
        reqs = [("WAN", 2), ("Sales", 60), ("Mgmt", 10), ("Eng", 28)]
        result = vlsm(net, reqs)
        got = {label: s.cidr() for label, _, s in result}
        self.assertEqual(got["Sales"], "192.168.10.0/26")
        self.assertEqual(got["Eng"], "192.168.10.64/27")
        self.assertEqual(got["Mgmt"], "192.168.10.96/28")
        self.assertEqual(got["WAN"], "192.168.10.112/30")

    def test_no_overlap_and_fits_hosts(self):
        net = Subnet(ip_to_int("10.0.0.0"), 22)
        reqs = [("A", 500), ("B", 120), ("C", 60), ("D", 30), ("E", 2), ("F", 2)]
        result = vlsm(net, reqs)
        blocks = [ipaddress.ip_network(s.cidr()) for _, _, s in result]
        for i, a in enumerate(blocks):
            for b in blocks[i + 1:]:
                self.assertFalse(a.overlaps(b))
        for _, needed, s in result:
            self.assertGreaterEqual(s.usable_hosts, needed)

    def test_out_of_space(self):
        net = Subnet(ip_to_int("192.168.10.0"), 24)
        with self.assertRaises(ValueError):
            vlsm(net, [("A", 120), ("B", 120), ("C", 120)])

    def test_requirement_parsing(self):
        self.assertEqual(parse_requirements(["Sales=60", "10"]), [("Sales", 60), ("Subnet2", 10)])
        with self.assertRaises(ValueError):
            parse_requirements(["Sales=abc"])


if __name__ == "__main__":
    unittest.main()
