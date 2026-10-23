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
-- SpaceFibre far end of the system testbenches: an OpenFibre ofb_core with its own physical adapter
-- ofb_pa_gty as the second port of a link of the system (in GHDL the adapter is its behavioural model,
-- the architecture mdl, with the control record ModelIdx_g of ofb_pa_model_pkg). The harness joins
-- lane i to lane i in both directions. The virtual channel RmapVc_g carries the RMAP initiator
-- osh_tb_rmap_initiator through an OpenSPP spp_nchar (N-Char stream to the link stream of the
-- channel). Every other channel v carries packets through the queues Index_g, v of osh_link
-- (osh_tb_link_pkg): received packets go to the receive queue, the packets of the send queue leave.
-- RmapVc_g = -1: no RMAP target behind the link; Cmd is ignored. The port starts its lanes itself (LaneStart and
-- AutoStart). LinkUp is '1' while the Data Link layer is initialised (DL_STATUS.LINK_STATE = 3, read
-- from its own register file every 32 cycles of ClkSys).
--
-- Documentation: docs/design.md of openspacehdl, section 6.3

---------------------------------------------------------------------------------------------------
-- Libraries
---------------------------------------------------------------------------------------------------
library ieee;
    use ieee.std_logic_1164.all;
    use ieee.numeric_std.all;

library openfibre;

library openspp;

library work;
    use work.osh_tb_pkg.all;
    use work.osh_tb_link_pkg.all;
    use work.osh_tb_linkvar_pkg.all;

---------------------------------------------------------------------------------------------------
-- Entity
---------------------------------------------------------------------------------------------------
entity osh_tb_spfi_far_end is
    generic (
        -- The generics of the system's SpaceFibre port
        NumLanes_g  : positive range 1 to 4  := 1;
        NumVc_g     : positive range 1 to 32 := 2;
        VcInDepth_g : positive               := 256;
        -- Virtual channel of the RMAP target of the system; -1: none
        RmapVc_g    : integer range -1 to 31 := 0;
        RefClkHz_g  : positive               := 156_250_000;  -- frequency of RefClk (the lane clock)
        SysClkHz_g  : positive;                                -- frequency of ClkSys, at least 1 MHz
        -- Control record of the adapter model; the system's adapter uses record 0
        ModelIdx_g  : natural range 1 to 7   := 1;
        -- Reply timeout of the RMAP initiator, in microseconds
        ReplyTimeoutUs_g : positive range 1 to 65535 := 1000;
        -- Queues of the far end in osh_link
        Index_g          : natural range 0 to 7      := 0
    );
    port (
        RefClk : in    std_logic;  -- reference clock of the transceivers, as for the system
        ClkSys : in    std_logic;  -- user, management and free-running clock
        Rst    : in    std_logic;
        Gt_TxP : out   std_logic_vector(NumLanes_g - 1 downto 0);
        Gt_TxN : out   std_logic_vector(NumLanes_g - 1 downto 0);
        Gt_RxP : in    std_logic_vector(NumLanes_g - 1 downto 0);
        Gt_RxN : in    std_logic_vector(NumLanes_g - 1 downto 0);
        LinkUp : out   std_logic := '0';
        Cmd    : in    t_osh_rmap_cmd;
        Res    : out   t_osh_rmap_res := C_OSH_RMAP_RES_IDLE
    );
end entity;

---------------------------------------------------------------------------------------------------
-- Architecture
---------------------------------------------------------------------------------------------------
architecture sim of osh_tb_spfi_far_end is

    constant Beat_c     : positive := 32 * NumLanes_g;  -- bits of one beat of a virtual channel
    constant DlStatus_c : std_logic_vector(11 downto 0) := x"010";

    signal LaneClk : std_logic;
    signal TxReady : std_logic;

    -- Virtual channels
    signal SVcTData  : std_logic_vector(Beat_c * NumVc_g - 1 downto 0)     := (others => '0');
    signal SVcTKeep  : std_logic_vector(Beat_c / 8 * NumVc_g - 1 downto 0) := (others => '0');
    signal SVcTLast  : std_logic_vector(NumVc_g - 1 downto 0)              := (others => '0');
    signal SVcTUser  : std_logic_vector(NumVc_g - 1 downto 0)              := (others => '0');
    signal SVcTValid : std_logic_vector(NumVc_g - 1 downto 0)              := (others => '0');
    signal SVcTReady : std_logic_vector(NumVc_g - 1 downto 0);
    signal MVcTData  : std_logic_vector(Beat_c * NumVc_g - 1 downto 0);
    signal MVcTKeep  : std_logic_vector(Beat_c / 8 * NumVc_g - 1 downto 0);
    signal MVcTLast  : std_logic_vector(NumVc_g - 1 downto 0);
    signal MVcTUser  : std_logic_vector(NumVc_g - 1 downto 0);
    signal MVcTValid : std_logic_vector(NumVc_g - 1 downto 0);
    signal MVcTReady : std_logic_vector(NumVc_g - 1 downto 0)              := (others => '1');

    -- Register file reads of the link state
    signal ArValid : std_logic := '0';
    signal ArReady : std_logic;
    signal RData   : std_logic_vector(31 downto 0);
    signal RValid  : std_logic;
    signal RReady  : std_logic := '0';

    -- Between the core and its physical adapter
    signal PhyTxData       : std_logic_vector(32 * NumLanes_g - 1 downto 0);
    signal PhyTxK          : std_logic_vector(4 * NumLanes_g - 1 downto 0);
    signal PhyRxData       : std_logic_vector(32 * NumLanes_g - 1 downto 0);
    signal PhyRxK          : std_logic_vector(4 * NumLanes_g - 1 downto 0);
    signal PhyRxCodeErr    : std_logic_vector(4 * NumLanes_g - 1 downto 0);
    signal PhyRxDispErr    : std_logic_vector(4 * NumLanes_g - 1 downto 0);
    signal PhyRxValid      : std_logic_vector(NumLanes_g - 1 downto 0);
    signal PhyTxEnable     : std_logic_vector(NumLanes_g - 1 downto 0);
    signal PhyRxEnable     : std_logic_vector(NumLanes_g - 1 downto 0);
    signal PhyCdrEnable    : std_logic_vector(NumLanes_g - 1 downto 0);
    signal PhyRxInvert     : std_logic_vector(NumLanes_g - 1 downto 0);
    signal PhyNoSignal     : std_logic_vector(NumLanes_g - 1 downto 0);
    signal PhyNearLoopback : std_logic_vector(NumLanes_g - 1 downto 0);
    signal PhyFarLoopback  : std_logic_vector(NumLanes_g - 1 downto 0);
    signal PhyPrbsTxSel    : std_logic_vector(4 * NumLanes_g - 1 downto 0);
    signal PhyPrbsRxSel    : std_logic_vector(4 * NumLanes_g - 1 downto 0);
    signal PhyPrbsForceErr : std_logic_vector(NumLanes_g - 1 downto 0);
    signal PhyPrbsCntReset : std_logic_vector(NumLanes_g - 1 downto 0);
    signal PhyPrbsErr      : std_logic_vector(NumLanes_g - 1 downto 0);
    signal PhyPrbsLocked   : std_logic_vector(NumLanes_g - 1 downto 0);
    signal PhyAligned      : std_logic_vector(NumLanes_g - 1 downto 0);

begin

    assert RmapVc_g < NumVc_g
        report "osh_tb_spfi_far_end: RmapVc_g must be a virtual channel of the port (or -1)"
        severity failure;

    -----------------------------------------------------------------------------------------------
    -- Physical adapter and SpaceFibre port
    -----------------------------------------------------------------------------------------------
    i_pa : entity openfibre.ofb_pa_gty
        generic map (
            NumLanes_g => NumLanes_g,
            ModelIdx_g => ModelIdx_g
        )
        port map (
            FreeRunClk             => ClkSys,
            Rst                    => Rst,
            RefClk                 => RefClk,
            LaneClk                => LaneClk,
            LaneRst                => open,
            Gt_TxP                 => Gt_TxP,
            Gt_TxN                 => Gt_TxN,
            Gt_RxP                 => Gt_RxP,
            Gt_RxN                 => Gt_RxN,
            PhyTx_Data             => PhyTxData,
            PhyTx_K                => PhyTxK,
            PhyRx_Data             => PhyRxData,
            PhyRx_K                => PhyRxK,
            PhyRx_CodeErr          => PhyRxCodeErr,
            PhyRx_DispErr          => PhyRxDispErr,
            PhyRx_Valid            => PhyRxValid,
            Phy_TxEnable           => PhyTxEnable,
            Phy_RxEnable           => PhyRxEnable,
            Phy_CdrEnable          => PhyCdrEnable,
            Phy_RxInvert           => PhyRxInvert,
            Phy_NoSignal           => PhyNoSignal,
            Phy_SerialNearLoopback => PhyNearLoopback,
            Phy_SerialFarLoopback  => PhyFarLoopback,
            Phy_PrbsTxSel          => PhyPrbsTxSel,
            Phy_PrbsRxSel          => PhyPrbsRxSel,
            Phy_PrbsForceErr       => PhyPrbsForceErr,
            Phy_PrbsCntReset       => PhyPrbsCntReset,
            Phy_PrbsErr            => PhyPrbsErr,
            Phy_PrbsLocked         => PhyPrbsLocked,
            Stat_TxReady           => TxReady,
            Stat_RxReady           => open,
            Stat_Aligned           => PhyAligned,
            Stat_RxBufErr          => open,
            Stat_ClkCor            => open
        );

    i_port : entity openfibre.ofb_core
        generic map (
            NumVc_g       => NumVc_g,
            NumLanes_g    => NumLanes_g,
            LaneClkFreq_g => real(RefClkHz_g),
            CoreClkFreq_g => real(RefClkHz_g),
            VcInDepth_g   => VcInDepth_g,
            LaneStart_g   => true,
            AutoStart_g   => true
        )
        port map (
            Rst                    => Rst,
            UserClk                => ClkSys,
            CoreClk                => LaneClk,
            LaneClk                => LaneClk,
            MgmtClk                => ClkSys,
            S_Vc_TData             => SVcTData,
            S_Vc_TKeep             => SVcTKeep,
            S_Vc_TLast             => SVcTLast,
            S_Vc_TUser             => SVcTUser,
            S_Vc_TValid            => SVcTValid,
            S_Vc_TReady            => SVcTReady,
            M_Vc_TData             => MVcTData,
            M_Vc_TKeep             => MVcTKeep,
            M_Vc_TLast             => MVcTLast,
            M_Vc_TUser             => MVcTUser,
            M_Vc_TValid            => MVcTValid,
            M_Vc_TReady            => MVcTReady,
            S_Bc_TData             => (others => '0'),
            S_Bc_TUser             => (others => '0'),
            S_Bc_TValid            => '0',
            S_Bc_TReady            => open,
            M_Bc_TData             => open,
            M_Bc_TUser             => open,
            M_Bc_TValid            => open,
            M_Bc_TReady            => '1',
            S_AxiLite_ArAddr       => DlStatus_c,
            S_AxiLite_ArValid      => ArValid,
            S_AxiLite_ArReady      => ArReady,
            S_AxiLite_AwAddr       => (others => '0'),
            S_AxiLite_AwValid      => '0',
            S_AxiLite_AwReady      => open,
            S_AxiLite_WData        => (others => '0'),
            S_AxiLite_WStrb        => (others => '0'),
            S_AxiLite_WValid       => '0',
            S_AxiLite_WReady       => open,
            S_AxiLite_BResp        => open,
            S_AxiLite_BValid       => open,
            S_AxiLite_BReady       => '1',
            S_AxiLite_RData        => RData,
            S_AxiLite_RResp        => open,
            S_AxiLite_RValid       => RValid,
            S_AxiLite_RReady       => RReady,
            Irq                    => open,
            PhyTx_Data             => PhyTxData,
            PhyTx_K                => PhyTxK,
            PhyRx_Data             => PhyRxData,
            PhyRx_K                => PhyRxK,
            PhyRx_CodeErr          => PhyRxCodeErr,
            PhyRx_DispErr          => PhyRxDispErr,
            PhyRx_Valid            => PhyRxValid,
            Phy_TxEnable           => PhyTxEnable,
            Phy_RxEnable           => PhyRxEnable,
            Phy_CdrEnable          => PhyCdrEnable,
            Phy_RxInvert           => PhyRxInvert,
            Phy_NoSignal           => PhyNoSignal,
            Phy_TxReady            => TxReady,
            Phy_BitSync            => PhyAligned,
            Phy_SerialNearLoopback => PhyNearLoopback,
            Phy_SerialFarLoopback  => PhyFarLoopback,
            Phy_PrbsTxSel          => PhyPrbsTxSel,
            Phy_PrbsRxSel          => PhyPrbsRxSel,
            Phy_PrbsForceErr       => PhyPrbsForceErr,
            Phy_PrbsCntReset       => PhyPrbsCntReset,
            Phy_PrbsErr            => PhyPrbsErr,
            Phy_PrbsLocked         => PhyPrbsLocked
        );

    -----------------------------------------------------------------------------------------------
    -- RMAP initiator on the virtual channel RmapVc_g
    -----------------------------------------------------------------------------------------------
    g_rmap : if RmapVc_g >= 0 generate
        constant Lo_c : natural := Beat_c * RmapVc_g;
        constant Ko_c : natural := Beat_c / 8 * RmapVc_g;

        signal TxData  : std_logic_vector(7 downto 0);
        signal TxLast  : std_logic;
        signal TxValid : std_logic;
        signal TxReady : std_logic;
        signal RxData  : std_logic_vector(7 downto 0);
        signal RxLast  : std_logic;
        signal RxValid : std_logic;
        signal RxReady : std_logic;
        signal LinkUsr : std_logic_vector(0 downto 0);
    begin

        i_nchar : entity openspp.spp_nchar
            generic map (
                DataWidth_g => Beat_c
            )
            port map (
                Clk           => ClkSys,
                Rst           => Rst,
                S_Link_Valid  => MVcTValid(RmapVc_g),
                S_Link_Ready  => MVcTReady(RmapVc_g),
                S_Link_Data   => MVcTData(Lo_c + Beat_c - 1 downto Lo_c),
                S_Link_Keep   => MVcTKeep(Ko_c + Beat_c / 8 - 1 downto Ko_c),
                S_Link_Last   => MVcTLast(RmapVc_g),
                S_Link_User   => "0000" & MVcTUser(RmapVc_g),
                M_NChar_Valid => RxValid,
                M_NChar_Ready => RxReady,
                M_NChar_Data  => RxData,
                M_NChar_Last  => RxLast,
                S_NChar_Valid => TxValid,
                S_NChar_Ready => TxReady,
                S_NChar_Data  => TxData,
                S_NChar_Last  => TxLast,
                M_Link_Valid  => SVcTValid(RmapVc_g),
                M_Link_Ready  => SVcTReady(RmapVc_g),
                M_Link_Data   => SVcTData(Lo_c + Beat_c - 1 downto Lo_c),
                M_Link_Keep   => SVcTKeep(Ko_c + Beat_c / 8 - 1 downto Ko_c),
                M_Link_Last   => SVcTLast(RmapVc_g),
                M_Link_User   => LinkUsr
            );

        SVcTUser(RmapVc_g) <= LinkUsr(0);

        i_initiator : entity work.osh_tb_rmap_initiator
            generic map (
                ClkHz_g          => SysClkHz_g,
                ReplyTimeoutUs_g => ReplyTimeoutUs_g
            )
            port map (
                Clk          => ClkSys,
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

    end generate;

    -----------------------------------------------------------------------------------------------
    -- Packets on the other virtual channels, through the queues
    -----------------------------------------------------------------------------------------------
    g_user : for V in 0 to NumVc_g - 1 generate

        g_vc : if V /= RmapVc_g generate
            constant Lo_c : natural := Beat_c * V;
            constant Ko_c : natural := Beat_c / 8 * V;
        begin

            -- Received packets: the bytes of every beat that TKeep marks; TUser with TLast is the EEP
            p_rx : process is
                variable Bytes_v : t_osh_byte_array(0 to C_OSH_LINK_MAX_BYTES - 1);
                variable N_v     : natural := 0;
            begin

                loop
                    wait until rising_edge(ClkSys) and MVcTValid(V) = '1';

                    for B in 0 to Beat_c / 8 - 1 loop

                        if MVcTKeep(Ko_c + B) = '1' and N_v < C_OSH_LINK_MAX_BYTES then
                            Bytes_v(N_v) := MVcTData(Lo_c + 8 * B + 7 downto Lo_c + 8 * B);
                            N_v          := N_v + 1;
                        end if;

                    end loop;

                    if MVcTLast(V) = '1' then
                        osh_link.push_rx(Index_g, V, Bytes_v(0 to N_v - 1), MVcTUser(V) = '1');
                        N_v := 0;
                    end if;

                end loop;

            end process;

            -- Packets of the send queue, Beat_c / 8 bytes per beat, the last beat with its valid bytes
            -- (the beat is built in variables, so that the process drives only the slices of channel V)
            p_tx : process is
                variable Len_v  : natural;
                variable I_v    : natural;
                variable Data_v : std_logic_vector(Beat_c - 1 downto 0);
                variable Keep_v : std_logic_vector(Beat_c / 8 - 1 downto 0);
            begin

                loop
                    wait until rising_edge(ClkSys) and Rst = '0' and osh_link.tx_count(Index_g, V) > 0;
                    Len_v := osh_link.tx_length(Index_g, V);
                    I_v   := 0;

                    loop
                        Data_v := (others => '0');
                        Keep_v := (others => '0');

                        for B in 0 to Beat_c / 8 - 1 loop

                            if I_v + B < Len_v then
                                Data_v(8 * B + 7 downto 8 * B) := osh_link.tx_byte(Index_g, V, I_v + B);
                                Keep_v(B)                      := '1';
                            end if;

                        end loop;

                        SVcTData(Lo_c + Beat_c - 1 downto Lo_c)     <= Data_v;
                        SVcTKeep(Ko_c + Beat_c / 8 - 1 downto Ko_c) <= Keep_v;
                        SVcTLast(V)                                 <= '0';

                        if I_v + Beat_c / 8 >= Len_v then
                            SVcTLast(V) <= '1';
                        end if;

                        SVcTValid(V) <= '1';
                        wait until rising_edge(ClkSys) and SVcTReady(V) = '1';
                        I_v := I_v + Beat_c / 8;
                        exit when I_v >= Len_v;
                    end loop;

                    SVcTValid(V) <= '0';
                    SVcTLast(V)  <= '0';
                    osh_link.pop_tx(Index_g, V);
                end loop;

            end process;

        end generate;

    end generate;

    -- Link state: DL_STATUS.LINK_STATE (bits 1:0), 3 = Link Initialised
    p_link : process is
    begin

        loop
            wait until rising_edge(ClkSys) and Rst = '0';
            ArValid <= '1';
            wait until rising_edge(ClkSys) and ArReady = '1';
            ArValid <= '0';
            RReady  <= '1';
            wait until rising_edge(ClkSys) and RValid = '1';
            RReady  <= '0';
            LinkUp  <= '0';

            if RData(1 downto 0) = "11" then
                LinkUp <= '1';
            end if;

            for I in 1 to 32 loop
                wait until rising_edge(ClkSys);
            end loop;

        end loop;

    end process;

end architecture;
