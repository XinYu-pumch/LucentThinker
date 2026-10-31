// Test the installed host entry point against DSH's real Cordis lifecycle.
import assert from 'node:assert/strict';
import {mkdtemp, rm, access, readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';

const packageRoot = process.env.LUCENT_TEST_PACKAGE;
const metadata = JSON.parse(await readFile(join(packageRoot, 'package.json'), 'utf8'));
const require = createRequire(join(packageRoot, 'package.json'));
const {Context} = await import(pathToFileURL(require.resolve('@deepseek-ai/cordis')));
const {default: Plugin} = await import(pathToFileURL(join(packageRoot, 'lib/host.js')));
const home = await mkdtemp(join(tmpdir(), 'Lucent DSH 宿主-'));
process.env.DSH_HOME = home;
const ctx = new Context();
let registrations = 0;
// The RPC schema registry is the only host service stubbed in this lifecycle check.
ctx.provide('typert', {register() {registrations++;}});
let activation;
try {
  for (let attempt = 0; attempt < 2; attempt++) {
    activation = await ctx.plugin(Plugin);
    const service = ctx.get('lucentThinker');
    assert.equal(service.status().state, 'idle');
    assert.equal(service.status().version, metadata.version);
    assert.equal(service.status().pid, null);
    const session = await service.session();
    assert.equal((await fetch(session.url+'api/projects')).status, 200);
    await activation.dispose();
    assert.equal(ctx.get('lucentThinker'), undefined);
    assert.equal(service.status().state, 'stopped');
    await assert.rejects(fetch(session.url+'api/projects'));
    await assert.rejects(access(join(home, 'plugin-data/lucentthinker/engine-state.json')));
  }
  assert.equal(registrations, 2);
  console.log('Installed Cordis host activation, disposal and reactivation passed.');
} finally {
  await activation?.dispose();
  await rm(home, {recursive:true, force:true});
}
