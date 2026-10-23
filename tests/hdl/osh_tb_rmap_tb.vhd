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
-- Testbench of osh_tb_rmap_initiator and the RMAP procedures of osh_tb_pkg: the initiator against an
-- OpenRMAP target (omap_core, Target only) whose memory is osh_tb_axi_mem, joined by their N-Char
-- streams. A write and read-back of 16 bytes across a 4 KB boundary over memory pre-filled with
-- another pattern (also the neighbours of the window, through the backdoor), the register check of
-- osh_rmap_check_word, and the negative tests: a wrong key gives the status "invalid key" (3), a cut
-- link the reply timeout of the initiator (local error 2), a far end that never answers the timeout
-- alert of the procedure.

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

library openrmap;

library osh_tb;
    use osh_tb.osh_tb_pkg.all;
    use osh_tb.osh_tb_memvar_pkg.all;
    use osh_tb.osh_tb_check_pkg.all;

---------------------------------------------------------------------------------------------------
-- Entity
---------------------------------------------------------------------------------------------------
entity osh_tb_rmap_tb is
    generic (
        runner_cfg : string
    );
end entity;

---------------------------------------------------------------------------------------------------
-- Architecture
---------------------------------------------------------------------------------------------------
architecture sim of osh_tb_rmap_tb is

    constant Period_c : time    := 10 ns;  -- 100 MHz
    constant Size_c   : natural := 16#2000#;
    constant Fill_c   : natural := 1;      -- initial pattern of the memory
    constant Data_c   : natural := 9;      -- pattern of the written data
    constant Start_c  : natural := 16#1000# - 4;

    signal Clk : std_logic := '0';
    signal Rst : std_logic := '1';
    signal Cut : std_logic := '0';  -- '1': the commands of the initiator are lost

    signal Cmd     : t_osh_rmap_cmd := C_OSH_RMAP_CMD_IDLE;
    signal Res     : t_osh_rmap_res;
    signal DeadCmd : t_osh_rmap_cmd := C_OSH_RMAP_CMD_IDLE;
    signal DeadRes : t_osh_rmap_res := C_OSH_RMAP_RES_IDLE;  -- a far end that never answers

    -- Initiator to target and back
    signal CmdData  : std_logic_vector(7 downto 0);
    signal CmdLast  : std_logic;
    signal CmdValid : std_logic;
    signal CmdReady : std_logic;
    signal TgtValid : std_logic;
    signal TgtReady : std_logic;
    signal RepData  : std_logic_vector(7 downto 0);
    signal RepLast  : std_logic;
    signal RepValid : std_logic;
    signal RepReady : std_logic;

    -- Memory of the target
    signal AwAddr  : std_logic_vector(31 downto 0);
    signal AwLen   : std_logic_vector(7 downto 0);
    signal AwSize  : std_logic_vector(2 downto 0);
    signal AwBurst : std_logic_vector(1 downto 0);
    signal AwValid : std_logic;
    signal AwReady : std_logic;
    signal WData   : std_logic_vector(31 downto 0);
    signal WStrb   : std_logic_vector(3 downto 0);
    signal WLast   : std_logic;
    signal WValid  : std_logic;
    signal WReady  : std_logic;
    signal BResp   : std_logic_vector(1 downto 0);
    signal BValid  : std_logic;
    signal BReady  : std_logic;
    signal ArAddr  : std_logic_vector(31 downto 0);
    signal ArLen   : std_logic_vector(7 downto 0);
    signal ArSize  : std_logic_vector(2 downto 0);
    signal ArBurst : std_logic_vector(1 downto 0);
    signal ArValid : std_logic;
    signal ArReady : std_logic;
    signal RData   : std_logic_vector(31 downto 0);
    signal RResp   : std_logic_vector(1 downto 0);
    signal RLast   : std_logic;
    signal RValid  : std_logic;
    signal RReady  : std_logic;

begin

    Clk <= not Clk after Period_c / 2;

    i_initiator : entity osh_tb.osh_tb_rmap_initiator
        generic map (
            ClkHz_g => 100_000_000
        )
        port map (
            Clk          => Clk,
            Rst          => Rst,
            M_Pkt_TData  => CmdData,
            M_Pkt_TLast  => CmdLast,
            M_Pkt_TValid => CmdValid,
            M_Pkt_TReady => CmdReady,
            S_Pkt_TData  => RepData,
            S_Pkt_TLast  => RepLast,
            S_Pkt_TValid => RepValid,
            S_Pkt_TReady => RepReady,
            Cmd          => Cmd,
            Res          => Res
        );

    -- The cut link swallows the commands
    TgtValid <= CmdValid and not Cut;
    CmdReady <= TgtReady or Cut;

    i_target : entity openrmap.omap_core
        generic map (
            Target_g      => true,
            Initiator_g   => false,
            Passthrough_g => false
        )
        port map (
            Clk               => Clk,
            Rst               => Rst,
            S_Pkt_TData       => CmdData,
            S_Pkt_TLast       => CmdLast,
            S_Pkt_TValid      => TgtValid,
            S_Pkt_TReady      => TgtReady,
            M_Pkt_TData       => RepData,
            M_Pkt_TLast       => RepLast,
            M_Pkt_TValid      => RepValid,
            M_Pkt_TReady      => RepReady,
            S_AxiLite_ArAddr  => (others => '0'),
            S_AxiLite_ArValid => '0',
            S_AxiLite_AwAddr  => (others => '0'),
            S_AxiLite_AwValid => '0',
            S_AxiLite_WData   => (others => '0'),
            S_AxiLite_WStrb   => (others => '0'),
            S_AxiLite_WValid  => '0',
            S_AxiLite_BReady  => '1',
            S_AxiLite_RReady  => '1',
            M_Axi_AwAddr      => AwAddr,
            M_Axi_AwLen       => AwLen,
            M_Axi_AwSize      => AwSize,
            M_Axi_AwBurst     => AwBurst,
            M_Axi_AwValid     => AwValid,
            M_Axi_AwReady     => AwReady,
            M_Axi_WData       => WData,
            M_Axi_WStrb       => WStrb,
            M_Axi_WLast       => WLast,
            M_Axi_WValid      => WValid,
            M_Axi_WReady      => WReady,
            M_Axi_BResp       => BResp,
            M_Axi_BValid      => BValid,
            M_Axi_BReady      => BReady,
            M_Axi_ArAddr      => ArAddr,
            M_Axi_ArLen       => ArLen,
            M_Axi_ArSize      => ArSize,
            M_Axi_ArBurst     => ArBurst,
            M_Axi_ArValid     => ArValid,
            M_Axi_ArReady     => ArReady,
            M_Axi_RData       => RData,
            M_Axi_RResp       => RResp,
            M_Axi_RLast       => RLast,
            M_Axi_RValid      => RValid,
            M_Axi_RReady      => RReady
        );

    i_mem : entity osh_tb.osh_tb_axi_mem
        generic map (
            Instance_g  => 0,
            AddrWidth_g => 32,
            DataWidth_g => 32,
            Base_g      => 0,
            SizeBytes_g => Size_c,
            Seed_g      => Fill_c
        )
        port map (
            Clk           => Clk,
            Rst           => Rst,
            S_Axi_AwAddr  => AwAddr,
            S_Axi_AwLen   => AwLen,
            S_Axi_AwSize  => AwSize,
            S_Axi_AwBurst => AwBurst,
            S_Axi_AwValid => AwValid,
            S_Axi_AwReady => AwReady,
            S_Axi_WData   => WData,
            S_Axi_WStrb   => WStrb,
            S_Axi_WLast   => WLast,
            S_Axi_WValid  => WValid,
            S_Axi_WReady  => WReady,
            S_Axi_BResp   => BResp,
            S_Axi_BValid  => BValid,
            S_Axi_BReady  => BReady,
            S_Axi_ArAddr  => ArAddr,
            S_Axi_ArLen   => ArLen,
            S_Axi_ArSize  => ArSize,
            S_Axi_ArBurst => ArBurst,
            S_Axi_ArValid => ArValid,
            S_Axi_ArReady => ArReady,
            S_Axi_RData   => RData,
            S_Axi_RResp   => RResp,
            S_Axi_RLast   => RLast,
            S_Axi_RValid  => RValid,
            S_Axi_RReady  => RReady
        );

    p_main : process is

        -- The bytes from first to last hold the test data of seed
        procedure checkMem (
            first : natural;
            last  : natural;
            seed  : natural;
            msg   : string) is
        begin

            for A in first to last loop
                check_value(osh_mem.read8(0, to_unsigned(A, 64)), osh_mem_byte(to_unsigned(A, 64), seed), ERROR,
                            msg & " 0x" & to_hstring(std_logic_vector(to_unsigned(A, 16))));
            end loop;

        end procedure;

        constant Write_c : t_osh_byte_array(0 to 15) := osh_mem_bytes(to_unsigned(Start_c, 64), 16, Data_c);

        variable Rd_v  : t_osh_byte_array(0 to 15);
        variable Res_v : t_osh_rmap_res;

    begin
        test_runner_setup(runner, runner_cfg);
        disable_log_msg(ID_POS_ACK);

        while test_suite loop
            Rst <= '1';
            Cut <= '0';
            wait for 10 * Period_c;
            wait until rising_edge(Clk);
            Rst <= '0';
            wait for 10 * Period_c;

            if run("test_write_read") then
                -- 16 bytes from 4 bytes before a 4 KB boundary; the neighbours keep the initial pattern
                osh_rmap_write(Cmd, Res, x"FE", x"00", to_unsigned(Start_c, 40), Write_c, "write");
                checkMem(Start_c, Start_c + 15, Data_c, "written");
                checkMem(Start_c - 16, Start_c - 1, Fill_c, "before the window");
                checkMem(Start_c + 16, Start_c + 31, Fill_c, "after the window");
                osh_rmap_read(Cmd, Res, x"FE", x"00", to_unsigned(Start_c, 40), 16, Rd_v, "read back");

                for I in 0 to 15 loop
                    check_value(Rd_v(I), Write_c(I), ERROR, "read back byte " & integer'image(I));
                end loop;

            elsif run("test_check_word") then
                -- The word at 0x100 holds the initial pattern; a wrong value must raise an alert
                osh_rmap_check_word(Cmd, Res, x"FE", x"00", to_unsigned(16#100#, 40),
                                    osh_mem_byte(to_unsigned(16#103#, 64), Fill_c) &
                                    osh_mem_byte(to_unsigned(16#102#, 64), Fill_c) &
                                    osh_mem_byte(to_unsigned(16#101#, 64), Fill_c) &
                                    osh_mem_byte(to_unsigned(16#100#, 64), Fill_c), "word at 0x100");
                increment_expected_alerts_and_stop_limit(ERROR, 1);
                osh_rmap_check_word(Cmd, Res, x"FE", x"00", to_unsigned(16#100#, 40), x"00000000", "a wrong value");

            elsif run("test_memory_check") then
                -- The memory check of the smoke test passes on an intact memory ...
                osh_rmap_memory_check(Cmd, Res, x"FE", x"00", to_unsigned(Start_c, 40), 0, Fill_c, Data_c, "check");

            elsif run("test_memory_check_finds_a_changed_neighbour") then
                -- ... and fails when a byte next to the window does not hold the initial data
                osh_mem.write8(0, to_unsigned(Start_c + 16 + 5, 64),
                               not osh_mem_byte(to_unsigned(Start_c + 16 + 5, 64), Fill_c));
                increment_expected_alerts_and_stop_limit(ERROR, 1);
                osh_rmap_memory_check(Cmd, Res, x"FE", x"00", to_unsigned(Start_c, 40), 0, Fill_c, Data_c, "check");

            elsif run("test_wrong_key") then
                -- TG-AU-04 of OpenRMAP: a command with another key is not executed, status 3
                osh_rmap_transfer(Cmd, Res, true, x"FE", x"5A", to_unsigned(Start_c, 40), Write_c, 16, Res_v, "key");
                check_value(Res_v.Error, 0, ERROR, "local error");
                check_value(Res_v.Status, x"03", ERROR, "status invalid key");
                checkMem(Start_c, Start_c + 15, Fill_c, "not written");

            elsif run("test_cut_link") then
                Cut <= '1';
                osh_rmap_transfer(Cmd, Res, false, x"FE", x"00", to_unsigned(Start_c, 40), Write_c, 4, Res_v, "cut");
                check_value(Res_v.Error, 2, ERROR, "reply timeout of the initiator");

            elsif run("test_no_answer") then
                increment_expected_alerts_and_stop_limit(TB_ERROR, 1);
                osh_rmap_transfer(DeadCmd, DeadRes, false, x"FE", x"00", to_unsigned(0, 40), Write_c, 4, Res_v,
                                  "no far end");
                check_value(Res_v.Error, 2, ERROR, "a missing result counts as a timeout");
            end if;

        end loop;

        osh_test_end(runner);
    end process;

end architecture;
