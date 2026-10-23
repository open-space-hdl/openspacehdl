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
-- SpaceWire far end of the system testbenches: an OpenWire owr_core as the second port of a link of
-- the system, with the RMAP initiator osh_tb_rmap_initiator on its packet service. The harness joins
-- the lines crosswise (Spw_DOut to the system's Spw_DIn and so on). The port starts the link itself
-- (LinkStart and AutoStart), so the link comes up as soon as the system's port starts or answers.
-- LinkUp is '1' while the port is in the state Run (PORT_STATUS.LINK_STATE = 5, read from its own
-- register file every 32 cycles of Clk).
--
-- Documentation: docs/design.md of openspacehdl, section 6.3

---------------------------------------------------------------------------------------------------
-- Libraries
---------------------------------------------------------------------------------------------------
library ieee;
    use ieee.std_logic_1164.all;
    use ieee.numeric_std.all;

library openwire;

library work;
    use work.osh_tb_pkg.all;

---------------------------------------------------------------------------------------------------
-- Entity
---------------------------------------------------------------------------------------------------
entity osh_tb_spw_far_end is
    generic (
        LinkClkHz_g : positive;                    -- frequency of LinkClk
        ClkHz_g     : positive;                    -- frequency of Clk, at least 1 MHz
        RunDiv_g    : positive range 1 to 255 := 1; -- bit period in Run (LinkClk cycles), as the system's port
        -- Reply timeout of the RMAP initiator, in microseconds
        ReplyTimeoutUs_g : positive range 1 to 65535 := 1000
    );
    port (
        Clk      : in    std_logic;  -- packet service and register file
        LinkClk  : in    std_logic;  -- line drivers and receivers
        Rst      : in    std_logic;
        Spw_DOut : out   std_logic;
        Spw_SOut : out   std_logic;
        Spw_DIn  : in    std_logic;
        Spw_SIn  : in    std_logic;
        LinkUp   : out   std_logic := '0';
        Cmd      : in    t_osh_rmap_cmd;
        Res      : out   t_osh_rmap_res
    );
end entity;

---------------------------------------------------------------------------------------------------
-- Architecture
---------------------------------------------------------------------------------------------------
architecture sim of osh_tb_spw_far_end is

    constant PortStatus_c : std_logic_vector(7 downto 0) := x"18";

    -- Packet service between the port and the initiator
    signal TxData  : std_logic_vector(7 downto 0);
    signal TxLast  : std_logic;
    signal TxValid : std_logic;
    signal TxReady : std_logic;
    signal RxData  : std_logic_vector(7 downto 0);
    signal RxLast  : std_logic;
    signal RxValid : std_logic;
    signal RxReady : std_logic;

    -- Register file reads of the link state
    signal ArValid : std_logic := '0';
    signal ArReady : std_logic;
    signal RData   : std_logic_vector(31 downto 0);
    signal RValid  : std_logic;
    signal RReady  : std_logic := '0';

begin

    i_port : entity openwire.owr_core
        generic map (
            LinkClkFreq_g => real(LinkClkHz_g),
            LinkStart_g   => true,
            AutoStart_g   => true,
            RunDiv_g      => RunDiv_g
        )
        port map (
            Rst               => Rst,
            UserClk           => Clk,
            LinkClk           => LinkClk,
            MgmtClk           => Clk,
            S_Pkt_TData       => TxData,
            S_Pkt_TLast       => TxLast,
            S_Pkt_TValid      => TxValid,
            S_Pkt_TReady      => TxReady,
            M_Pkt_TData       => RxData,
            M_Pkt_TLast       => RxLast,
            M_Pkt_TValid      => RxValid,
            M_Pkt_TReady      => RxReady,
            S_Tc_TReady       => open,
            M_Tc_TData        => open,
            M_Tc_TValid       => open,
            S_Int_TReady      => open,
            S_IntAck_TReady   => open,
            M_Int_TData       => open,
            M_Int_TValid      => open,
            M_IntAck_TData    => open,
            M_IntAck_TValid   => open,
            S_AxiLite_ArAddr  => PortStatus_c,
            S_AxiLite_ArValid => ArValid,
            S_AxiLite_ArReady => ArReady,
            S_AxiLite_AwAddr  => (others => '0'),
            S_AxiLite_AwValid => '0',
            S_AxiLite_AwReady => open,
            S_AxiLite_WData   => (others => '0'),
            S_AxiLite_WStrb   => (others => '0'),
            S_AxiLite_WValid  => '0',
            S_AxiLite_WReady  => open,
            S_AxiLite_BResp   => open,
            S_AxiLite_BValid  => open,
            S_AxiLite_BReady  => '1',
            S_AxiLite_RData   => RData,
            S_AxiLite_RResp   => open,
            S_AxiLite_RValid  => RValid,
            S_AxiLite_RReady  => RReady,
            Irq               => open,
            Spw_DOut          => Spw_DOut,
            Spw_SOut          => Spw_SOut,
            Spw_DIn           => Spw_DIn,
            Spw_SIn           => Spw_SIn,
            Phy_TxEn          => open,
            Phy_RxEn          => open
        );

    i_initiator : entity work.osh_tb_rmap_initiator
        generic map (
            ClkHz_g          => ClkHz_g,
            ReplyTimeoutUs_g => ReplyTimeoutUs_g
        )
        port map (
            Clk          => Clk,
            Rst          => Rst,
            M_Pkt_TData  => TxData,
            M_Pkt_TLast  => TxLast,
            M_Pkt_TValid => TxValid,
            M_Pkt_TReady => TxReady,
            S_Pkt_TData  => RxData,
            S_Pkt_TLast  => RxLast,
            S_Pkt_TValid => RxValid,
            S_Pkt_TReady => RxReady,
            Cmd          => Cmd,
            Res          => Res
        );

    -- Link state: PORT_STATUS.LINK_STATE (bits 2:0), 5 = Run
    p_link : process is
    begin

        loop
            wait until rising_edge(Clk) and Rst = '0';
            ArValid <= '1';
            wait until rising_edge(Clk) and ArReady = '1';
            ArValid <= '0';
            RReady  <= '1';
            wait until rising_edge(Clk) and RValid = '1';
            RReady  <= '0';
            LinkUp  <= '0';

            if RData(2 downto 0) = "101" then
                LinkUp <= '1';
            end if;

            for I in 1 to 32 loop
                wait until rising_edge(Clk);
            end loop;

        end loop;

    end process;

end architecture;
