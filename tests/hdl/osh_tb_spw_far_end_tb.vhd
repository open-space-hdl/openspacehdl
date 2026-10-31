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
-- Testbench of osh_tb_spw_far_end: the far end against a stand-in of a system port (an owr_core with
-- LinkStart and AutoStart off, as in the SpaceWire examples of the Composer, and an RMAP target with
-- osh_tb_axi_mem as its memory). The test starts the port through its register file (PORT_CTRL, as the
-- generated smoke test does), waits for the link and accesses the memory with RMAP over the link.
-- Negative tests: without the start the link stays down, cut lines give the link timeout and the
-- reply timeout, a wrong key gives the status "invalid key". Packets of other protocols: the target of
-- the stand-in passes them on (Passthrough) to an echo, so that every packet the far end sends comes
-- back to its receive queue; a wrong expected packet gives a mismatch alert, a missing one the timeout,
-- a shorter one the length alert, and one that the echo ends with an error end (EEP) the EOP alert.

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

library uvvm_vvc_framework;
    use uvvm_vvc_framework.ti_vvc_framework_support_pkg.all;

library bitvis_vip_axilite;
    context bitvis_vip_axilite.vvc_context;

library openwire;

library openrmap;

library osh_tb;
    use osh_tb.osh_tb_pkg.all;
    use osh_tb.osh_tb_memvar_pkg.all;
    use osh_tb.osh_tb_stream_pkg.all;

---------------------------------------------------------------------------------------------------
-- Entity
---------------------------------------------------------------------------------------------------
entity osh_tb_spw_far_end_tb is
    generic (
        runner_cfg : string
    );
end entity;

---------------------------------------------------------------------------------------------------
-- Architecture
---------------------------------------------------------------------------------------------------
architecture sim of osh_tb_spw_far_end_tb is

    constant Period_c     : time    := 10 ns;  -- 100 MHz
    constant LinkPeriod_c : time    := 5 ns;   -- 200 MHz
    constant Fill_c       : natural := 1;
    constant Data_c       : natural := 9;
    constant Start_c      : natural := 16#1000# - 4;

    signal Clk     : std_logic := '0';
    signal LinkClk : std_logic := '0';
    signal Rst     : std_logic := '1';
    signal Cut     : std_logic := '0';  -- '1': both directions of the lines held at '0'

    signal Cmd    : t_osh_rmap_cmd := C_OSH_RMAP_CMD_IDLE;
    signal Res    : t_osh_rmap_res;
    signal LinkUp : std_logic;

    -- Lines
    signal FarD, FarS, SysD, SysS : std_logic;
    signal FarDIn, FarSIn, SysDIn, SysSIn : std_logic;

    -- Stand-in of the system: its port, register file, target and memory
    signal ArAddr, AwAddr : std_logic_vector(7 downto 0);
    signal ArValid, ArReady, AwValid, AwReady, WValid, WReady, BValid, BReady, RValid, RReady : std_logic;
    signal WData, RData : std_logic_vector(31 downto 0);
    signal WStrb : std_logic_vector(3 downto 0);
    signal BResp, RResp : std_logic_vector(1 downto 0);

    signal PktInData, PktOutData : std_logic_vector(7 downto 0);
    signal PktInLast, PktInValid, PktInReady, PktOutLast, PktOutValid, PktOutReady : std_logic;
    signal EchoData, EchoBack : std_logic_vector(7 downto 0);
    signal EchoLast, EchoValid, EchoReady : std_logic;
    signal ForceEep : std_logic := '0';

    signal MAwAddr, MArAddr, MWData, MRData : std_logic_vector(31 downto 0);
    signal MAwLen, MArLen : std_logic_vector(7 downto 0);
    signal MAwSize, MArSize : std_logic_vector(2 downto 0);
    signal MAwBurst, MArBurst, MBResp, MRResp : std_logic_vector(1 downto 0);
    signal MWStrb : std_logic_vector(3 downto 0);
    signal MAwValid, MAwReady, MWLast, MWValid, MWReady, MBValid, MBReady : std_logic;
    signal MArValid, MArReady, MRLast, MRValid, MRReady : std_logic;

begin

    Clk     <= not Clk after Period_c / 2;
    LinkClk <= not LinkClk after LinkPeriod_c / 2;

    i_uvvm : entity uvvm_vvc_framework.ti_uvvm_engine;

    -- Lines joined crosswise
    SysDIn <= FarD and not Cut;
    SysSIn <= FarS and not Cut;
    FarDIn <= SysD and not Cut;
    FarSIn <= SysS and not Cut;

    i_far : entity osh_tb.osh_tb_spw_far_end
        generic map (
            LinkClkHz_g => 200_000_000,
            ClkHz_g     => 100_000_000,
            RunDiv_g    => 2,
            ReplyTimeoutUs_g => 100
        )
        port map (
            Clk      => Clk,
            LinkClk  => LinkClk,
            Rst      => Rst,
            Spw_DOut => FarD,
            Spw_SOut => FarS,
            Spw_DIn  => FarDIn,
            Spw_SIn  => FarSIn,
            LinkUp   => LinkUp,
            Cmd      => Cmd,
            Res      => Res
        );

    i_port : entity openwire.owr_core
        generic map (
            LinkClkFreq_g => 200.0e6,
            RunDiv_g      => 2
        )
        port map (
            Rst               => Rst,
            UserClk           => Clk,
            LinkClk           => LinkClk,
            MgmtClk           => Clk,
            S_Pkt_TData       => PktOutData,
            S_Pkt_TLast       => PktOutLast,
            S_Pkt_TValid      => PktOutValid,
            S_Pkt_TReady      => PktOutReady,
            M_Pkt_TData       => PktInData,
            M_Pkt_TLast       => PktInLast,
            M_Pkt_TValid      => PktInValid,
            M_Pkt_TReady      => PktInReady,
            S_AxiLite_ArAddr  => ArAddr,
            S_AxiLite_ArValid => ArValid,
            S_AxiLite_ArReady => ArReady,
            S_AxiLite_AwAddr  => AwAddr,
            S_AxiLite_AwValid => AwValid,
            S_AxiLite_AwReady => AwReady,
            S_AxiLite_WData   => WData,
            S_AxiLite_WStrb   => WStrb,
            S_AxiLite_WValid  => WValid,
            S_AxiLite_WReady  => WReady,
            S_AxiLite_BResp   => BResp,
            S_AxiLite_BValid  => BValid,
            S_AxiLite_BReady  => BReady,
            S_AxiLite_RData   => RData,
            S_AxiLite_RResp   => RResp,
            S_AxiLite_RValid  => RValid,
            S_AxiLite_RReady  => RReady,
            Spw_DOut          => SysD,
            Spw_SOut          => SysS,
            Spw_DIn           => SysDIn,
            Spw_SIn           => SysSIn
        );

    i_mib : entity osh_tb.osh_tb_axilite_master
        generic map (
            Instance_g  => 0,
            AddrWidth_g => 8
        )
        port map (
            Clk     => Clk,
            ArAddr  => ArAddr,
            ArValid => ArValid,
            ArReady => ArReady,
            AwAddr  => AwAddr,
            AwValid => AwValid,
            AwReady => AwReady,
            WData   => WData,
            WStrb   => WStrb,
            WValid  => WValid,
            WReady  => WReady,
            BResp   => BResp,
            BValid  => BValid,
            BReady  => BReady,
            RData   => RData,
            RResp   => RResp,
            RValid  => RValid,
            RReady  => RReady
        );

    -- The echo returns every packet as it came, or with an error end (EEP: the marker with TData(0) '1')
    EchoBack <= EchoData(7 downto 1) & '1' when ForceEep = '1' and EchoLast = '1' else EchoData;

    i_target : entity openrmap.omap_core
        generic map (
            Target_g      => true,
            Initiator_g   => false,
            Passthrough_g => true
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
            -- Echo of the packets of other protocols
            M_User_TData      => EchoData,
            M_User_TLast      => EchoLast,
            M_User_TValid     => EchoValid,
            M_User_TReady     => EchoReady,
            S_User_TData      => EchoBack,
            S_User_TLast      => EchoLast,
            S_User_TValid     => EchoValid,
            S_User_TReady     => EchoReady,
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

        -- Starts the port of the stand-in: PORT_CTRL = AUTO_START, DRIVER_EN, RECEIVER_EN
        procedure startPort is
        begin
            axilite_write(AXILITE_VVCT, 0, x"10", x"00000038", "PORT_CTRL: AutoStart");
            await_completion(AXILITE_VVCT, 0, 10 us, "PORT_CTRL written");
        end procedure;

    begin
        test_runner_setup(runner, runner_cfg);
        disable_log_msg(ID_POS_ACK);
        await_uvvm_initialization(VOID);
        disable_log_msg(AXILITE_VVCT, 0, ALL_MESSAGES);

        while test_suite loop
            Rst <= '1';
            wait for 10 * Period_c;
            wait until rising_edge(Clk);
            Rst <= '0';
            wait for 10 * Period_c;

            if run("test_link_rmap") then
                axilite_check(AXILITE_VVCT, 0, x"00", x"4F575201", "ID of the stand-in");
                startPort;
                osh_await_link_up(LinkUp, 1 ms, "far end");
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
                -- The link stays up through the traffic (LinkUp reports Run, not a state before it)
                check_value(LinkUp, '1', ERROR, "link still up after the transfers");

            elsif run("test_wrong_key") then
                startPort;
                osh_await_link_up(LinkUp, 1 ms, "far end");
                osh_rmap_transfer(Cmd, Res, false, x"FE", x"A5", to_unsigned(Start_c, 40), Write_c, 4, Res_v, "key");
                check_value(Res_v.Error, 0, ERROR, "local error");
                check_value(Res_v.Status, x"03", ERROR, "status invalid key");

            elsif run("test_user_packets") then
                -- Packets of another protocol (Protocol Identifier 0x02) through the echo of the stand-in, next
                -- to RMAP: each comes back byte for byte
                startPort;
                osh_await_link_up(LinkUp, 1 ms, "far end");
                osh_link_send(0, 0, osh_cptp_header(x"FE", x"00") & osh_mem_bytes(to_unsigned(0, 64), 1, 11),
                              "packet 1");
                osh_link_send(0, 0, osh_cptp_header(x"FE", x"07") & osh_mem_bytes(to_unsigned(0, 64), 17, 12),
                              "packet 2");
                osh_rmap_write(Cmd, Res, x"FE", x"00", to_unsigned(Start_c, 40), Write_c, "RMAP between them");
                osh_link_send(0, 0, osh_cptp_header(x"FE", x"00") & osh_mem_bytes(to_unsigned(0, 64), 300, 13),
                              "packet 3");
                osh_link_check(0, 0, osh_cptp_header(x"FE", x"00") & osh_mem_bytes(to_unsigned(0, 64), 1, 11),
                               200 us, "echo 1");
                osh_link_check(0, 0, osh_cptp_header(x"FE", x"07") & osh_mem_bytes(to_unsigned(0, 64), 17, 12),
                               200 us, "echo 2");
                osh_link_check(0, 0, osh_cptp_header(x"FE", x"00") & osh_mem_bytes(to_unsigned(0, 64), 300, 13),
                               500 us, "echo 3");

            elsif run("test_user_packet_mismatch") then
                -- A packet that differs in one byte from the expected one raises one alert
                startPort;
                osh_await_link_up(LinkUp, 1 ms, "far end");
                osh_link_send(0, 0, osh_cptp_header(x"FE", x"00") & osh_mem_bytes(to_unsigned(0, 64), 9, 14),
                              "packet");
                increment_expected_alerts_and_stop_limit(ERROR, 1);
                osh_link_check(0, 0, osh_cptp_header(x"FE", x"01") & osh_mem_bytes(to_unsigned(0, 64), 9, 14),
                               200 us, "echo against another packet");

            elsif run("test_user_packet_short") then
                -- A packet one byte shorter than the expected one raises one alert, its length
                startPort;
                osh_await_link_up(LinkUp, 1 ms, "far end");
                osh_link_send(0, 0, osh_cptp_header(x"FE", x"00") & osh_mem_bytes(to_unsigned(0, 64), 9, 15),
                              "packet");
                increment_expected_alerts_and_stop_limit(ERROR, 1);
                osh_link_check(0, 0, osh_cptp_header(x"FE", x"00") & osh_mem_bytes(to_unsigned(0, 64), 10, 15),
                               200 us, "echo against a longer packet");

            elsif run("test_user_packet_error_end") then
                -- A packet that ends with an error end (EEP) raises one alert, its end of packet
                startPort;
                osh_await_link_up(LinkUp, 1 ms, "far end");
                ForceEep <= '1';
                osh_link_send(0, 0, osh_cptp_header(x"FE", x"00") & osh_mem_bytes(to_unsigned(0, 64), 9, 16),
                              "packet");
                increment_expected_alerts_and_stop_limit(ERROR, 1);
                osh_link_check(0, 0, osh_cptp_header(x"FE", x"00") & osh_mem_bytes(to_unsigned(0, 64), 9, 16),
                               200 us, "echo with an error end");

            elsif run("test_user_packet_timeout") then
                startPort;
                osh_await_link_up(LinkUp, 1 ms, "far end");
                increment_expected_alerts_and_stop_limit(TB_ERROR, 1);
                osh_link_check(0, 0, osh_cptp_header(x"FE", x"00"), 50 us, "no packet sent");

            elsif run("test_no_start") then
                -- The port of the stand-in neither starts nor answers: no link without the start
                increment_expected_alerts_and_stop_limit(TB_ERROR, 1);
                osh_await_link_up(LinkUp, 300 us, "far end without the start of the port");

            elsif run("test_dead_link") then
                Cut <= '1';
                startPort;
                increment_expected_alerts_and_stop_limit(TB_ERROR, 1);
                osh_await_link_up(LinkUp, 300 us, "far end with cut lines");
                osh_rmap_transfer(Cmd, Res, false, x"FE", x"00", to_unsigned(Start_c, 40), Write_c, 4, Res_v, "dead");
                check_value(Res_v.Error, 2, ERROR, "reply timeout over a dead link");
            end if;

        end loop;

        osh_test_end(runner);
    end process;

end architecture;
