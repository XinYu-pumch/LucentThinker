// Maintainer-only preparation. User installation uses the bundled runtime offline.
import {execFileSync} from 'node:child_process';
import {mkdir} from 'node:fs/promises';
import {join, resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = fileURLToPath(new URL('../..', import.meta.url));
const target = `${process.platform}-${process.arch}`;
if (!['darwin-arm64', 'win32-x64'].includes(target)) {
  throw new Error(`Unsupported build target ${target}`);
}
const env = {...process.env, UV_PYTHON_INSTALL_DIR: join(root, '.cache/dsh-python')};
const run = args => execFileSync('uv', args, {cwd: root, env, encoding: 'utf8'}).trim();
await mkdir(join(root, '.cache'), {recursive: true});
run(['python', 'install', '3.12.9']);
const python = run(['python', 'find', '--managed-python', '3.12.9']);
const requirements = join(root, '.cache/dsh-runtime-requirements.txt');
run(['export', '--frozen', '--no-dev', '--no-emit-project', '--format', 'requirements-txt', '--output-file', requirements]);
run(['pip', 'sync', '--python', python, '--require-hashes', requirements]);
const source = process.platform === 'win32' ? dirname(python) : resolve(dirname(python), '..');
execFileSync(process.execPath, [join(root, 'dsh-plugin/scripts/build.mjs')], {
  cwd: root, stdio: 'inherit', env: {...env, LUCENT_RUNTIME_SOURCE: source},
});
