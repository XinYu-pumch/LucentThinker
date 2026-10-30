import json
from .search_policy import SEARCH_TEXT_LIMIT, validate_search_text

class SearchQueryTooLong(ValueError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON argument: ' + key)
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('Non-finite JSON number: ' + value)

TOOLS = [
    {'type': 'function', 'function': {
        'name': 'search',
        'description': 'Search live web pages with DeepSeek Search. query and optional search_intent must each be 1–128 characters; never silently truncate. Return ranked titles, URLs, dates and snippets ONLY, as discovery leads, not original-page verification. Vendor content/summary remain server-side. Generate search_intent when a focused natural-language question helps; it is sent as ori_question. If omitted, the program supplies the original task only when it fits 128 characters; otherwise it uses the validated query as the search intent, while retaining the entire original task in main history. Supports site:, exact quoted phrases and date/language operators.',
        'parameters': {'type': 'object', 'properties': {
            'query': {'type': 'string', 'minLength': 1, 'maxLength': SEARCH_TEXT_LIMIT},
            'search_intent': {'type':'string','minLength':1,'maxLength':SEARCH_TEXT_LIMIT,'description':'Focused question for this search, sent verbatim as DeepSeek ori_question. Must be 1–128 characters; not a copy of the full research task.'},
            'count': {'type': 'integer', 'minimum': 1, 'default': 10}},
            'required': ['query'], 'additionalProperties': False}}},
    {'type': 'function', 'function': {
        'name': 'scrape_and_extract_info',
        'description': 'Read one HTTP(S) page with DeepSeek Fetch, then ALWAYS use a separate model to extract the requested information. The research model receives extracted findings, never the full fetched body. If Fetch fails or returns no usable text, the program uses saved Search content bound directly to the selected source_id in this attempt, or Search summary if content is unavailable. Both pass through independent extraction and are explicitly marked degraded/search_content or degraded/search_summary, not successful Fetch verification. Select a source_id returned by search; URLs are resolved by the program, never copied or rewritten by you. Unknown or previous-attempt IDs are rejected. Provide an explicit information requirement; the extraction model receives no research history or other pages. Returns success, url, extracted_info, error, scrape_stats, model_used and tokens_used.',
        'parameters': {'type': 'object', 'properties': {
            'source_id': {'type': 'integer', 'minimum': 1, 'description': 'Choose a source_id from current-attempt search results. The program retrieves its saved URL and materials.'},
            'info_to_extract': {'type': 'string', 'minLength': 1}},
            'required': ['source_id', 'info_to_extract'], 'additionalProperties': False}}},
    {'type': 'function', 'function': {
        'name': 'finish_research',
        'description': 'Explicitly end research and request separate final writing without tools. Call alone, never together with search or reading. Use ready when evidence is sufficient, or blocked when further research cannot resolve the gaps. Supply a brief public status and remaining questions, not a draft answer or private reasoning. The program validates structure, not factual completeness.',
        'parameters': {'type': 'object', 'properties': {
            'status': {'type': 'string', 'enum': ['ready', 'blocked']},
            'summary': {'type': 'string', 'minLength': 1},
            'unresolved_questions': {'type': 'array', 'items': {'type': 'string', 'minLength': 1}}},
            'required': ['status', 'summary', 'unresolved_questions'], 'additionalProperties': False}}},
]


for tool in TOOLS[:2]:
    params = tool['function']['parameters']
    params['properties']['progress'] = {'type': 'string', 'minLength': 1, 'description': 'Brief public action description in the user language (what you are about to check). No private reasoning or mandatory evidence summary.'}
    params['required'].append('progress')

def parse_call(call):
    if not isinstance(call, dict) or call.get('type') != 'function' or not isinstance(call.get('function'), dict):
        raise ValueError('Expected a native function call')
    name = call.get('function', {}).get('name')
    raw = call.get('function', {}).get('arguments', '')
    try:
        args = json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, TypeError):
        raise ValueError('Tool arguments must be valid JSON; no automatic repair is performed') from None
    if not isinstance(args, dict):
        raise ValueError('Tool arguments must be a JSON object')
    if name in ('search', 'scrape_and_extract_info') and (not isinstance(args.get('progress'), str) or not args['progress'].strip()):
        raise ValueError('progress is required: provide a brief public action description in the user language, not private reasoning')
    if name == 'search':
        if set(args) - {'query', 'count', 'search_intent', 'progress'} or not isinstance(args.get('query'), str) or not args['query'].strip():
            raise ValueError('search requires a nonempty query and optional count')
        if len(args['query']) > 128: raise SearchQueryTooLong('DeepSeek Search query 最多 128 个字符；请重新生成精简关键词。原参数未截断。')
        if 'search_intent' in args and (not isinstance(args['search_intent'], str) or not args['search_intent'].strip()): raise ValueError('search_intent must be a nonempty string')
        if 'search_intent' in args: validate_search_text(args['search_intent'], 'search_intent / ori_question')
        if type(args.get('count', 10)) is not int or args.get('count', 10) < 1:
            raise ValueError('Search count must be a positive integer')
    elif name == 'scrape_and_extract_info':
        if set(args) != {'source_id', 'info_to_extract', 'progress'} or type(args.get('source_id')) is not int or args['source_id'] < 1 or not isinstance(args.get('info_to_extract'), str) or not args['info_to_extract'].strip():
            raise ValueError('scrape_and_extract_info requires a positive source_id and nonempty info_to_extract and progress; do not supply a URL')
    elif name == 'finish_research':
        if (set(args) != {'status', 'summary', 'unresolved_questions'}
                or args['status'] not in ('ready', 'blocked')
                or not isinstance(args['summary'], str) or not args['summary'].strip()
                or not isinstance(args['unresolved_questions'], list)
                or any(not isinstance(q, str) or not q.strip() for q in args['unresolved_questions'])):
            raise ValueError('finish_research requires status ready/blocked, nonempty summary and an array of nonempty unresolved_questions')
    else:
        raise ValueError('Unknown tool: ' + str(name))
    return name, args


def query_key(name, args):
    # Search query (not count); reading uses program-owned source identity + explicit task.
    if name == 'search': return (name, args['query'])
    if name == 'scrape_and_extract_info': return (name, args['source_id'], args['info_to_extract'])
    return None
