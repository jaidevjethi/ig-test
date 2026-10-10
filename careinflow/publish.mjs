/**
 * CareInflow scheduled publisher. Runs inside GitHub Actions in the public
 * staging repo (jaidevjethi/ig-test), every 30 minutes and on demand.
 *
 * careinflow/queue/<ID>/post.json  { id, kind, publishAt (UTC ISO), caption, alt, images[] }
 * careinflow/queue/<ID>/01.jpg …   the slides; served to Instagram from raw.githubusercontent.com
 * careinflow/published/<ID>.json   written after a successful publish; the queue folder is then removed
 *
 * Env: INSTAGRAM_TOKEN (Actions secret), DRY_RUN ("true" = check token and list only),
 *      FORCE_ID (publish this one post now, whatever its date).
 * The token is only ever sent in request bodies, never in a URL or a log line.
 */
import { readFileSync, readdirSync, existsSync, writeFileSync, rmSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(fileURLToPath(import.meta.url));
const GRAPH = 'https://graph.facebook.com/v20.0';
const TOKEN = process.env.INSTAGRAM_TOKEN;
const DRY = String(process.env.DRY_RUN ?? 'false') === 'true';
const FORCE = (process.env.FORCE_ID ?? '').trim();
const REPO = process.env.GITHUB_REPOSITORY ?? 'jaidevjethi/ig-test';
const BRANCH = process.env.GITHUB_REF_NAME ?? 'main';
const config = JSON.parse(readFileSync(join(ROOT, 'config.json'), 'utf8'));
const IG = config.igUserId;
const MAX_PER_RUN = 2;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

async function graph(method, path, params = {}) {
  const body = new URLSearchParams({ ...params, access_token: TOKEN });
  const res = method === 'GET'
    ? await fetch(`${GRAPH}/${path}?${new URLSearchParams(params)}`, { headers: { Authorization: `Bearer ${TOKEN}` } })
    : await fetch(`${GRAPH}/${path}`, { method, body });
  const json = await res.json().catch(() => ({}));
  if (json.error) {
    const e = new Error(`Graph ${json.error.code}/${json.error.error_subcode ?? '-'}: ${json.error.message}`);
    e.code = json.error.code;
    throw e;
  }
  return json;
}

/** Wait until a media container has finished processing. */
async function ready(containerId) {
  for (let i = 0; i < 36; i++) {
    const { status_code } = await graph('GET', containerId, { fields: 'status_code' });
    if (status_code === 'FINISHED') return;
    if (status_code === 'ERROR' || status_code === 'EXPIRED') throw new Error(`container ${containerId} ${status_code}`);
    await sleep(5000);
  }
  throw new Error(`container ${containerId} not ready after 3 minutes`);
}

/** Create a container; if Instagram rejects alt_text, try once more without it. */
async function container(params) {
  try {
    return (await graph('POST', `${IG}/media`, params)).id;
  } catch (e) {
    if (params.alt_text && e.code === 100) {
      log('  alt_text not accepted here; retrying without it (add alt text in the app)');
      const { alt_text, ...rest } = params;
      return (await graph('POST', `${IG}/media`, rest)).id;
    }
    throw e;
  }
}

const raw = (id, file) => `https://raw.githubusercontent.com/${REPO}/${BRANCH}/careinflow/queue/${id}/${file}`;

/** Raw GitHub URLs can lag a push by a few seconds; wait until each one serves the image. */
async function servable(url) {
  for (let i = 0; i < 24; i++) {
    const r = await fetch(url, { method: 'HEAD' }).catch(() => null);
    if (r && r.ok && (r.headers.get('content-type') ?? '').startsWith('image/')) return;
    await sleep(5000);
  }
  throw new Error(`image not reachable after 2 minutes: ${url}`);
}

async function publish(post) {
  for (const f of post.images) await servable(raw(post.id, f));
  let creationId;
  if (post.kind === 'carousel') {
    const children = [];
    for (const f of post.images) {
      const c = await container({ image_url: raw(post.id, f), is_carousel_item: 'true', alt_text: post.alt });
      await ready(c);
      children.push(c);
      log(`  slide ${children.length}/${post.images.length} ready`);
    }
    creationId = await container({ media_type: 'CAROUSEL', children: children.join(','), caption: post.caption });
  } else {
    creationId = await container({ image_url: raw(post.id, post.images[0]), caption: post.caption, alt_text: post.alt });
  }
  await ready(creationId);
  const { id: mediaId } = await graph('POST', `${IG}/media_publish`, { creation_id: creationId });
  const { permalink } = await graph('GET', mediaId, { fields: 'permalink' });
  return { mediaId, permalink };
}

async function main() {
  if (!TOKEN) throw new Error('INSTAGRAM_TOKEN is not set');
  const me = await graph('GET', IG, { fields: 'username' });
  if (me.username !== config.expectUsername) throw new Error(`token is for @${me.username}, expected @${config.expectUsername}; refusing to post`);
  log(`token ok for @${me.username}`);

  const queueDir = join(ROOT, 'queue');
  const doneDir = join(ROOT, 'published');
  mkdirSync(doneDir, { recursive: true });
  const queued = existsSync(queueDir) ? readdirSync(queueDir).filter((d) => existsSync(join(queueDir, d, 'post.json'))) : [];
  const posts = queued.map((d) => JSON.parse(readFileSync(join(queueDir, d, 'post.json'), 'utf8'))).sort((a, b) => a.publishAt.localeCompare(b.publishAt));
  const now = Date.now();
  const due = posts.filter((p) => (FORCE ? p.id === FORCE : Date.parse(p.publishAt) <= now) && !existsSync(join(doneDir, `${p.id}.json`)));
  log(`${posts.length} queued, ${due.length} due${FORCE ? ` (forced: ${FORCE})` : ''}`);
  for (const p of posts) log(`  ${p.id}  ${p.publishAt}  ${p.kind}  ${p.images.length} image(s)`);
  if (FORCE && !due.length) throw new Error(`${FORCE} is not in the queue (or already published)`);
  if (DRY) return log('dry run: nothing published');

  let failures = 0;
  for (const post of due.slice(0, MAX_PER_RUN)) {
    log(`publishing ${post.id}`);
    try {
      const r = await publish(post);
      writeFileSync(join(doneDir, `${post.id}.json`), JSON.stringify({ id: post.id, ...r, publishedAt: new Date().toISOString(), scheduledFor: post.publishAt }, null, 2) + '\n');
      rmSync(join(queueDir, post.id), { recursive: true, force: true });
      log(`  ✓ ${r.permalink}`);
    } catch (e) {
      failures++;
      log(`  ✗ ${post.id}: ${String(e.message).replaceAll(TOKEN, '<token>')}`);
    }
  }
  if (failures) process.exitCode = 1;
}

main().catch((e) => {
  console.error(String(e.message).replaceAll(TOKEN ?? '\u0000', '<token>'));
  process.exit(1);
});
