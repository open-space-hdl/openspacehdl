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
-- Memory of the AXI4 memory responder osh_tb_axi_mem: a protected type with one byte array per
-- responder instance and the backdoor access of the testbench. The object itself is the shared
-- variable osh_mem of osh_tb_memvar_pkg (a shared variable of a protected type is declared after the
-- protected body, in a package of its own).
--
-- Documentation: docs/design.md of openspacehdl, section 6.3

---------------------------------------------------------------------------------------------------
-- Libraries
---------------------------------------------------------------------------------------------------
library ieee;
    use ieee.std_logic_1164.all;
    use ieee.numeric_std.all;

library work;
    use work.osh_tb_pkg.all;

---------------------------------------------------------------------------------------------------
-- Package Header
---------------------------------------------------------------------------------------------------
package osh_tb_mem_pkg is

    -- Responder instances (Instance_g of osh_tb_axi_mem)
    constant C_OSH_MEM_INSTANCES : positive := 8;

    type t_osh_mem is protected
        -- Allocates the memory of instance idx: size bytes from base on, filled with
        -- osh_mem_byte(address, seed). A second call fills the memory again.
        procedure init (
            idx  : natural;
            base : unsigned;
            size : positive;
            seed : natural);
        -- True when the byte at addr is in the memory of instance idx
        impure function contains (
            idx  : natural;
            addr : unsigned) return boolean;
        -- Backdoor access; an address outside the memory reads 0x00 and is not written
        procedure write8 (
            idx  : natural;
            addr : unsigned;
            data : std_logic_vector(7 downto 0));
        impure function read8 (
            idx  : natural;
            addr : unsigned) return std_logic_vector;
        -- Fills n bytes from addr on with osh_mem_byte(address, seed)
        procedure fill (
            idx  : natural;
            addr : unsigned;
            n    : natural;
            seed : natural);
    end protected;

end package;

---------------------------------------------------------------------------------------------------
-- Package Body
---------------------------------------------------------------------------------------------------
package body osh_tb_mem_pkg is

    type t_osh_mem is protected body

        type t_bytes is array (natural range <>) of std_logic_vector(7 downto 0);
        type t_bytes_ptr is access t_bytes;
        type t_ptr_array is array (0 to C_OSH_MEM_INSTANCES - 1) of t_bytes_ptr;
        type t_base_array is array (0 to C_OSH_MEM_INSTANCES - 1) of unsigned(63 downto 0);

        variable Mem_v  : t_ptr_array;
        variable Base_v : t_base_array := (others => (others => '0'));

        -- Offset of addr in the memory of idx, or -1 outside it
        impure function offset (
            idx  : natural;
            addr : unsigned) return integer is
            variable A_v : unsigned(63 downto 0);
        begin
            A_v := resize(addr, 64);

            if Mem_v(idx) = null or A_v < Base_v(idx) then
                return -1;
            end if;

            if A_v - Base_v(idx) >= to_unsigned(Mem_v(idx)'length, 64) then
                return -1;
            end if;

            return to_integer(A_v - Base_v(idx));
        end function;

        procedure init (
            idx  : natural;
            base : unsigned;
            size : positive;
            seed : natural) is
        begin

            if Mem_v(idx) /= null then
                deallocate(Mem_v(idx));
            end if;

            Mem_v(idx)  := new t_bytes(0 to size - 1);
            Base_v(idx) := resize(base, 64);

            for I in 0 to size - 1 loop
                Mem_v(idx)(I) := osh_mem_byte(Base_v(idx) + I, seed);
            end loop;

        end procedure;

        impure function contains (
            idx  : natural;
            addr : unsigned) return boolean is
        begin
            return offset(idx, addr) >= 0;
        end function;

        procedure write8 (
            idx  : natural;
            addr : unsigned;
            data : std_logic_vector(7 downto 0)) is
            constant Off_c : integer := offset(idx, addr);
        begin

            if Off_c >= 0 then
                Mem_v(idx)(Off_c) := data;
            end if;

        end procedure;

        impure function read8 (
            idx  : natural;
            addr : unsigned) return std_logic_vector is
            constant Off_c : integer := offset(idx, addr);
        begin

            if Off_c < 0 then
                return x"00";
            end if;

            return Mem_v(idx)(Off_c);
        end function;

        procedure fill (
            idx  : natural;
            addr : unsigned;
            n    : natural;
            seed : natural) is
        begin

            for I in 0 to n - 1 loop
                write8(idx, resize(addr, 64) + I, osh_mem_byte(resize(addr, 64) + I, seed));
            end loop;

        end procedure;

    end protected body;

end package body;
