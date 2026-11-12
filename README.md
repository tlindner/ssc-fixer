# ssc-fixer

A cartridge-port interposer that keeps the Tandy **Speech/Sound Cartridge**'s PIC 7040
MCU and AY-3-8913 PSG at 1.79 MHz when a CoCo runs at double speed. Without it, both
run at 3.58 MHz, which makes the firmware run twice as fast and the music play an
octave higher. The cartridge itself is not modified.

* [DESIGN.md](DESIGN.md): analysis, circuit, netlist, BOM, timing and caveats
* [sim/ssc_fixer_sim.py](sim/ssc_fixer_sim.py): 1 ns timing simulation (`python3 sim/ssc_fixer_sim.py`)

The schematic references are to pages 17–18 of the Speech/Sound Cartridge service
manual, which is not included here for copyright reasons. Copies are available from
CoCo archive sites.

Status: design only. No hardware has been built or tested yet.

## License

MIT. See [LICENSE](LICENSE).
