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
-- Testbench of osh_tb_spfi_far_end: the far end against a stand-in of a system port (ofb_pa_gty with
-- the control record 0 of the model, an ofb_core with the default start, LaneStart off and AutoStart
-- on, and on the virtual channel RmapVc_g an spp_nchar with an RMAP target whose memory is
-- osh_tb_axi_mem), lane i joined to lane i. The test waits for the link and accesses the memory with
-- RMAP over the link. Negative tests: lanes of the far end in electrical idle give the link timeout
-- and the reply timeout, a wrong key gives the status "invalid key". The other virtual channel of the
-- stand-in is an echo, so that every packet the far end sends on it comes back to its receive queue; a
-- wrong expected packet gives a mismatch alert, a missing one the timeout.

---------------------------------------------------------------------------------------------------
-- Libraries
---------------------------------------------------------------------------------------------------
library ieee;
    use ieee.std_logic_1164.all;
    use ieee.numeric_std.all;

library vunit_lib;
    context vunit_lib.vunit_run_context;

library uvvm_util;
    context uvvm_util.uvvm_util_context;

library openfibre;
    use openfibre.ofb_pa_model_pkg.all;

library openspp;

library openrmap;

library osh_tb;
    use osh_tb.osh_tb_pkg.all;
    use osh_tb.osh_tb_memvar_pkg.all;
    use osh_tb.osh_tb_stream_pkg.all;

---------------------------------------------------------------------------------------------------
-- Entity
---------------------------------------------------------------------------------------------------
entity osh_tb_spfi_far_end_tb is
    generic (
        runner_cfg : string;
        NumLanes_g : positive range 1 to 4 := 1;
        RmapVc_g   : natural range 0 to 1  := 1
    );
end entity;

---------------------------------------------------------------------------------------------------
-- Architecture
---------------------------------------------------------------------------------------------------
architecture sim of osh_tb_spfi_far_end_tb is

    constant RefPeriod_c : time     := 6.4 ns;  -- 156.25 MHz
    constant Period_c    : time     := 10 ns;   -- 100 MHz
    constant NumVc_c     : positive := 2;
    constant Beat_c      : positive := 32 * NumLanes_g;
    constant Fill_c      : natural  := 1;
    constant Data_c      : natural  := 9;
    constant Start_c     : natural  := 16#1000# - 4;
    constant Echo_c      : natural  := 1 - RmapVc_g;  -- the virtual channel without the RMAP target

    constant IdleLane_c : PaModelLane_t := (
        TxInvert => false,
        SkewUi   => 0,
        Idle     => true,
        ErrReq   => 0,
        BurstReq => 0,
        BurstLen => 8,
        ErrEvery => 0
    );

    signal RefClk : std_logic := '0';
    signal Clk    : std_logic := '0';
    signal Rst    : std_logic := '1';

    signal Cmd    : t_osh_rmap_cmd := C_OSH_RMAP_CMD_IDLE;
    signal Res    : t_osh_rmap_res;
    signal LinkUp : std_logic;

    -- Lanes
    signal FarTxP, FarTxN, SysTxP, SysTxN : std_logic_vector(NumLanes_g - 1 downto 0);

    -- Stand-in of the system
    signal LaneClk, TxReady : std_logic;
    signal PhyTxData, PhyRxData : std_logic_vector(32 * NumLanes_g - 1 downto 0);
    signal PhyTxK, PhyRxK, PhyRxCodeErr, PhyRxDispErr, PhyPrbsTxSel, PhyPrbsRxSel :
        std_logic_vector(4 * NumLanes_g - 1 downto 0);
    signal PhyRxValid, PhyTxEnable, PhyRxEnable, PhyCdrEnable, PhyRxInvert, PhyNoSignal, PhyNearLoopback,
        PhyFarLoopback, PhyPrbsForceErr, PhyPrbsCntReset, PhyPrbsErr, PhyPrbsLocked, PhyAligned :
        std_logic_vector(NumLanes_g - 1 downto 0);

    signal SVcTData  : std_logic_vector(Beat_c * NumVc_c - 1 downto 0)     := (others => '0');
    signal SVcTKeep  : std_logic_vector(Beat_c / 8 * NumVc_c - 1 downto 0) := (others => '0');
    signal SVcTLast  : std_logic_vector(NumVc_c - 1 downto 0)              := (others => '0');
    signal SVcTUser  : std_logic_vector(NumVc_c - 1 downto 0)              := (others => '0');
    signal SVcTValid : std_logic_vector(NumVc_c - 1 downto 0)              := (others => '0');
    signal SVcTReady : std_logic_vector(NumVc_c - 1 downto 0);
    signal MVcTData  : std_logic_vector(Beat_c * NumVc_c - 1 downto 0);
    signal MVcTKeep  : std_logic_vector(Beat_c / 8 * NumVc_c - 1 downto 0);
    signal MVcTLast  : std_logic_vector(NumVc_c - 1 downto 0);
    signal MVcTUser  : std_logic_vector(NumVc_c - 1 downto 0);
    signal MVcTValid : std_logic_vector(NumVc_c - 1 downto 0);
    signal MVcTReady : std_logic_vector(NumVc_c - 1 downto 0)              := (others => '1');
    signal LinkUsr   : std_logic_vector(0 downto 0);

    signal PktInData, PktOutData : std_logic_vector(7 downto 0);
    signal PktInLast, PktInValid, PktInReady, PktOutLast, PktOutValid, PktOutReady : std_logic;

    signal MAwAddr, MArAddr, MWData, MRData : std_logic_vector(31 downto 0);
    signal MAwLen, MArLen : std_logic_vector(7 downto 0);
    signal MAwSize, MArSize : std_logic_vector(2 downto 0);
    signal MAwBurst, MArBurst, MBResp, MRResp : std_logic_vector(1 downto 0);
    signal MWStrb : std_logic_vector(3 downto 0);
    signal MAwValid, MAwReady, MWLast, MWValid, MWReady, MBValid, MBReady : std_logic;
    signal MArValid, MArReady, MRLast, MRValid, MRReady : std_logic;

begin

    RefClk <= not RefClk after RefPeriod_c / 2;
    Clk    <= not Clk after Period_c / 2;

    i_far : entity osh_tb.osh_tb_spfi_far_end
        generic map (
            NumLanes_g  => NumLanes_g,
            NumVc_g     => NumVc_c,
            VcInDepth_g => 256 * NumLanes_g,
            RmapVc_g    => RmapVc_g,
            RefClkHz_g  => 156_250_000,
            SysClkHz_g  => 100_000_000,
            ModelIdx_g  => 1,
            -- A short reply timeout: the model of a lane in electrical idle is slow to simulate
            ReplyTimeoutUs_g => 100
        )
        port map (
            RefClk => RefClk,
            ClkSys => Clk,
            Rst    => Rst,
            Gt_TxP => FarTxP,
            Gt_TxN => FarTxN,
            Gt_RxP => SysTxP,
            Gt_RxN => SysTxN,
            LinkUp => LinkUp,
            Cmd    => Cmd,
            Res    => Res
        );

    i_pa : entity openfibre.ofb_pa_gty
        generic map (
            NumLanes_g => NumLanes_g,
            ModelIdx_g => 0
        )
        port map (
            FreeRunClk             => Clk,
            Rst                    => Rst,
            RefClk                 => RefClk,
            LaneClk                => LaneClk,
            LaneRst                => open,
            Gt_TxP                 => SysTxP,
            Gt_TxN                 => SysTxN,
            Gt_RxP                 => FarTxP,
            Gt_RxN                 => FarTxN,
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
            NumVc_g       => NumVc_c,
            NumLanes_g    => NumLanes_g,
            LaneClkFreq_g => 156.25e6,
            CoreClkFreq_g => 156.25e6,
            VcInDepth_g   => 256 * NumLanes_g
        )
        port map (
            Rst                    => Rst,
            UserClk                => Clk,
            CoreClk                => LaneClk,
            LaneClk                => LaneClk,
            MgmtClk                => Clk,
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
            S_AxiLite_ArAddr       => (others => '0'),
            S_AxiLite_ArValid      => '0',
            S_AxiLite_ArReady      => open,
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
            S_AxiLite_RData        => open,
            S_AxiLite_RResp        => open,
            S_AxiLite_RValid       => open,
            S_AxiLite_RReady       => '1',
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

    i_nchar : entity openspp.spp_nchar
        generic map (
            DataWidth_g => Beat_c
        )
        port map (
            Clk           => Clk,
            Rst           => Rst,
            S_Link_Valid  => MVcTValid(RmapVc_g),
            S_Link_Ready  => MVcTReady(RmapVc_g),
            S_Link_Data   => MVcTData(Beat_c * RmapVc_g + Beat_c - 1 downto Beat_c * RmapVc_g),
            S_Link_Keep   => MVcTKeep(Beat_c / 8 * RmapVc_g + Beat_c / 8 - 1 downto Beat_c / 8 * RmapVc_g),
            S_Link_Last   => MVcTLast(RmapVc_g),
            S_Link_User   => "0000" & MVcTUser(RmapVc_g),
            M_NChar_Valid => PktInValid,
            M_NChar_Ready => PktInReady,
            M_NChar_Data  => PktInData,
            M_NChar_Last  => PktInLast,
            S_NChar_Valid => PktOutValid,
            S_NChar_Ready => PktOutReady,
            S_NChar_Data  => PktOutData,
            S_NChar_Last  => PktOutLast,
            M_Link_Valid  => SVcTValid(RmapVc_g),
            M_Link_Ready  => SVcTReady(RmapVc_g),
            M_Link_Data   => SVcTData(Beat_c * RmapVc_g + Beat_c - 1 downto Beat_c * RmapVc_g),
            M_Link_Keep   => SVcTKeep(Beat_c / 8 * RmapVc_g + Beat_c / 8 - 1 downto Beat_c / 8 * RmapVc_g),
            M_Link_Last   => SVcTLast(RmapVc_g),
            M_Link_User   => LinkUsr
        );

    SVcTUser(RmapVc_g) <= LinkUsr(0);

    -- Echo on the other virtual channel
    SVcTData(Beat_c * Echo_c + Beat_c - 1 downto Beat_c * Echo_c)
        <= MVcTData(Beat_c * Echo_c + Beat_c - 1 downto Beat_c * Echo_c);
    SVcTKeep(Beat_c / 8 * Echo_c + Beat_c / 8 - 1 downto Beat_c / 8 * Echo_c)
        <= MVcTKeep(Beat_c / 8 * Echo_c + Beat_c / 8 - 1 downto Beat_c / 8 * Echo_c);
    SVcTLast(Echo_c)  <= MVcTLast(Echo_c);
    SVcTUser(Echo_c)  <= MVcTUser(Echo_c);
    SVcTValid(Echo_c) <= MVcTValid(Echo_c);
    MVcTReady(Echo_c) <= SVcTReady(Echo_c);

    i_target : entity openrmap.omap_core
        generic map (
            Target_g      => true,
            Initiator_g   => false,
            Passthrough_g => false
        )
        port map (
            Clk               => Clk,
            Rst               => Rst,
            S_Pkt_TData       => PktInData,
            S_Pkt_TLast       => PktInLast,
            S_Pkt_TValid      => PktInValid,
            S_Pkt_TReady      => PktInReady,
            M_Pkt_TData       => PktOutData,
            M_Pkt_TLast       => PktOutLast,
            M_Pkt_TValid      => PktOutValid,
            M_Pkt_TReady      => PktOutReady,
            S_AxiLite_ArAddr  => (others => '0'),
            S_AxiLite_ArValid => '0',
            S_AxiLite_AwAddr  => (others => '0'),
            S_AxiLite_AwValid => '0',
            S_AxiLite_WData   => (others => '0'),
            S_AxiLite_WStrb   => (others => '0'),
            S_AxiLite_WValid  => '0',
            S_AxiLite_BReady  => '1',
            S_AxiLite_RReady  => '1',
            M_Axi_AwAddr      => MAwAddr,
            M_Axi_AwLen       => MAwLen,
            M_Axi_AwSize      => MAwSize,
            M_Axi_AwBurst     => MAwBurst,
            M_Axi_AwValid     => MAwValid,
            M_Axi_AwReady     => MAwReady,
            M_Axi_WData       => MWData,
            M_Axi_WStrb       => MWStrb,
            M_Axi_WLast       => MWLast,
            M_Axi_WValid      => MWValid,
            M_Axi_WReady      => MWReady,
            M_Axi_BResp       => MBResp,
            M_Axi_BValid      => MBValid,
            M_Axi_BReady      => MBReady,
            M_Axi_ArAddr      => MArAddr,
            M_Axi_ArLen       => MArLen,
            M_Axi_ArSize      => MArSize,
            M_Axi_ArBurst     => MArBurst,
            M_Axi_ArValid     => MArValid,
            M_Axi_ArReady     => MArReady,
            M_Axi_RData       => MRData,
            M_Axi_RResp       => MRResp,
            M_Axi_RLast       => MRLast,
            M_Axi_RValid      => MRValid,
            M_Axi_RReady      => MRReady
        );

    i_mem : entity osh_tb.osh_tb_axi_mem
        generic map (
            Instance_g  => 0,
            AddrWidth_g => 32,
            DataWidth_g => 32,
            Base_g      => 0,
            SizeBytes_g => 16#2000#,
            Seed_g      => Fill_c
        )
        port map (
            Clk           => Clk,
            Rst           => Rst,
            S_Axi_AwAddr  => MAwAddr,
            S_Axi_AwLen   => MAwLen,
            S_Axi_AwSize  => MAwSize,
            S_Axi_AwBurst => MAwBurst,
            S_Axi_AwValid => MAwValid,
            S_Axi_AwReady => MAwReady,
            S_Axi_WData   => MWData,
            S_Axi_WStrb   => MWStrb,
            S_Axi_WLast   => MWLast,
            S_Axi_WValid  => MWValid,
            S_Axi_WReady  => MWReady,
            S_Axi_BResp   => MBResp,
            S_Axi_BValid  => MBValid,
            S_Axi_BReady  => MBReady,
            S_Axi_ArAddr  => MArAddr,
            S_Axi_ArLen   => MArLen,
            S_Axi_ArSize  => MArSize,
            S_Axi_ArBurst => MArBurst,
            S_Axi_ArValid => MArValid,
            S_Axi_ArReady => MArReady,
            S_Axi_RData   => MRData,
            S_Axi_RResp   => MRResp,
            S_Axi_RLast   => MRLast,
            S_Axi_RValid  => MRValid,
            S_Axi_RReady  => MRReady
        );

    p_main : process is

        constant Write_c : t_osh_byte_array(0 to 15) := osh_mem_bytes(to_unsigned(Start_c, 64), 16, Data_c);

        variable Rd_v  : t_osh_byte_array(0 to 15);
        variable Res_v : t_osh_rmap_res;

    begin
        test_runner_setup(runner, runner_cfg);
        disable_log_msg(ID_POS_ACK);

        while test_suite loop
            Rst <= '1';
            wait for 10 * Period_c;
            wait until rising_edge(Clk);
            Rst <= '0';

            if run("test_link_rmap") then
                osh_await_link_up(LinkUp, 3 ms, "far end");
                osh_rmap_write(Cmd, Res, x"FE", x"00", to_unsigned(Start_c, 40), Write_c, "write over the link");
                osh_rmap_read(Cmd, Res, x"FE", x"00", to_unsigned(Start_c, 40), 16, Rd_v, "read over the link");

                for I in 0 to 15 loop
                    check_value(Rd_v(I), Write_c(I), ERROR, "read back byte " & integer'image(I));
                    check_value(osh_mem.read8(0, to_unsigned(Start_c + I, 64)), Write_c(I), ERROR,
                                "memory byte " & integer'image(I));
                end loop;

                check_value(osh_mem.read8(0, to_unsigned(Start_c - 1, 64)),
                            osh_mem_byte(to_unsigned(Start_c - 1, 64), Fill_c), ERROR, "byte before the window");
                check_value(osh_mem.read8(0, to_unsigned(Start_c + 16, 64)),
                            osh_mem_byte(to_unsigned(Start_c + 16, 64), Fill_c), ERROR, "byte after the window");
                -- The link stays up through the traffic (LinkUp reports Link Initialised, not a state before it)
                check_value(LinkUp, '1', ERROR, "link still up after the transfers");

            elsif run("test_wrong_key") then
                osh_await_link_up(LinkUp, 3 ms, "far end");
                osh_rmap_transfer(Cmd, Res, false, x"FE", x"A5", to_unsigned(Start_c, 40), Write_c, 4, Res_v, "key");
                check_value(Res_v.Error, 0, ERROR, "local error");
                check_value(Res_v.Status, x"03", ERROR, "status invalid key");

            elsif run("test_user_packets") then
                -- Packets on the virtual channel without the RMAP target, through the echo of the stand-in;
                -- lengths below, at and above a beat of the lanes
                osh_await_link_up(LinkUp, 3 ms, "far end");
                osh_link_send(0, Echo_c, osh_cptp_header(x"FE", x"00") & osh_mem_bytes(to_unsigned(0, 64), 1, 11),
                              "packet 1");
                osh_link_send(0, Echo_c, osh_cptp_header(x"FE", x"07") & osh_mem_bytes(to_unsigned(0, 64), 12, 12),
                              "packet 2");
                osh_link_send(0, Echo_c, osh_cptp_header(x"FE", x"00") & osh_mem_bytes(to_unsigned(0, 64), 301, 13),
                              "packet 3");
                osh_link_check(0, Echo_c, osh_cptp_header(x"FE", x"00") & osh_mem_bytes(to_unsigned(0, 64), 1, 11),
                               200 us, "echo 1");
                osh_link_check(0, Echo_c, osh_cptp_header(x"FE", x"07") & osh_mem_bytes(to_unsigned(0, 64), 12, 12),
                               200 us, "echo 2");
                osh_link_check(0, Echo_c, osh_cptp_header(x"FE", x"00") & osh_mem_bytes(to_unsigned(0, 64), 301, 13),
                               200 us, "echo 3");

            elsif run("test_user_packet_mismatch") then
                osh_await_link_up(LinkUp, 3 ms, "far end");
                osh_link_send(0, Echo_c, osh_cptp_header(x"FE", x"00") & osh_mem_bytes(to_unsigned(0, 64), 9, 14),
                              "packet");
                increment_expected_alerts_and_stop_limit(ERROR, 1);
                osh_link_check(0, Echo_c, osh_cptp_header(x"FE", x"01") & osh_mem_bytes(to_unsigned(0, 64), 9, 14),
                               200 us, "echo against another packet");

            elsif run("test_user_packet_timeout") then
                osh_await_link_up(LinkUp, 3 ms, "far end");
                increment_expected_alerts_and_stop_limit(TB_ERROR, 1);
                osh_link_check(0, Echo_c, osh_cptp_header(x"FE", x"00"), 50 us, "no packet sent");

            elsif run("test_dead_link") then
                -- The far end transmits electrical idle on every lane
                PaModelCtrl(1).Lane <= (others => IdleLane_c);
                increment_expected_alerts_and_stop_limit(TB_ERROR, 1);
                osh_await_link_up(LinkUp, 300 us, "far end with idle lanes");
                osh_rmap_transfer(Cmd, Res, false, x"FE", x"00", to_unsigned(Start_c, 40), Write_c, 4, Res_v, "dead");
                check_value(Res_v.Error, 2, ERROR, "reply timeout over a dead link");
            end if;

        end loop;

        osh_test_end(runner);
    end process;

end architecture;
