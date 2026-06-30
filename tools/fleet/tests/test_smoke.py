def test_const_imports():
    from galeflash import const
    assert const.FMAP["FW_MAIN_A"] == (0x402000, 0x14DF00)
    assert "RW_SECTION_A" not in const.LEAF_FMAP
    assert const.ALLOWED_CHANGED == {"GBB", "RO_FRID", "FW_MAIN_A", "VBLOCK_A", "FW_MAIN_B", "VBLOCK_B"}
