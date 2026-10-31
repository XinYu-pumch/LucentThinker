// Combine native artifacts from the same CI commit into one offline installable package.
import {execFileSync} from 'node:child_process';
import {cp, mkdir, mkdtemp, readFile, readdir, rm, writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = fileURLToPath(new URL('../..', import.meta.url));
const staging = await mkdtemp(join(root, '.cache/assemble-'));
try {
  const manifests = {};
  let version;
  for (const [platform, artifact] of [['darwin-arm64', 'macos'], ['win32-x64', 'windows']]) {
    const directory = join(root, '.cache/artifacts', artifact);
    const files = (await readdir(directory)).filter(file => file.endsWith('.tgz'));
    if (files.length !== 1) throw new Error(`Expected one native package in ${directory}`);
    const extraction = join(staging, platform);
    await mkdir(extraction);
    execFileSync('tar', ['-xzf', join(directory, files[0]), '-C', extraction]);
    const source = join(extraction, 'package');
    const metadata = JSON.parse(await readFile(join(source, 'package.json'), 'utf8'));
    if (version && version !== metadata.version) throw new Error('Native package versions differ');
    version = metadata.version;
    const manifest = JSON.parse(await readFile(join(source, 'runtime/manifest.json'), 'utf8'));
    if (!manifest.targets[platform]) throw new Error(`Missing runtime ${platform}`);
    manifests[platform] = manifest.targets[platform];
    if (platform === 'darwin-arm64') await cp(source, join(staging, 'package'), {recursive:true});
    else await cp(join(source, 'runtime', platform), join(staging, 'package/runtime', platform), {recursive:true});
  }
  await writeFile(join(staging, 'package/runtime/manifest.json'), JSON.stringify({targets:manifests}, null, 2)+'\n');
  const releases = join(root, 'releases');
  await mkdir(releases, {recursive:true});
  if (!process.env.npm_execpath) throw new Error('Use npm run assemble');
  execFileSync(process.execPath, [process.env.npm_execpath, 'pack', '--ignore-scripts', '--pack-destination', releases], {cwd:join(staging, 'package'), stdio:'inherit'});
} finally {
  await rm(staging, {recursive:true, force:true});
}
