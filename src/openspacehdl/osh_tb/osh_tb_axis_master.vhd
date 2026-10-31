---------------------------------------------------------------------------------------------------
-- Copyright (c) 2026 Julian Schneider
--
-- Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
-- associated documentation files (the "Software"), to deal in the Software without restriction,
-- including without limitation the rights to use, copy, modify, merge, publish, distribute,
-- sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
-- furnished to do so, subject to the following conditions:
--
-- The above copyright notice and this permission notice shall be included in all copies or substantial
-- portions of the Software.
--
-- THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
-- NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
-- NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES
-- OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
-- CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
---------------------------------------------------------------------------------------------------

---------------------------------------------------------------------------------------------------
-- Description
---------------------------------------------------------------------------------------------------
-- AXI4-Stream transmitter of the system testbenches: the UVVM AXI4-Stream VVC (instance Instance_g of
-- AXISTREAM_VVCT, master) at a stream input (sink) of the system. The UVVM BFM needs data in whole
-- bytes, so a width that is not a multiple of 8 (for example 12-bit samples) is padded: the VVC sends
-- words of the next multiple of 8 bits, and the system gets their lower DataWidth_g bits. KeepWidth_g
-- and UserWidth_g of 0 mean that the stream has no keep or user signal; the port then has one bit and
-- stays open.
--
-- Documentation: docs/design.md of openspacehdl, section 6.3

---------------------------------------------------------------------------------------------------
-- Libraries
---------------------------------------------------------------------------------------------------
library ieee;
    use ieee.std_logic_1164.all;

library bitvis_vip_axistream;
    use bitvis_vip_axistream.axistream_bfm_pkg.all;

---------------------------------------------------------------------------------------------------
-- Entity
---------------------------------------------------------------------------------------------------
entity osh_tb_axis_master is
    generic (
        Instance_g  : natural;
        DataWidth_g : positive;
        KeepWidth_g : natural := 0;
        UserWidth_g : natural := 0
    );
    port (
        Clk   : in    std_logic;
        Data  : out   std_logic_vector(DataWidth_g - 1 downto 0);
        Keep  : out   std_logic_vector(maximum(KeepWidth_g, 1) - 1 downto 0);
        User  : out   std_logic_vector(maximum(UserWidth_g, 1) - 1 downto 0);
        Last  : out   std_logic;
        Valid : out   std_logic;
        Ready : in    std_logic
    );
end entity;

---------------------------------------------------------------------------------------------------
-- Architecture
---------------------------------------------------------------------------------------------------
architecture sim of osh_tb_axis_master is

    constant VvcWidth_c : positive := 8 * ((DataWidth_g + 7) / 8);
    constant UserW_c    : positive := maximum(UserWidth_g, 1);

    signal AxisIf : t_axistream_if(
        tdata(VvcWidth_c - 1 downto 0),
        tkeep(VvcWidth_c / 8 - 1 downto 0),
        tuser(UserW_c - 1 downto 0),
        tstrb(VvcWidth_c / 8 - 1 downto 0),
        tid(0 downto 0),
        tdest(0 downto 0)) := init_axistream_if_signals(true, VvcWidth_c, UserW_c, 1, 1);

begin

    Data          <= AxisIf.tdata(DataWidth_g - 1 downto 0);
    Keep          <= AxisIf.tkeep(Keep'range) when KeepWidth_g > 0 else (others => '1');
    User          <= AxisIf.tuser(User'range);
    Last          <= AxisIf.tlast;
    Valid         <= AxisIf.tvalid;
    AxisIf.tready <= Ready;

    i_vvc : entity bitvis_vip_axistream.axistream_vvc
        generic map (
            GC_VVC_IS_MASTER => true,
            GC_DATA_WIDTH    => VvcWidth_c,
            GC_USER_WIDTH    => UserW_c,
            GC_ID_WIDTH      => 1,
            GC_DEST_WIDTH    => 1,
            GC_INSTANCE_IDX  => Instance_g
        )
        port map (
            clk              => Clk,
            axistream_vvc_if => AxisIf
        );

end architecture;
