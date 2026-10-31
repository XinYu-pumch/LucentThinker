import {spawn} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import {mkdir, readFile, writeFile, unlink} from 'node:fs/promises';
import {createWriteStream} from 'node:fs';
import {join} from 'node:path';
import {createInterface} from 'node:readline';

// No module-level process or timer: every instance belongs to one Cordis activation.
export class Engine {
  constructor({packageRoot, dataDir, python, parentOrigin = 'dsh-app://app', startupMs = 30000, shutdownMs = 6000}) {
    Object.assign(this, {packageRoot, dataDir, python, parentOrigin, startupMs, shutdownMs});
    this.closed = false; this.phase = 'idle'; this.child = null; this.port = null;
    this.error = null; this.starting = null; this.stopping = null;
  }
  status() {
    return {state: this.phase, error: this.error, dataDir: this.dataDir,
      pid: this.child?.pid ?? null, version: '0.1.0-local.1'};
  }
  async session() {
    await this.start();
    if (this.closed || this.phase !== 'ready') throw new Error('LucentThinker 已停用');
    return {...this.status(), url: `http://127.0.0.1:${this.port}/dsh/${this.token}/`};
  }
  start() {
    if (this.closed) return Promise.reject(new Error('LucentThinker 已停用'));
    if (this.phase === 'ready') return Promise.resolve();
    if (this.starting) return this.starting;
    this.starting = this.launch().catch(async error => {
      await this.stopChild();
      if (!this.closed) { this.phase = 'error'; this.error = error.message; }
      throw error;
    }).finally(() => { this.starting = null; });
    return this.starting;
  }
  async launch() {
    this.phase = 'starting'; this.error = null;
    await mkdir(this.dataDir, {recursive: true, mode: 0o700});
    const runtime = this.python ? null : JSON.parse(await readFile(join(this.packageRoot, 'runtime/manifest.json'), 'utf8'));
    const python = this.python ?? join(this.packageRoot, 'runtime', runtime.executable);
    if (this.closed) throw new Error('LucentThinker 已停用');
    this.token = randomBytes(32).toString('hex');
    // Do not inherit model API keys, PYTHONPATH or another project's .env; respect existing proxy settings.
    const env = Object.fromEntries(['PATH','HOME','USERPROFILE','TMPDIR','TEMP','SYSTEMROOT','LANG','LC_ALL',
      'HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy']
      .filter(k => process.env[k] !== undefined).map(k => [k, process.env[k]]));
    Object.assign(env, {LUCENT_DATA_DIR: this.dataDir, PYTHONUNBUFFERED: '1',
      PYTHONDONTWRITEBYTECODE: '1', PYTHONNOUSERSITE: '1',
      TIKTOKEN_CACHE_DIR: join(this.dataDir, 'cache/tiktoken')});
    const child = spawn(python, ['-s', '-m', 'app.dsh'], {
      cwd: join(this.packageRoot, 'engine'), env,
      stdio: ['pipe','pipe','pipe'], detached: process.platform !== 'win32', windowsHide: true,
    });
    this.child = child;
    const log = createWriteStream(join(this.dataDir, 'engine.log'), {flags: 'a', mode: 0o600});
    log.on('error', () => {});
    // Tokens travel through stdin; no URL is emitted to a log.
    child.stderr.pipe(log, {end: false});
    child.stdin.on('error', () => {});
    this.exited = new Promise(resolve => {
      child.once('close', (code, signal) => {
        log.end();
        if (!this.closed && this.phase === 'ready') {
          this.phase = 'error'; this.error = `研究引擎已退出（${signal ?? code}），请点击重试。`;
        }
        resolve();
      });
    });
    await new Promise((resolve, reject) => {
      const lines = createInterface({input: child.stdout});
      let settled = false;
      const timer = setTimeout(() => done(new Error('研究引擎启动超时，请查看插件日志后重试。')), this.startupMs);
      const onError = () => done(new Error('无法启动内置 Python，请检查插件平台版本或重新安装。'));
      const onExit = () => done(new Error('研究引擎未能启动，请查看插件日志；数据将保留。'));
      const done = error => {
        if (settled) return; settled = true; clearTimeout(timer); lines.close();
        child.off('error', onError); child.off('exit', onExit);
        error ? reject(error) : resolve();
      };
      child.once('error', onError); child.once('exit', onExit);
      lines.on('line', line => {
        try {
          const value = JSON.parse(line);
          if (value.ready && Number.isInteger(value.port) && value.port > 0 && value.port < 65536) {
            this.port = value.port; done();
          }
        } catch {}
      });
      child.stdin.write(JSON.stringify({token: this.token, parentOrigin: this.parentOrigin}) + '\n');
    });
    if (this.closed) throw new Error('LucentThinker 已停用');
    this.phase = 'ready';
    await writeFile(join(this.dataDir, 'engine-state.json'), JSON.stringify({hostPid: process.pid,
      enginePid: child.pid, port: this.port, started: new Date().toISOString()}), {mode: 0o600});
    if (this.closed) throw new Error('LucentThinker 已停用');
  }
  async stopChild() {
    const child = this.child;
    if (!child) return;
    child.stdin.end(); // EOF is the normal shutdown protocol, also handles host death.
    const kill = () => {
      if (child.exitCode !== null || child.signalCode !== null) return;
      try {
        if (process.platform === 'win32') child.kill('SIGKILL');
        else process.kill(-child.pid, 'SIGKILL');
      } catch (error) { this.error = error.code === 'ESRCH' ? this.error : '引擎进程未能退出，请查看日志。'; }
    };
    const timer = setTimeout(kill, this.shutdownMs);
    try { await this.exited; } finally {
      clearTimeout(timer); this.child = null; this.port = null; this.token = null;
      try {
        const file=join(this.dataDir,'engine-state.json');
        if(JSON.parse(await readFile(file,'utf8')).enginePid===child.pid)await unlink(file);
      } catch(error) { if(error.code!=='ENOENT')throw error; }
    }
  }
  dispose() {
    if (this.stopping) return this.stopping;
    this.closed = true; this.phase = 'stopping';
    this.stopping = (async () => {
      // If unload races with startup, signal the child immediately, then await both paths.
      this.child?.stdin.end();
      await this.starting?.catch(() => {});
      await this.stopChild();
      this.phase = 'stopped';
    })();
    return this.stopping;
  }
}
