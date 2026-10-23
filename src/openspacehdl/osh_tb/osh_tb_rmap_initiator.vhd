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
-- RMAP initiator of the far ends: an OpenRMAP omap_core with the Initiator only (one outstanding
-- command, a reply timeout of ReplyTimeoutUs_g, 1 ms by default) and a sequencer that serves the
-- commands of the testbench on Cmd and Res (osh_tb_pkg). A command is a verified, incrementing write
-- with reply or an incrementing read with reply, without a Target SpaceWire Address and without a
-- Reply Address (a point-to-point link); the Transaction Identifier counts up. Res returns the status
-- of the reply, the local error of the initiator and the data of a read reply. The confirmation and
-- the reply data are always accepted, also outside a command (a late reply after a timeout).
--
-- Documentation: docs/design.md of openspacehdl, section 6.3

---------------------------------------------------------------------------------------------------
-- Libraries
---------------------------------------------------------------------------------------------------
library ieee;
    use ieee.std_logic_1164.all;
    use ieee.numeric_std.all;

library openrmap;

library work;
    use work.osh_tb_pkg.all;

---------------------------------------------------------------------------------------------------
-- Entity
---------------------------------------------------------------------------------------------------
entity osh_tb_rmap_initiator is
    generic (
        ClkHz_g          : positive;                       -- frequency of Clk, at least 1 MHz
        ReplyTimeoutUs_g : positive range 1 to 65535 := 1000  -- reply timeout of a command, in microseconds
    );
    port (
        Clk          : in    std_logic;
        Rst          : in    std_logic;
        -- N-Char streams to and from the link
        M_Pkt_TData  : out   std_logic_vector(7 downto 0);
        M_Pkt_TLast  : out   std_logic;
        M_Pkt_TValid : out   std_logic;
        M_Pkt_TReady : in    std_logic;
        S_Pkt_TData  : in    std_logic_vector(7 downto 0);
        S_Pkt_TLast  : in    std_logic;
        S_Pkt_TValid : in    std_logic;
        S_Pkt_TReady : out   std_logic;
        -- Commands of the testbench
        Cmd          : in    t_osh_rmap_cmd;
        Res          : out   t_osh_rmap_res := C_OSH_RMAP_RES_IDLE
    );
end entity;

---------------------------------------------------------------------------------------------------
-- Architecture
---------------------------------------------------------------------------------------------------
architecture sim of osh_tb_rmap_initiator is

    constant TickCycles_c : natural := ClkHz_g / 1_000_000 - 1;  -- one tick per microsecond
    constant Timeout_c    : natural := ReplyTimeoutUs_g;         -- reply timeout in ticks

    signal ReqValid     : std_logic                     := '0';
    signal ReqReady     : std_logic;
    signal ReqCode      : std_logic_vector(3 downto 0)  := "0000";
    signal ReqTla       : std_logic_vector(7 downto 0)  := x"FE";
    signal ReqKey       : std_logic_vector(7 downto 0)  := x"00";
    signal ReqTid       : std_logic_vector(15 downto 0) := (others => '0');
    signal ReqAddr      : std_logic_vector(39 downto 0) := (others => '0');
    signal ReqLen       : std_logic_vector(23 downto 0) := (others => '0');
    signal ReqDataData  : std_logic_vector(7 downto 0)  := (others => '0');
    signal ReqDataValid : std_logic                     := '0';
    signal ReqDataReady : std_logic;
    signal ConfValid    : std_logic;
    signal ConfStatus   : std_logic_vector(7 downto 0);
    signal ConfError    : std_logic_vector(1 downto 0);
    signal RepData      : std_logic_vector(7 downto 0);
    signal RepValid     : std_logic;

begin

    assert ClkHz_g >= 1_000_000
        report "osh_tb_rmap_initiator: ClkHz_g must be at least 1 MHz (one tick per microsecond)"
        severity failure;

    i_rmap : entity openrmap.omap_core
        generic map (
            Target_g       => false,
            Initiator_g    => true,
            Passthrough_g  => false,
            Transactions_g => 1,
            TickCycles_g   => TickCycles_c,
            Timeout_g      => Timeout_c
        )
        port map (
            Clk               => Clk,
            Rst               => Rst,
            S_Pkt_TData       => S_Pkt_TData,
            S_Pkt_TLast       => S_Pkt_TLast,
            S_Pkt_TValid      => S_Pkt_TValid,
            S_Pkt_TReady      => S_Pkt_TReady,
            M_Pkt_TData       => M_Pkt_TData,
            M_Pkt_TLast       => M_Pkt_TLast,
            M_Pkt_TValid      => M_Pkt_TValid,
            M_Pkt_TReady      => M_Pkt_TReady,
            M_User_TData      => open,
            M_User_TLast      => open,
            M_User_TValid     => open,
            S_User_TReady     => open,
            S_AxiLite_ArAddr  => (others => '0'),
            S_AxiLite_ArValid => '0',
            S_AxiLite_ArReady => open,
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
            S_AxiLite_RData   => open,
            S_AxiLite_RResp   => open,
            S_AxiLite_RValid  => open,
            S_AxiLite_RReady  => '1',
            Irq               => open,
            M_Axi_AwAddr      => open,
            M_Axi_AwLen       => open,
            M_Axi_AwSize      => open,
            M_Axi_AwBurst     => open,
            M_Axi_AwLock      => open,
            M_Axi_AwCache     => open,
            M_Axi_AwProt      => open,
            M_Axi_AwValid     => open,
            M_Axi_WData       => open,
            M_Axi_WStrb       => open,
            M_Axi_WLast       => open,
            M_Axi_WValid      => open,
            M_Axi_BReady      => open,
            M_Axi_ArAddr      => open,
            M_Axi_ArLen       => open,
            M_Axi_ArSize      => open,
            M_Axi_ArBurst     => open,
            M_Axi_ArLock      => open,
            M_Axi_ArCache     => open,
            M_Axi_ArProt      => open,
            M_Axi_ArValid     => open,
            M_Axi_RReady      => open,
            Auth_Valid        => open,
            Auth_Tla          => open,
            Auth_Instr        => open,
            Auth_Key          => open,
            Auth_Ila          => open,
            Auth_Tid          => open,
            Auth_Addr         => open,
            Auth_Len          => open,
            Ind_Valid         => open,
            Ind_Tla           => open,
            Ind_Instr         => open,
            Ind_Ila           => open,
            Ind_Tid           => open,
            Ind_Addr          => open,
            Ind_Len           => open,
            Ind_Status        => open,
            Ind_Replied       => open,
            S_Req_Valid       => ReqValid,
            S_Req_Ready       => ReqReady,
            S_Req_Code        => ReqCode,
            S_Req_TgtAddrLen  => (others => '0'),
            S_Req_Tla         => ReqTla,
            S_Req_Key         => ReqKey,
            S_Req_ReplyAddrLen => (others => '0'),
            S_Req_Ila         => x"FE",
            S_Req_Tid         => ReqTid,
            S_Req_Addr        => ReqAddr,
            S_Req_Len         => ReqLen,
            S_ReqData_TData   => ReqDataData,
            S_ReqData_TValid  => ReqDataValid,
            S_ReqData_TReady  => ReqDataReady,
            M_Conf_Valid      => ConfValid,
            M_Conf_Ready      => '1',
            M_Conf_Tid        => open,
            M_Conf_Instr      => open,
            M_Conf_Status     => ConfStatus,
            M_Conf_Len        => open,
            M_Conf_Error      => ConfError,
            M_RepData_TData   => RepData,
            M_RepData_TLast   => open,
            M_RepData_TValid  => RepValid,
            M_RepData_TReady  => '1'
        );

    p_seq : process is
        variable Res_v : t_osh_rmap_res := C_OSH_RMAP_RES_IDLE;
        variable Tid_v : unsigned(15 downto 0) := (others => '0');
        variable N_v   : natural;
    begin
        Res <= C_OSH_RMAP_RES_IDLE;

        loop
            wait until rising_edge(Clk) and Cmd.Req /= Res_v.Ack and Rst = '0';

            -- Request
            Tid_v    := Tid_v + 1;
            ReqCode  <= "0011";

            if Cmd.Write = '1' then
                ReqCode <= "1111";
            end if;

            ReqTla   <= Cmd.Tla;
            ReqKey   <= Cmd.Key;
            ReqTid   <= std_logic_vector(Tid_v);
            ReqAddr  <= Cmd.Addr;
            ReqLen   <= std_logic_vector(to_unsigned(Cmd.Len, 24));
            ReqValid <= '1';
            wait until rising_edge(Clk) and ReqReady = '1';
            ReqValid <= '0';

            -- Data of a write; the reply comes only after the command, so nothing is missed meanwhile
            if Cmd.Write = '1' then

                for I in 0 to Cmd.Len - 1 loop
                    ReqDataData  <= Cmd.Data(I);
                    ReqDataValid <= '1';
                    wait until rising_edge(Clk) and ReqDataReady = '1';
                end loop;

                ReqDataValid <= '0';
            end if;

            -- Reply data, then the confirmation
            N_v        := 0;
            Res_v.Data := (others => x"00");

            loop
                wait until rising_edge(Clk);

                if RepValid = '1' and N_v < C_OSH_RMAP_MAX_BYTES then
                    Res_v.Data(N_v) := RepData;
                    N_v             := N_v + 1;
                end if;

                exit when ConfValid = '1';
            end loop;

            Res_v.Status := ConfStatus;
            Res_v.Error  := to_integer(unsigned(ConfError));
            Res_v.Len    := N_v;
            Res_v.Ack    := Cmd.Req;
            Res          <= Res_v;
        end loop;

    end process;

end architecture;
