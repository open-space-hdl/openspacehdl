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
-- AXI4-Stream receiver of the system testbenches: the UVVM AXI4-Stream VVC (instance Instance_g of
-- AXISTREAM_VVCT, slave) at a stream output (source) of the system. Data of a width that is not a
-- multiple of 8 reaches the VVC zero-extended to the next multiple of 8 bits (the UVVM BFM needs whole
-- bytes). Without a keep signal (KeepWidth_g = 0) every byte counts as valid; without a user signal
-- (UserWidth_g = 0) the VVC sees user 0. The VVC holds Ready low except while it receives.
--
-- Documentation: docs/design.md of openspacehdl, section 6.3

---------------------------------------------------------------------------------------------------
-- Libraries
---------------------------------------------------------------------------------------------------
library ieee;
    use ieee.std_logic_1164.all;
    use ieee.numeric_std.all;

library bitvis_vip_axistream;
    use bitvis_vip_axistream.axistream_bfm_pkg.all;

---------------------------------------------------------------------------------------------------
-- Entity
---------------------------------------------------------------------------------------------------
entity osh_tb_axis_slave is
    generic (
        Instance_g  : natural;
        DataWidth_g : positive;
        KeepWidth_g : natural := 0;
        UserWidth_g : natural := 0
    );
    port (
        Clk   : in    std_logic;
        Data  : in    std_logic_vector(DataWidth_g - 1 downto 0);
        Keep  : in    std_logic_vector(maximum(KeepWidth_g, 1) - 1 downto 0) := (others => '1');
        User  : in    std_logic_vector(maximum(UserWidth_g, 1) - 1 downto 0) := (others => '0');
        Last  : in    std_logic                                              := '0';
        Valid : in    std_logic;
        Ready : out   std_logic
    );
end entity;

---------------------------------------------------------------------------------------------------
-- Architecture
---------------------------------------------------------------------------------------------------
architecture sim of osh_tb_axis_slave is

    constant VvcWidth_c : positive := 8 * ((DataWidth_g + 7) / 8);
    constant UserW_c    : positive := maximum(UserWidth_g, 1);

    signal AxisIf : t_axistream_if(
        tdata(VvcWidth_c - 1 downto 0),
        tkeep(VvcWidth_c / 8 - 1 downto 0),
        tuser(UserW_c - 1 downto 0),
        tstrb(VvcWidth_c / 8 - 1 downto 0),
        tid(0 downto 0),
        tdest(0 downto 0)) := init_axistream_if_signals(false, VvcWidth_c, UserW_c, 1, 1);

begin

    AxisIf.tdata  <= std_logic_vector(resize(unsigned(Data), VvcWidth_c));
    AxisIf.tkeep  <= std_logic_vector(resize(unsigned(Keep), VvcWidth_c / 8)) when KeepWidth_g > 0 else
                     (others => '1');
    AxisIf.tuser  <= std_logic_vector(resize(unsigned(User), UserW_c)) when UserWidth_g > 0 else (others => '0');
    AxisIf.tlast  <= Last;
    AxisIf.tvalid <= Valid;
    AxisIf.tstrb  <= (others => '1');
    AxisIf.tid    <= (others => '0');
    AxisIf.tdest  <= (others => '0');
    Ready         <= AxisIf.tready;

    i_vvc : entity bitvis_vip_axistream.axistream_vvc
        generic map (
            GC_VVC_IS_MASTER => false,
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
