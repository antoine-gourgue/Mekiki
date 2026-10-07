// Sets the app version everywhere it is written, before tagging a release:
//   npm run version:set -- 0.2.0
// Tauri compares this version with the latest release to offer updates.
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const version = process.argv[2]
if (!/^\d+\.\d+\.\d+$/.test(version ?? '')) {
  console.error('Usage: npm run version:set -- <major.minor.patch>')
  process.exit(1)
}

const root = fileURLToPath(new URL('../../', import.meta.url))
const edits = [
  ['desktop/package.json', /("version":\s*")[^"]+(")/],
  ['desktop/src-tauri/tauri.conf.json', /("version":\s*")[^"]+(")/],
  ['desktop/src-tauri/Cargo.toml', /^(version\s*=\s*")[^"]+(")/m],
  ['engine/mekiki_engine/__init__.py', /(__version__\s*=\s*")[^"]+(")/],
]

for (const [file, pattern] of edits) {
  const path = root + file
  const text = readFileSync(path, 'utf8')
  if (!pattern.test(text)) {
    console.error(`No version found in ${file}`)
    process.exit(1)
  }
  writeFileSync(path, text.replace(pattern, `$1${version}$2`))
  console.log(`${file} → ${version}`)
}
console.log(`\nThen: git commit -am "chore: release v${version}" && git tag v${version}`)
