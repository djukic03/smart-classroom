// Renders the PWA icon set from one vector source. Run with `npm run icons`
// after changing the mark; the PNGs are committed so a plain `npm ci && build`
// never needs sharp.
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import sharp from 'sharp'

const out = join(dirname(fileURLToPath(import.meta.url)), '../public/icons')
await mkdir(out, { recursive: true })

const TABLA = '#101412'
const KREDA = '#EEF1F0'
const MINT = '#4FC49C'

/** `skala` shrinks the mark for maskable icons, whose outer 20% gets cropped. */
function znak(skala = 1, radijus = 112) {
  const pomeraj = (512 - 512 * skala) / 2
  return `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="${radijus}" fill="${TABLA}"/>
  <g transform="translate(${pomeraj} ${pomeraj}) scale(${skala})">
    <rect x="104" y="128" width="304" height="216" rx="34" fill="none"
          stroke="${KREDA}" stroke-width="22"/>
    <path d="M156 286 214 222 262 262 356 178" fill="none" stroke="${MINT}"
          stroke-width="26" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M212 400h88" stroke="${KREDA}" stroke-width="22" stroke-linecap="round"/>
  </g>
</svg>`
}

const poslovi = [
  { ime: 'icon-192.png', svg: znak(1), velicina: 192 },
  { ime: 'icon-512.png', svg: znak(1), velicina: 512 },
  { ime: 'maskable-512.png', svg: znak(0.72, 0), velicina: 512 },
  { ime: 'apple-touch-icon.png', svg: znak(0.86, 0), velicina: 180 },
]

for (const { ime, svg, velicina } of poslovi) {
  const png = await sharp(Buffer.from(svg))
    .resize(velicina, velicina)
    .png({ compressionLevel: 9 })
    .toBuffer()
  await writeFile(join(out, ime), png)
  console.log('napravljeno', ime, png.length + ' B')
}
