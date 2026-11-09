// Run against the installed tarball, using the same prerelease semantics as DSH.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {join} from 'node:path';

const packageRoot = process.env.LUCENT_TEST_PACKAGE;
const require = createRequire(join(packageRoot, 'package.json'));
const semver = require('semver');
const metadata = JSON.parse(await readFile(join(packageRoot, 'package.json'), 'utf8'));
const engineRange = metadata.engines.dsh;
const peerRange = metadata.peerDependencies['@deepseek-ai/dsh-home-paths'];
for (const version of ['0.2.1-rc.5', '0.2.1', '0.2.2-rc.1', '0.2.2-rc.2', '0.2.2']) {
  assert.ok(semver.satisfies(version, engineRange, {includePrerelease: true}), `DSH ${version} rejected`);
  // npm peer resolution excludes prereleases unless their version tuple is explicit.
  assert.ok(semver.satisfies(version, peerRange), `DSH home-paths ${version} rejected by npm`);
}
for (const version of ['0.2.0', '0.2.1-rc.4', '0.2.2-rc.0', '0.2.3-rc.1', '0.2.3', '0.3.0', '1.0.0']) {
  assert.ok(!semver.satisfies(version, engineRange, {includePrerelease: true}), `Untested DSH line ${version} accepted`);
}
for (const name of ['@deepseek-ai/cordis', '@deepseek-ai/dsh-home-paths']) {
  const installed = require(`${name}/package.json`);
  assert.ok(semver.satisfies(installed.version, metadata.peerDependencies[name]), `${name}@${installed.version} violates peer requirements`);
}
console.log('Installed manifest accepts supported DSH/peer versions and rejects versions outside the supported lines.');
