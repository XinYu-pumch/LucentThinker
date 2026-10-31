// Maintainer-only preparation. User installation uses the bundled runtime offline.
import {execFileSync} from 'node:child_process';
import {mkdir} from 'node:fs/promises';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = fileURLToPath(new URL('../..', import.meta.url));
const target = `${process.platform}-${process.arch}`;
if (!['darwin-arm64', 'win32-x64'].includes(target)) {
  throw new Error(`Unsupported build target ${target}`);
}
const env = {...process.env, UV_PYTHON_INSTALL_DIR: join(root, '.cache/dsh-python')};
const run = args => execFileSync('uv', args, {cwd: root, env, encoding: 'utf8'}).trim();
await mkdir(join(root, '.cache'), {recursive: true});
const distribution = process.platform === 'win32'
  ? 'cpython-3.12.9-windows-x86_64-none' : 'cpython-3.12.9-macos-aarch64-none';
run(['python', 'install', distribution]);
const source = join(env.UV_PYTHON_INSTALL_DIR, distribution);
const python = join(source, process.platform === 'win32' ? 'python.exe' : 'bin/python3.12');
const requirements = join(root, '.cache/dsh-runtime-requirements.txt');
run(['export', '--frozen', '--no-dev', '--no-emit-project', '--format', 'requirements-txt', '--output-file', requirements]);
run(['pip', 'sync', '--python', python, '--require-hashes', requirements]);
execFileSync(process.execPath, [join(root, 'dsh-plugin/scripts/build.mjs')], {
  cwd: root, stdio: 'inherit', env: {...env, LUCENT_RUNTIME_SOURCE: source},
});
