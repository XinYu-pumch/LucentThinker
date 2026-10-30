"""DeepSeek Search wire limits; these never limit the user's research question."""

SEARCH_TEXT_LIMIT = 128


def validate_search_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'DeepSeek Search {field} 必须是非空字符串。')
    if len(value) > SEARCH_TEXT_LIMIT:
        raise ValueError(
            f'DeepSeek Search {field} 最多 {SEARCH_TEXT_LIMIT} 个字符，'
            f'当前 {len(value)} 个；请生成更短的检索意图。未发送请求，原参数未截断。')
    return value


def resolve_search_context(query, original_question, search_intent=None):
    validate_search_text(query, 'query')
    if search_intent is not None:
        return validate_search_text(search_intent, 'search_intent / ori_question'), 'search_intent'
    if isinstance(original_question, str) and original_question.strip() and len(original_question) <= SEARCH_TEXT_LIMIT:
        return original_question, 'original_question'
    # A query is already a validated, focused search action, not a shortened copy
    # of the user's task. Keep the full original task in the main research history.
    return query, 'query'
