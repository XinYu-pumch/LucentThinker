import {Service} from '@deepseek-ai/cordis';
import {resolveDshHome} from '@deepseek-ai/dsh-home-paths';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {Engine} from './engine.js';
import {PACKAGE, descriptors} from './protocol.js';

export default class LucentThinker extends Service {
  static inject = ['typert'];
  constructor(ctx) {
    super(ctx, 'lucentThinker');
    this.typertRemote = {serviceKey: 'lucentThinker', namespace: 'lucentThinker', service: this};
    this.engine = new Engine({packageRoot: fileURLToPath(new URL('..', import.meta.url)),
      dataDir: join(resolveDshHome(), 'plugin-data', 'lucentthinker')});
    // Register teardown before any asynchronous startup work begins.
    ctx.effect(() => () => this.engine.dispose(), 'LucentThinker: owned engine');
    ctx.typert.register({package: PACKAGE, face: 'host', schemas: [], invocations: descriptors,
      model: {services: [], events: [], objects: []}});
  }
  session() {
    // The Web carrier may activate after this plugin; select its exact origin at first use.
    const server = this.ctx.get('webServer');
    this.engine.parentOrigin = server ? server.getOrigin() : 'dsh-app://app';
    return this.engine.session();
  }
  status() { return this.engine.status(); }
}
