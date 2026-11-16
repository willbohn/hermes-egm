// Update a bot-owned report comment; never edit maintainer notes or adopt upstream code.
'use strict';

const MARKER = '<!-- upstream-monitor:report -->';
const GOOGLE_BASELINE = '6a8001ea31ccf72430ba0603a467ec6df9f69dd7'; // Before v0.2.0.
const ISSUE = 7;


function sha(value) {
  if (!/^[0-9a-f]{40}$/.test(value)) throw new Error('Invalid upstream commit SHA');
  return value;
}

async function report({ github, context, core, env = process.env }) {
  const result = env.COMPATIBILITY_RESULT;
  if (!['success', 'failure', 'cancelled', 'skipped'].includes(result)) {
    throw new Error('Missing or invalid compatibility result');
  }
  const params = { ...context.repo, issue_number: ISSUE };
  const { data: issue } = await github.rest.issues.get(params);
  if (issue.title !== 'Upstream maintenance tracking' || issue.pull_request) {
    throw new Error('Tracking issue identity changed');
  }

  const run = `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
  const lines = [
    MARKER,
    'Automated report. Please put triage notes in the issue body or a separate comment.',
    '',
    `## Latest check: [workflow run](${run})`,
    '',
    `Hermes main validation/registration: **${result}**. This is not a live-model test.`,
  ];
  let lookupFailed = false;
  try {
    const host = sha(env.HERMES_SHA);
    const { data: release } = await github.rest.repos.getLatestRelease({ owner: 'NousResearch', repo: 'hermes-agent' });
    const { data: google } = await github.rest.repos.getCommit({ owner: 'google', repo: 'elephant-goldfish-model', ref: 'main' });
    const googleHead = sha(google.sha);
    const tag = encodeURIComponent(release.tag_name);
    lines.push(
      `Tested Hermes commit: [\`${host}\`](https://github.com/NousResearch/hermes-agent/commit/${host}).`,
      `Latest stable release: [release notes](https://github.com/NousResearch/hermes-agent/releases/tag/${tag}).`,
      '',
      '### Hermes follow-up',
      '',
      'On failure, inspect the run before changing the pinned host. Review plugin APIs, registration, storage and LLM request behavior first.',
      `[Changes since latest stable](https://github.com/NousResearch/hermes-agent/compare/${tag}...${host}). The required PR check remains pinned separately.`,
      '',
      '### Google EGM follow-up',
      '',
      `Current commit: [\`${googleHead}\`](https://github.com/google/elephant-goldfish-model/commit/${googleHead}).`,
      `[Changes since the monitoring baseline](https://github.com/google/elephant-goldfish-model/compare/${GOOGLE_BASELINE}...${googleHead}).`,
      'Review methodology, reviewer contracts, validation and security changes for applicability. No changes are imported automatically.',
      'Advance GOOGLE_BASELINE in .github/upstream-monitor.cjs through a reviewed PR after triage; until then the full outstanding range stays linked.',
    );
  } catch {
    lookupFailed = true;
    lines.push('', '**Upstream lookup incomplete.** See the workflow; do not interpret missing data as no changes.');
  }
  const body = lines.join('\n');
  const comments = await github.paginate(github.rest.issues.listComments, params);
  const owned = comments.filter((comment) => comment.user?.login === 'github-actions[bot]'
    && comment.user?.type === 'Bot' && comment.body?.startsWith(MARKER));
  if (owned.length > 1) throw new Error('Multiple automated reports; refusing ambiguous update');
  let comment = owned[0];
  if (!comment) {
    ({ data: comment } = await github.rest.issues.createComment({ ...params, body }));
  } else if (comment.body !== body) {
    await github.rest.issues.updateComment({ ...context.repo, comment_id: comment.id, body });
  }
  const { data: saved } = await github.rest.issues.getComment({ ...context.repo, comment_id: comment.id });
  if (saved.body !== body) throw new Error('Report comment read-back did not match');
  if (lookupFailed) core.setFailed('Upstream lookup incomplete');
}

module.exports = { report };
