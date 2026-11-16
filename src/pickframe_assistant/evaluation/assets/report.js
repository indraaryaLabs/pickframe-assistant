(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('report-data').textContent);
  const byId = new Map(data.cases.map((c) => [c.id, c]));
  const frames = [...document.querySelectorAll('.frame')];
  const panel = document.getElementById('panel-body');
  const KIND = {
    answer: 'answer',
    handoff: 'hand off',
    abstain: 'abstain',
    out_of_scope: 'out of scope',
    refuse: 'refuse',
  };
  const RING = 'M52 9C80 8 95 28 92 52S70 94 44 91 6 72 9 46 28 10 56 11C66 11 72 14 77 18';
  const CROSS = 'M14 17L86 84M85 14L16 86';

  const el = (tag, props = {}, ...children) => {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (key === 'text') node.textContent = value;
      else if (key === 'class') node.className = value;
      else node.setAttribute(key, value);
    }
    node.append(...children);
    return node;
  };

  const mark = (passed) => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 100 100');
    svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', passed ? RING : CROSS);
    svg.append(path);
    return svg;
  };

  const section = (title, ...children) => [el('h3', { text: title }), ...children];

  const answerNodes = (text) =>
    text.split(/(\[\d+\])/).map((part) => {
      const match = /^\[(\d+)\]$/.exec(part);
      return match ? el('sup', { text: match[1] }) : document.createTextNode(part);
    });

  const render = (c) => {
    const nodes = [];
    nodes.push(el('h2', { text: c.id }));
    nodes.push(el('p', { class: 'meta', text: `${c.split} split · ${c.category} · asked in ${c.lang === 'id' ? 'Indonesian' : 'English'}` }));
    nodes.push(el('p', { class: 'question', text: c.question }));
    nodes.push(
      el('p', { class: 'verdict', 'data-passed': String(c.passed) }, mark(c.passed), el('span', { text: c.passed ? 'Passed' : 'Failed' })),
    );
    nodes.push(
      el(
        'dl',
        { class: 'pair' },
        el('div', {}, el('dt', { text: 'Expected' }), el('dd', { text: KIND[c.expected] })),
        el('div', {}, el('dt', { text: 'Got' }), el('dd', { text: KIND[c.got] })),
      ),
    );
    if (c.failures.length) {
      nodes.push(...section('Why it failed', el('ul', { class: 'reasons' }, ...c.failures.map((f) => el('li', { text: f })))));
    }
    if (c.facts.length) {
      nodes.push(
        ...section(
          'Facts the answer needs',
          el('ul', { class: 'facts' }, ...c.facts.map((f) => el('li', { class: f.found ? 'found' : 'missing', text: f.label }))),
        ),
      );
    }
    nodes.push(...section('What it said', el('p', { class: 'answer-text' }, ...answerNodes(c.answer))));
    if (c.citations.length) {
      nodes.push(
        ...section(
          'Cited',
          el(
            'ul',
            { class: 'cites' },
            ...c.citations.map((ci) => el('li', {}, `[${ci.n}] `, el('a', { href: ci.source, rel: 'noopener' }, `${ci.title} - ${ci.heading}`))),
          ),
        ),
      );
    }
    if (c.decision.startsWith('router')) {
      nodes.push(...section('Decision', el('p', { class: 'meter-caption', text: `Decided before searching: ${c.decision}.` })));
    } else {
      const meter = el('div', { class: 'meter', role: 'img', 'aria-label': `Coverage ${c.coverage.toFixed(2)}, answer threshold ${data.threshold.toFixed(2)}` });
      meter.append(el('div', { class: 'fill', style: `width:${Math.min(100, c.coverage * 100)}%` }));
      meter.append(el('div', { class: 'tick', style: `left:${data.threshold * 100}%` }));
      nodes.push(
        ...section(
          'How much of the question the passages cover',
          meter,
          el('p', { class: 'meter-caption', text: `${(c.coverage * 100).toFixed(0)}% covered; the assistant answers from ${(data.threshold * 100).toFixed(0)}%.` }),
        ),
      );
    }
    if (c.retrieved.length) {
      const top = Math.max(...c.retrieved.map((r) => r.score)) || 1;
      nodes.push(
        ...section(
          'Passages it found',
          el(
            'ol',
            { class: 'passages' },
            ...c.retrieved.map((r) =>
              el(
                'li',
                {},
                el('span', { text: r.id }),
                el('span', { class: 'score', text: r.score.toFixed(1) }),
                el('span', { class: 'bar' }, el('i', { style: `width:${(r.score / top) * 100}%` })),
              ),
            ),
          ),
        ),
      );
    }
    panel.replaceChildren(...nodes);
  };

  const select = (id, focus) => {
    const c = byId.get(id);
    if (!c) return;
    for (const f of frames) f.setAttribute('aria-pressed', String(f.dataset.id === id));
    render(c);
    if (focus) document.getElementById('frame-' + id)?.focus();
    history.replaceState(null, '', '#' + id);
  };

  for (const f of frames) f.addEventListener('click', () => select(f.dataset.id, false));

  const visible = () => frames.filter((f) => f.dataset.dim !== 'true');
  document.getElementById('sheet').addEventListener('keydown', (event) => {
    const keys = { ArrowRight: 1, ArrowLeft: -1 };
    if (!(event.key in keys) || !(event.target instanceof HTMLElement) || !event.target.classList.contains('frame')) return;
    const list = visible();
    const next = list[list.indexOf(event.target) + keys[event.key]];
    if (next) {
      event.preventDefault();
      next.focus();
    }
  });

  const filters = document.getElementById('filters');
  const apply = () => {
    const form = new FormData(filters);
    const split = form.get('split');
    const result = form.get('result');
    const category = form.get('category');
    for (const f of frames) {
      const hide =
        (split !== 'all' && f.dataset.split !== split) ||
        (result === 'passed' && f.dataset.passed !== 'true') ||
        (result === 'failed' && f.dataset.passed !== 'false') ||
        (category !== 'all' && f.dataset.category !== category);
      f.dataset.dim = String(hide);
      f.tabIndex = hide ? -1 : 0;
    }
  };
  filters.addEventListener('change', apply);
  filters.addEventListener('submit', (event) => event.preventDefault());

  for (const link of document.querySelectorAll('a[data-case]')) {
    link.addEventListener('click', (event) => {
      event.preventDefault();
      select(link.dataset.case, true);
      document.getElementById('sheet').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  const fromHash = decodeURIComponent(location.hash.slice(1));
  const firstFailure = data.cases.find((c) => !c.passed && c.split === 'test') ?? data.cases.find((c) => !c.passed) ?? data.cases[0];
  select(byId.has(fromHash) ? fromHash : firstFailure.id, false);
  if (!byId.has(fromHash)) history.replaceState(null, '', location.pathname + location.search);
})();
