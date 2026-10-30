"""Registered IDs own their URLs. Validate mappings, never infer factual support."""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Remove only known tracking keys; preserve document IDs and other semantic parameters.
TRACKING = {'pvid', 'scm', 'spm', 'utm_source', 'utm_medium', 'utm_campaign',
            'utm_term', 'utm_content', 'utm_id'}
LINK = re.compile(r'\[(\d+)\]\(<?(https?://[^\s<>]*?(?:\([^\s<>]*?\)[^\s<>]*?)?)>?(?:\s+"[^"\n]*")?\)')
REFERENCE = re.compile(r'^\s*(?:[-*]\s*)?\[(\d+)\](?:[ \t]+|:[ \t]*)(.*)$')
CODE = re.compile(r'(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)')
IDS = r'[ \t]*[0-9０-９]+(?:[ \t]*[,，、;；][ \t]*[0-9０-９]+)*[ \t]*'
CITATION = re.compile(rf'(?:\[{IDS}\]|［{IDS}］|【{IDS}】)')
# Protect Markdown destinations and non-citation link labels from normalization.
INLINE_LINK = re.compile(r'(!?\[[^\]\n]*\]\((?:<[^>\n]*>|[^\s()]+(?:\([^\s()]*\)[^\s()]*)?)(?:[ \t]+"[^"\n]*")?\))')


def marker_ids(marker):
    return [int(value) for value in re.findall(r'[0-9０-９]+', marker)]


def normalize_citations(answer):
    """Normalize citation groups, leaving code, ordinary links and URLs intact."""
    def plain(text):
        return CITATION.sub(lambda m: ''.join(f'[{sid}]' for sid in marker_ids(m[0])), text)

    def prose(text):
        parts = INLINE_LINK.split(text)
        for i, part in enumerate(parts):
            if i % 2:
                label, destination = part.split('](', 1)
                label += ']'
                if CITATION.fullmatch(label):
                    parts[i] = ''.join(f'[{sid}]({destination}' for sid in marker_ids(label))
            else:
                # Raw URLs and autolinks are not citation markers.
                urls = re.split(r'(<https?://[^>\n]*>|https?://[^\s<>]+)', part)
                parts[i] = ''.join(s if j % 2 else plain(s) for j, s in enumerate(urls))
        return ''.join(parts)

    return ''.join(s if i % 2 else prose(s) for i, s in enumerate(CODE.split(answer)))


def cited_ids(answer):
    ids = set()
    for i, chunk in enumerate(CODE.split(normalize_citations(answer))):
        if i % 2: continue
        for j, part in enumerate(INLINE_LINK.split(chunk)):
            if j % 2:
                label = part.split('](', 1)[0] + ']'
                if CITATION.fullmatch(label): ids.update(marker_ids(label))
            else:
                text = re.sub(r'<https?://[^>\n]*>|https?://[^\s<>]+', '', part)
                for match in CITATION.finditer(text): ids.update(marker_ids(match[0]))
    return ids


def canonical(url):
    try:
        p = urlsplit(url.rstrip('.,;，。；'))
        query = urlencode(sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                                 if k.lower() not in TRACKING))
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/'), query, ''))
    except ValueError:
        return None


def reconcile(answer, sources):
    answer = normalize_citations(answer)
    known = {s['id']: s for s in sources}
    cited, unresolved, conflicts = set(), set(), set()

    def check(sid, urls):
        cited.add(sid)
        if sid not in known:
            unresolved.add(sid)
            return False
        if any(canonical(url) != canonical(known[sid]['url']) for url in urls):
            conflicts.add(sid)
        return True

    def marker(sid):
        return '[引用无法匹配 ' + str(sid) + ']'

    def process(text):
        # Preserve prose; only reference URLs are replaced by registered URLs.
        lines = []
        for line in text.splitlines(keepends=True):
            match = REFERENCE.match(line)
            urls = re.findall(r'https?://[^\s<>\])]+', match[2]) if match else []
            if match and urls and len(re.findall(r'\[(\d+)\]', line)) == 1:
                sid = int(match[1])
                if check(sid, urls):
                    line = re.sub(r'https?://[^\s<>\])]+', lambda _: known[sid]['url'], line)
                else:
                    line = re.sub(r'https?://[^\s<>\])]+', '(引用无法匹配)', line)
            lines.append(line)
        text = ''.join(lines)

        def link(match):
            sid = int(match[1])
            if not check(sid, [match[2]]):
                return marker(sid)
            # Angle brackets safely preserve query strings and parentheses in Markdown.
            return f'[{sid}](<{known[sid]["url"]}>)'
        text = LINK.sub(link, text)

        def number(match):
            sid = int(match[1])
            return match[0] if check(sid, []) else marker(sid)
        parts = INLINE_LINK.split(text)
        for i in range(0, len(parts), 2):
            urls = re.split(r'(<https?://[^>\n]*>|https?://[^\s<>]+)', parts[i])
            parts[i] = ''.join(s if j % 2 else re.sub(r'\[([0-9]+)\]', number, s)
                               for j, s in enumerate(urls))
        return ''.join(parts)

    chunks = CODE.split(answer)
    normalized = ''.join(chunk if i % 2 else process(chunk) for i, chunk in enumerate(chunks))
    if conflicts:
        normalized += '\n\n> 引用冲突：来源 ' + '、'.join(map(str, sorted(conflicts))) + ' 的模型生成 URL 与登记来源不同，链接已按登记编号显示；相关陈述仍需核对。'
    return normalized, {'unmatched_ids': sorted(unresolved), 'conflicting_ids': sorted(conflicts),
                        'missing_citations': bool(sources) and not cited}


def append_registered_references(answer, sources, heading='参考来源'):
    """Titles and URLs come from the registry, never a model-written bibliography."""
    cited = cited_ids(answer)
    rows = reference_rows(sources, cited)
    return answer + ('\n\n### ' + heading + '\n\n' + '\n'.join(rows) if rows else '')


def reference_rows(sources, cited):
    rows = []
    for source in sources:
        if source['id'] not in cited: continue
        title = source.get('title') or source['url']
        title = re.sub(r'([\\`*_{}\[\]<>])', r'\\\1', title).replace('\n', ' ')
        url = source['url'].replace('<', '%3C').replace('>', '%3E')
        rows.append(f'- [{source["id"]}](<{url}>) {title} — <{url}>')
    return rows


def refresh_registered_references(answer, sources, heading='参考来源'):
    """Repair the read/export view, without rewriting historical model output.

    Remove a trailing bibliography only when it exactly matches our generated
    rows. Never discard a model/user-written References section on a guess.
    """
    sections = list(re.finditer(r'\n\n### (References|参考来源)\n\n', answer))
    if sections:
        section = sections[-1]
        tail = answer[section.end():]
        ids = {int(n) for n in re.findall(r'^- \[([0-9]+)\]', tail, re.M)}
        if not ids or tail != '\n'.join(reference_rows(sources, ids)):
            return answer
        heading = section[1]
        answer = answer[:section.start()]
    answer, _ = reconcile(answer, sources)
    return append_registered_references(answer, sources, heading)
