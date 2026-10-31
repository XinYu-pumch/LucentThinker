// Exercise the actual tarball, with a Unicode/space path and no global install.
import {execFileSync} from 'node:child_process';
import {mkdir, mkdtemp, readFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = fileURLToPath(new URL('../..', import.meta.url));
const pkg = join(root, 'dsh-plugin');
const releases = join(root, 'releases');
await mkdir(releases, {recursive: true});
// npm's JS entry point avoids shell quoting problems on Windows.
const npm = process.env.npm_execpath;
if (!npm) throw new Error('Run this script through npm run test:install');
let tarball = process.env.LUCENT_TEST_TARBALL;
if (process.argv.includes('--release')) {
  const {name, version} = JSON.parse(await readFile(join(pkg, 'package.json'), 'utf8'));
  tarball = join(releases, `${name}-${version}.tgz`);
}
if (tarball) {
  tarball = resolve(root, tarball);
} else {
  const output = execFileSync(process.execPath, [npm, 'pack', '--ignore-scripts', '--json', '--pack-destination', releases], {cwd: pkg, encoding: 'utf8'});
  const [{filename}] = JSON.parse(output);
  tarball = join(releases, filename);
}
const destination = await mkdtemp(join(tmpdir(), 'Lucent 安装 test-'));
try {
  execFileSync(process.execPath, [npm, 'install', '--ignore-scripts', '--omit=optional', '--no-audit', '--no-fund', '--prefix', destination, tarball, '@deepseek-ai/cordis@4.0.5', '@deepseek-ai/dsh-home-paths@0.2.1-rc.5'], {stdio: 'inherit'});
  const installed = join(destination, 'node_modules/dsh-plugin-lucentthinker');
  const manifest = JSON.parse(await readFile(join(installed, 'runtime/manifest.json'), 'utf8'));
  if (!manifest.targets[`${process.platform}-${process.arch}`]) throw new Error('Native runtime missing');
  execFileSync(process.execPath, ['--test', 'test/client.test.mjs', 'test/lifecycle.test.mjs'], {
    cwd: pkg, stdio: 'inherit', env: {...process.env, LUCENT_TEST_PACKAGE: installed},
  });
  execFileSync(process.execPath, [join(pkg, 'scripts/verify-host.mjs')], {
    stdio:'inherit', env:{...process.env, LUCENT_TEST_PACKAGE:installed},
  });
} finally {
  await rm(destination, {recursive: true, force: true});
}
