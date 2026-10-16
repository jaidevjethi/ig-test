/**
 * CareInflow scheduled publisher. Runs inside GitHub Actions in the public
 * staging repo (jaidevjethi/ig-test): early each day (then it waits for the post's
 * minute), hourly as a backstop, and on demand.
 *
 * careinflow/queue/<ID>/post.json  { id, kind, publishAt (UTC ISO), caption, alt, images[] }
 * careinflow/queue/<ID>/01.jpg …   the slides; served to Instagram from raw.githubusercontent.com
 * careinflow/published/<ID>.json   written after a successful publish; the queue folder is then removed
 *
 * Env: INSTAGRAM_TOKEN (Actions secret), DRY_RUN ("true" = check token and list only),
 *      FORCE_ID (publish this one post now, whatever its date).
 * The token is only ever sent in request bodies, never in a URL or a log line.
 *
 * Never twice: a run that waited in the concurrency queue may start from an old
 * commit, so the queue is pulled before anything is read, and every post is
 * checked against the account's latest captions before it is made. A post that
 * is already live is recorded as published and not posted again.
 */
import { readFileSync, readdirSync, existsSync, writeFileSync, rmSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { execSync } from 'node:child_process';
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
// Wait mode: if the next post is due within this many minutes, sleep until it is due.
const WAIT_MAX_MIN = Number(process.env.WAIT_MAX_MIN ?? 0);

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

/** Captions compare by their words, not their whitespace: Instagram may normalise line breaks. */
const words = (s) => String(s ?? '').replace(/\s+/g, ' ').trim();
let recent = null;

/** The live post that already carries this caption, if any (the account's latest 12 are checked). */
async function alreadyLive(post) {
  recent ??= (await graph('GET', `${IG}/media`, { fields: 'caption,permalink,timestamp', limit: '12' })).data ?? [];
  const mine = words(post.caption);
  return recent.find((m) => {
    const theirs = words(m.caption);
    return theirs === mine || (mine.length > 160 && theirs.slice(0, 160) === mine.slice(0, 160));
  });
}

async function main() {
  if (!TOKEN) throw new Error('INSTAGRAM_TOKEN is not set');
  const me = await graph('GET', IG, { fields: 'username' });
  if (me.username !== config.expectUsername) throw new Error(`token is for @${me.username}, expected @${config.expectUsername}; refusing to post`);
  log(`token ok for @${me.username}`);

  // A run that queued behind another starts from the commit it was created at; read the branch as it is now.
  try {
    execSync(`git pull --ff-only --quiet origin ${BRANCH}`, { cwd: ROOT, stdio: 'pipe' });
  } catch (e) {
    log(`could not pull ${BRANCH} at start (${String(e.message).split('\n')[0]}); the duplicate check still applies`);
  }

  const queueDir = join(ROOT, 'queue');
  const doneDir = join(ROOT, 'published');
  mkdirSync(doneDir, { recursive: true });
  const load = () => {
    const queued = existsSync(queueDir) ? readdirSync(queueDir).filter((d) => existsSync(join(queueDir, d, 'post.json'))) : [];
    return queued.map((d) => JSON.parse(readFileSync(join(queueDir, d, 'post.json'), 'utf8'))).sort((a, b) => a.publishAt.localeCompare(b.publishAt));
  };
  let posts = load();
  let now = Date.now();
  // GitHub starts scheduled runs late and irregularly; an early run waits for the exact minute.
  const next = posts.find((p) => !existsSync(join(doneDir, `${p.id}.json`)) && Date.parse(p.publishAt) > now);
  const overdue = posts.some((p) => !existsSync(join(doneDir, `${p.id}.json`)) && Date.parse(p.publishAt) <= now);
  if (!FORCE && !DRY && !overdue && next && WAIT_MAX_MIN > 0) {
    const ms = Date.parse(next.publishAt) - now;
    if (ms <= WAIT_MAX_MIN * 60000) {
      log(`waiting ${Math.round(ms / 60000)} min for ${next.id} at ${next.publishAt}`);
      await sleep(ms + 2000);
      now = Date.now();
      // The checkout is hours old by now: a post edited, re-timed or withdrawn meanwhile must win.
      try {
        execSync(`git pull --ff-only --quiet origin ${BRANCH}`, { cwd: ROOT, stdio: 'pipe' });
        posts = load();
        log('queue refreshed after waiting');
      } catch (e) {
        throw new Error(`could not refresh the queue after waiting; publishing nothing (${String(e.message).split('\n')[0]})`);
      }
    }
  }
  const due = posts.filter((p) => (FORCE ? p.id === FORCE : Date.parse(p.publishAt) <= now) && !existsSync(join(doneDir, `${p.id}.json`)));
  log(`${posts.length} queued, ${due.length} due${FORCE ? ` (forced: ${FORCE})` : ''}`);
  for (const p of posts) log(`  ${p.id}  ${p.publishAt}  ${p.kind}  ${p.images.length} image(s)`);
  if (FORCE && !due.length) throw new Error(`${FORCE} is not in the queue (or already published)`);
  if (DRY) {
    for (const p of due) {
      const live = await alreadyLive(p);
      log(`  due: ${p.id}${live ? ` (already on Instagram: ${live.permalink}; would be recorded, not posted)` : ''}`);
    }
    return log('dry run: nothing published');
  }

  let failures = 0;
  for (const post of due.slice(0, MAX_PER_RUN)) {
    // If this check cannot run, publish nothing: the hourly backstop retries, a duplicate cannot be undone.
    const live = await alreadyLive(post);
    if (live) {
      writeFileSync(join(doneDir, `${post.id}.json`), JSON.stringify({ id: post.id, mediaId: live.id, permalink: live.permalink, publishedAt: new Date(String(live.timestamp).replace(/([+-]\d\d)(\d\d)$/, '$1:$2')).toISOString(), scheduledFor: post.publishAt, note: 'found already live; not posted again' }, null, 2) + '\n');
      rmSync(join(queueDir, post.id), { recursive: true, force: true });
      log(`  = ${post.id} is already on Instagram (${live.permalink}); recorded, not posted again`);
      continue;
    }
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
