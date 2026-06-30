from galeflash import vpd, const


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
