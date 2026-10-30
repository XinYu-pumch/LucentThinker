"""Separate immutable journal from active history and per-request retention view."""
import copy
from . import store

OMITTED = 'Tool result is omitted to save tokens.'

def request_view(messages, keep_tool_result, omitted=OMITTED):
    """The native protocol labels actual results with role=tool; control users are not results."""
    result = copy.deepcopy(messages)
    if keep_tool_result == -1:
        return result
    if keep_tool_result < 0:
        raise ValueError('keep_tool_result must be -1 or nonnegative')
    indices = [i for i, m in enumerate(result) if m['role'] == 'tool']
    omitted_indices = indices[:-keep_tool_result] if keep_tool_result else indices
    for i in omitted_indices:
        result[i]['content'] = omitted
    return result


class History:
    def __init__(self, rid, attempt):
        self.rid, self.attempt = rid, attempt
        self.messages, self.ids = [], []

    def append(self, message, purpose='research'):
        self.ids.append(store.record_message(self.rid, self.attempt, purpose, message))
        self.messages.append(copy.deepcopy(message))

    def checkpoint(self):
        return len(self.messages)

    def rollback(self, checkpoint, reason):
        ids = self.ids[checkpoint:]
        store.rollback_messages(ids, reason)
        del self.messages[checkpoint:]
        del self.ids[checkpoint:]

    def rollback_last_interaction(self, reason):
        for i in range(len(self.messages)-1, -1, -1):
            if self.messages[i]['role'] == 'assistant':
                self.rollback(i, reason)
                return True
        return False
