# ssc-fixer

A cartridge-port interposer that keeps the Tandy **Speech/Sound Cartridge**'s PIC 7040
MCU and AY-3-8913 PSG at 1.79 MHz when a CoCo runs at double speed. Without it, both
run at 3.58 MHz, which makes the firmware run twice as fast and the music play an
octave higher. The cartridge itself is not modified.

There are two designs:

* **Rev A, [DESIGN.md](DESIGN.md):** substitutes Q, with 3 chips plus an oscillator. It handles CoCo E of
  0.89 and 1.79 MHz, including mixed-speed operation. Simulation: [sim/ssc_fixer_sim.py](sim/ssc_fixer_sim.py)
* **Rev B, [DESIGN-4MHz.md](DESIGN-4MHz.md):** a bus bridge built from 17 74HCT chips plus an oscillator.
  It handles any CoCo E up to 4 MHz by giving the SSC its own stock-speed private bus, which also runs
  the −5 V converter at its stock frequency. Simulation: [sim/bridge_sim.py](sim/bridge_sim.py)

The schematic references are to pages 17–18 of the Speech/Sound Cartridge service
manual, which is not included here for copyright reasons. Copies are available from
CoCo archive sites.

Status: design only. No hardware has been built or tested yet.

## License

MIT. See [LICENSE](LICENSE).
