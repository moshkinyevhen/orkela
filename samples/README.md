# Native Resonith sample

`emotional-piano-resonith.lps5` is an eight-second stereo research clip encoded
by the prospective Resonith LPS5 transport. Orkela opens this file directly,
decodes it through Resonith Core, and sends the resulting PCM16 to the Windows
audio device. No WAV conversion or external decoder is used.

`emotional-piano-original.wav` is the exact PCM16 input used for that
bitstream and for the rate-matched Opus comparison.

## Bitstream

- bytes: `117643`
- SHA-256: `fbd985cce4091d92c911e93a617faddf0b94370d6677640aa0dc94a12623a05a`
- sample rate: `44100 Hz`
- channels: `2`
- duration: `8.0 s`
- LPS5 packet frames: `12288`
- transform half-window: `512`
- bands: `24`
- average coefficient budget: `68`
- decoded PCM16 SHA-256:
  `3cfcae4996a08976f42ec83744ea0130935ca53d83b37129c001581697618618`

## Rate-matched Opus anchor

The public comparison uses the official libopus `1.6.1` library through
`opusenc` from opus-tools `0.2`. The workflow tests candidate true-VBR rates
and selects the complete Ogg Opus file closest to the Resonith file size.

- complete Opus bytes: `117091`
- complete byte delta from Resonith: `-552` (`-0.47%`)
- requested bitrate: `93.9 kb/s`
- mode: music true VBR
- encoder complexity: `10`
- frame duration: `20 ms`
- expected packet loss: `0%`
- SHA-256:
  `1a6889a2f671cd4901e8081c171c22b28ca34f67c13bf6beab48157174fd2d10`
- reproducible workflow:
  [opus-comparison.yml](../.github/workflows/opus-comparison.yml)
- successful run:
  <https://github.com/moshkinyevhen/orkela/actions/runs/30219306914>

## Source and license

- title: *Emotional piano*
- creator/credit: triangelx / Freesound sound 189175
- source:
  <https://commons.wikimedia.org/wiki/File:Emotional_piano.wav>
- license: CC0 1.0
- source file SHA-256:
  `9661f81d37c59f230b324b830ab68c0482336af3ec117c92e73108ffb4095f15`
- selected source PCM16 SHA-256:
  `3481c6d893ff9b41a15862e042de56a2f13ac54ee2d230eff8a44123c640405e`
- selected WAV bytes: `1411244`
- selected WAV SHA-256:
  `37d28f15c8b3ecb13c2c161049c39d5de18f0c1b7e5f4a832684dd8059afdab5`
