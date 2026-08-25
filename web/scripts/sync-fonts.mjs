// Copies only the woff2 subsets Serbian Latin actually needs out of the
// Fontsource packages. Keeping the set explicit stops the PWA precache from
// shipping Cyrillic, Greek and Vietnamese faces nobody in this app renders.
import { copyFile, mkdir } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const out = join(root, 'src/assets/fonts')

const FILES = [
  '@fontsource-variable/geist/files/geist-latin-wght-normal.woff2',
  '@fontsource-variable/geist/files/geist-latin-ext-wght-normal.woff2',
  '@fontsource-variable/geist-mono/files/geist-mono-latin-wght-normal.woff2',
  '@fontsource-variable/geist-mono/files/geist-mono-latin-ext-wght-normal.woff2',
]

await mkdir(out, { recursive: true })
for (const rel of FILES) {
  const name = rel.split('/').pop()
  await copyFile(join(root, 'node_modules', rel), join(out, name))
  console.log('copied', name)
}
