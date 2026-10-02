# References and provenance

[Documents](../README.md)

The controller is a Python lab implementation. Downloaded C/C++ reference files, third-party source snapshots, device administration HTML, and captured WSC messages from the working lab are not included here.

Protocol and implementation references used during development:

- [Wireshark IEEE 1905 fields](https://www.wireshark.org/docs/dfref/i/ieee1905.html)
- [pyieee1905 message definitions](https://github.com/evanslai/pyieee1905/blob/master/pyieee1905/multiap_msg.py)
- [prplMesh WSC construction](https://github.com/prplfoundation/prplMesh/blob/master/framework/tlvf/src/src/WSC/m2.cpp)
- [prplMesh encrypted configuration attributes](https://github.com/prplfoundation/prplMesh/blob/master/framework/tlvf/src/src/WSC/configData.cpp)
- [RDK unified-wifi-mesh definitions](https://github.com/rdkcentral/unified-wifi-mesh/blob/main/inc/em_base.h)
- [EasyMesh labs](https://mesh.vcpe.dev/) and [OpenSync lab topology](https://vcpe.dev/opensync-lab/topology/) provided visual inspiration for the topology view.

Message/TLV names and numeric values in `protocol_names.json` are a protocol lookup dictionary; recognition of a name does not imply a complete decoder or implemented feature.

Synthetic test messages use locally administered MAC addresses and test-only credentials. The synthetic DH exponent is for a fixture only; live M2 generation uses fresh cryptographic randomness.

No project license has been selected. The repository owner should choose a license before granting reuse rights. Dependencies retain their own licenses and are installed separately, not vendored.
