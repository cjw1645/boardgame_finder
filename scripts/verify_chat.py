"""Live local-model acceptance; requires Ollama and real local data."""
import json
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'service_app'))
from local_llm import available, plan, respond
from search import load_catalog, search


def main():
    assert available(), 'Local model is not ready'
    start = time.monotonic()
    history = [{'role': 'user', 'content': '네 명이서 한 시간 안에 할 마피아 게임 추천해줘'}]
    conditions = plan(history, {'players': 4, 'minutes': 60})
    print('PLAN', json.dumps(conditions, ensure_ascii=False), flush=True)
    assert conditions['players'] == 4 and conditions['minutes'] == 60
    rows, _ = load_catalog(ROOT / 'data')
    results = search(rows, conditions['query'], players=conditions['players'], minutes=conditions['minutes'], limit=5)
    assert results, 'No grounded matches'
    answer = respond(history, results, conditions)
    print('ANSWER', answer, flush=True)
    assert any(r['title_ko'] in answer for r in results), 'Answer did not reference retrieved games'
    history += [{'role': 'assistant', 'content': answer}, {'role': 'user', 'content': '그럼 30분 이내로 추천해줘'}]
    followup = plan(history, {'players': 4, 'minutes': 60})
    print('FOLLOWUP', json.dumps(followup, ensure_ascii=False), flush=True)
    assert followup['players'] == 4 and followup['minutes'] == 30
    assert '마피아' in followup['query']
    print(f'LIVE_CHAT_OK {time.monotonic() - start:.1f}s', flush=True)


if __name__ == '__main__':
    main()
