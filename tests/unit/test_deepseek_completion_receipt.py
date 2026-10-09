"""Production receipts retain actual SDK identity and usage, never credentials."""
import asyncio
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest


def test_one_call_receipt_retains_response_identity_and_tokens(monkeypatch):
    from lib import llm_deepseek as llm
    response = SimpleNamespace(id='chat-synthetic', model='deepseek-flash',
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=3, total_tokens=13,
                              prompt_cache_hit_tokens=6,prompt_cache_miss_tokens=4),
        choices=[SimpleNamespace(message=SimpleNamespace(content='result'), finish_reason='stop')])
    create = AsyncMock(return_value=response)
    single = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    client = Mock();client.with_options.return_value = single
    monkeypatch.setattr(llm, '_get_client', lambda: client)
    result = asyncio.run(llm.deepseek_complete_with_receipt('synthetic'))
    assert result['text'] == 'result'
    assert result['usage']['request_id'] == 'chat-synthetic'
    assert result['usage']['total_tokens'] == 13
    assert result['usage']['prompt_cache_hit_tokens'] == 6
    assert result['usage']['prompt_cache_miss_tokens'] == 4
    assert result['usage']['model'] == 'deepseek-flash'
    assert result['usage']['requested_model'] == 'deepseek-v4-flash'
    assert result['usage']['output_sha256'] == hashlib.sha256(b'result').hexdigest()
    client.with_options.assert_called_once_with(max_retries=0)
    create.assert_awaited_once()
    assert create.await_args.kwargs["reasoning_effort"] == "none"
    assert create.await_args.kwargs["response_format"] == {"type":"json_object"}
    assert create.await_args.kwargs["max_tokens"] == 12000


def test_receipt_validation_rejects_wrong_route_truncation_and_modified_output():
    from lib.llm_deepseek import validate_completion_receipt
    receipt = dict(receipt_type='deepseek-chat.v1', provider='deepseek', model='deepseek-v4-flash',
        requested_model='deepseek-v4-flash', request_id='synthetic', api_calls=1, failed=False,
        finish_reason='stop', prompt_tokens=10, completion_tokens=3, total_tokens=13,
        output_sha256=hashlib.sha256(b'result').hexdigest(), credential='must-not-copy')
    assert 'credential' not in validate_completion_receipt(receipt, 'result')
    for updates in ({'provider':'openai-codex'}, {'finish_reason':'length'}, {'total_tokens':'13'}, {'model':'other'}):
        with pytest.raises(ValueError):validate_completion_receipt(receipt | updates, 'result')
    with pytest.raises(ValueError):validate_completion_receipt(receipt, 'edited')


def test_legacy_wrapper_never_returns_a_truncated_body(monkeypatch):
    from lib import llm_deepseek as llm
    create=AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content='incomplete text'),finish_reason='length')]))
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm,'_get_client',lambda:client)
    with pytest.raises(RuntimeError,match='incomplete'):
        asyncio.run(llm.deepseek_model_complete('synthetic'))


def test_task_selects_the_matching_system_prompt(monkeypatch):
    from lib import llm_deepseek as llm
    response=SimpleNamespace(id='chat-1',model='deepseek-flash',
        usage=SimpleNamespace(prompt_tokens=1,completion_tokens=1,total_tokens=2),
        choices=[SimpleNamespace(message=SimpleNamespace(content='{}'),finish_reason='stop')])
    create=AsyncMock(return_value=response)
    client=Mock();client.with_options.return_value=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm,'_get_client',lambda: client)
    asyncio.run(llm.deepseek_complete_with_receipt('p',task='translate'))
    system=create.await_args.kwargs['messages'][0]['content']
    assert 'faithful' in system and 'translation' in system
    with pytest.raises(ValueError):asyncio.run(llm.deepseek_complete_with_receipt('p',task='unknown-task'))


def test_chunk_text_round_trips_on_line_boundaries():
    from lib.llm_deepseek import assemble_chunks, chunk_text
    text='\n'.join('line number %d'%i for i in range(50))
    chunks=chunk_text(text,max_chars=40)
    assert assemble_chunks(chunks)==text
    assert len(chunks)>1 and all(len(chunk)<=40 for chunk in chunks)
    assert chunk_text('short',max_chars=40)==['short']
    with pytest.raises(ValueError):chunk_text('x',max_chars=0)


def test_chunk_task_requests_text_while_structured_tasks_keep_json(monkeypatch):
    """The chunk task asks for plain text; every structural task still asks for JSON."""
    from lib import llm_deepseek as llm
    response=SimpleNamespace(id='chat-1',model='deepseek-flash',
        usage=SimpleNamespace(prompt_tokens=1,completion_tokens=1,total_tokens=2),
        choices=[SimpleNamespace(message=SimpleNamespace(content='译文正文'),finish_reason='stop')])
    create=AsyncMock(return_value=response)
    client=Mock();client.with_options.return_value=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm,'_get_client',lambda: client)
    asyncio.run(llm.deepseek_complete_with_receipt('p',task='translate_chunk'))
    chunk_kwargs=create.await_args.kwargs
    assert 'response_format' not in chunk_kwargs and 'no JSON wrapper' in chunk_kwargs['messages'][0]['content']
    asyncio.run(llm.deepseek_complete_with_receipt('p',task='translate'))
    assert create.await_args.kwargs['response_format']=={'type':'json_object'}
    asyncio.run(llm.deepseek_complete_with_receipt('p'))
    assert create.await_args.kwargs['response_format']=={'type':'json_object'}
