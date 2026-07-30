from galeflash import vpd, const


def test_vpd_truncated_mid_entry_does_not_raise():
    """vpd.decode on a buffer truncated mid-entry must return a dict, not raise.

    Buffer layout:
      - 8-byte "gVpdInfo" magic
      - 5-byte version/size metadata (mimics real header)
      - 1-byte type 0x01 (string-pair entry)
      - NO further bytes (truncated before the key-length varint)

    Without the _pad_len bounds guard this triggered IndexError at position 14.
    """
    header = b"gVpdInfo" + b"\x04\x0d\x7f\x00\x00"  # 13 bytes: magic + meta
    buf = header + b"\x01"                            # type byte only, then EOF
    result = vpd.decode(buf)
    assert isinstance(result, dict)


def test_vpd_decodes_g4_identity(stock_g4):
    off, size = const.FMAP["RO_VPD"]
    kv = vpd.decode(stock_g4[off:off+size])
    assert kv["serial_number"] == "2831HW00VZA"
    assert kv["ethernet_mac0"] == "44070B0187B4"
    assert kv["ethernet_mac1"] == "44070B0187B5"
    assert kv["mlb_serial_number"] == "NJOKI350392FX01"
    assert kv["model_name"] == "AC1304"
    assert "region" in kv


def test_vpd_rw_does_not_raise(stock_g4):
    off, size = const.FMAP["RW_VPD"]
    kv = vpd.decode(stock_g4[off:off+size])
    assert isinstance(kv, dict)
