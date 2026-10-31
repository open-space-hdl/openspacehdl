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
-- AXI4-Lite master of the system testbenches: the UVVM AXI4-Lite VVC (instance Instance_g of
-- AXILITE_VVCT) with the signals of a register port of the system. The testbench sends its commands
-- with axilite_write, axilite_read and axilite_check; the BFM checks every response against OKAY.
--
-- Documentation: docs/design.md of openspacehdl, section 6.3

---------------------------------------------------------------------------------------------------
-- Libraries
---------------------------------------------------------------------------------------------------
library ieee;
    use ieee.std_logic_1164.all;

library bitvis_vip_axilite;
    use bitvis_vip_axilite.axilite_bfm_pkg.all;

---------------------------------------------------------------------------------------------------
-- Entity
---------------------------------------------------------------------------------------------------
entity osh_tb_axilite_master is
    generic (
        Instance_g  : natural;
        AddrWidth_g : positive
    );
    port (
        Clk     : in    std_logic;
        ArAddr  : out   std_logic_vector(AddrWidth_g - 1 downto 0);
        ArValid : out   std_logic;
        ArReady : in    std_logic;
        AwAddr  : out   std_logic_vector(AddrWidth_g - 1 downto 0);
        AwValid : out   std_logic;
        AwReady : in    std_logic;
        WData   : out   std_logic_vector(31 downto 0);
        WStrb   : out   std_logic_vector(3 downto 0);
        WValid  : out   std_logic;
        WReady  : in    std_logic;
        BResp   : in    std_logic_vector(1 downto 0);
        BValid  : in    std_logic;
        BReady  : out   std_logic;
        RData   : in    std_logic_vector(31 downto 0);
        RResp   : in    std_logic_vector(1 downto 0);
        RValid  : in    std_logic;
        RReady  : out   std_logic
    );
end entity;

---------------------------------------------------------------------------------------------------
-- Architecture
---------------------------------------------------------------------------------------------------
architecture sim of osh_tb_axilite_master is

    signal AxiIf : t_axilite_if(
        write_address_channel(awaddr(AddrWidth_g - 1 downto 0)),
        write_data_channel(wdata(31 downto 0), wstrb(3 downto 0)),
        read_address_channel(araddr(AddrWidth_g - 1 downto 0)),
        read_data_channel(rdata(31 downto 0))) := init_axilite_if_signals(AddrWidth_g, 32);

begin

    AxiIf.write_address_channel.awready <= AwReady;
    AxiIf.write_data_channel.wready     <= WReady;
    AxiIf.write_response_channel.bresp  <= BResp;
    AxiIf.write_response_channel.bvalid <= BValid;
    AxiIf.read_address_channel.arready  <= ArReady;
    AxiIf.read_data_channel.rdata       <= RData;
    AxiIf.read_data_channel.rresp       <= RResp;
    AxiIf.read_data_channel.rvalid      <= RValid;

    ArAddr  <= AxiIf.read_address_channel.araddr;
    ArValid <= AxiIf.read_address_channel.arvalid;
    AwAddr  <= AxiIf.write_address_channel.awaddr;
    AwValid <= AxiIf.write_address_channel.awvalid;
    WData   <= AxiIf.write_data_channel.wdata;
    WStrb   <= AxiIf.write_data_channel.wstrb;
    WValid  <= AxiIf.write_data_channel.wvalid;
    BReady  <= AxiIf.write_response_channel.bready;
    RReady  <= AxiIf.read_data_channel.rready;

    i_vvc : entity bitvis_vip_axilite.axilite_vvc
        generic map (
            GC_ADDR_WIDTH   => AddrWidth_g,
            GC_DATA_WIDTH   => 32,
            GC_INSTANCE_IDX => Instance_g
        )
        port map (
            clk                   => Clk,
            axilite_vvc_master_if => AxiIf
        );

end architecture;
