// Contract tests for issue updates without GitHub writes.
'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const { report } = require('./upstream-monitor.cjs');
const marker = '<!-- upstream-monitor:report -->';

function fixture() {
  const comments = [];
  const updates = [];
  const failures = [];
  const issues = {
    get: async () => ({ data: { body: 'Maintainer notes', title: 'Upstream maintenance tracking' } }),
    update: async () => { throw new Error('Must not edit issue body'); },
    listComments: async () => ({ data: comments }),
    createComment: async (args) => {
      updates.push(args);
      const comment = { id: 1234, body: args.body, user: { login: 'github-actions[bot]', type: 'Bot' } };
      comments.push(comment);
      return { data: comment };
    },
    updateComment: async (args) => {
      updates.push(args);
      const comment = comments.find((item) => item.id === args.comment_id);
      assert.equal(comment.user.type, 'Bot');
      comment.body = args.body;
    },
    getComment: async (args) => ({ data: comments.find((item) => item.id === args.comment_id) }),
  };
  return {
    updates, failures, issues, comments,
    args: {
      github: { paginate: async (method, args) => (await method(args)).data, rest: { issues, repos: {
        getLatestRelease: async () => ({ data: { tag_name: 'v0.23.1' } }),
        getCommit: async () => ({ data: { sha: 'b'.repeat(40) } }),
      } } },
      context: { repo: { owner: 'example', repo: 'plugin' }, serverUrl: 'https://github.com', runId: 123 },
      core: { setFailed: (message) => failures.push(message) },
      env: { COMPATIBILITY_RESULT: 'success', HERMES_SHA: 'a'.repeat(40) },
    },
  };
}

test('creates one report, reuses it, and is idempotent for the same run', async () => {
  const f = fixture();
  await report(f.args);
  await report(f.args);
  assert.equal(f.updates.length, 1);
  assert.equal(f.updates[0].issue_number, 7);

  assert.match(f.updates[0].body, /\*\*success\*\*/);
  assert.match(f.updates[0].body, /compare\/6a8001ea31ccf72430ba0603a467ec6df9f69dd7\.\.\.b{40}/);
  assert.deepEqual(f.failures, []);
  f.args.context.runId = 124;
  await report(f.args);
  assert.equal(f.updates.length, 2);
  assert.equal(f.updates[1].comment_id, 1234);
  assert.equal(f.comments.length, 1);
});

test('failed compatibility and lookup remain explicit, never a clean bill of health', async () => {
  const f = fixture();
  f.args.env.COMPATIBILITY_RESULT = 'failure';
  f.args.github.rest.repos.getCommit = async () => { throw new Error('API unavailable'); };
  await report(f.args);
  assert.match(f.updates[0].body, /\*\*failure\*\*/);
  assert.match(f.updates[0].body, /Upstream lookup incomplete/);
  assert.equal(f.failures.length, 1);
});

test('human comments with the same marker are never edited', async () => {
  const f = fixture();
  const human = { id: 99, body: marker + '\nnotes', user: { login: 'maintainer', type: 'User' } };
  f.comments.push(human);
  await report(f.args);
  assert.equal(human.body, marker + '\nnotes');
  assert.equal(f.comments.length, 2);
});

test('ambiguous bot-owned comments fail without mutation', async () => {
  const f = fixture();
  await report(f.args);
  f.comments.push({ ...f.comments[0], id: 2345 });
  f.updates.length = 0;
  await assert.rejects(report(f.args), /Multiple automated reports/);
  assert.equal(f.updates.length, 0);
});

test('a successful update response is not accepted without matching read-back', async () => {
  const f = fixture();
  f.issues.getComment = async () => ({ data: { body: 'unexpected' } });
  await assert.rejects(report(f.args), /read-back did not match/);
});

test('invalid routing data and changed issue identity cannot be silently accepted', async () => {
  const f = fixture();
  f.args.env.COMPATIBILITY_RESULT = 'unknown';
  await assert.rejects(report(f.args), /invalid compatibility result/);
  f.args.env.COMPATIBILITY_RESULT = 'success';
  f.issues.get = async () => ({ data: { title: 'Different issue', body: 'notes' } });
  await assert.rejects(report(f.args), /identity changed/);
  assert.equal(f.updates.length, 0);
});
