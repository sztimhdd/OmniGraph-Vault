"""One K/D backfill ledger, written only under the existing refresh lock."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import uuid


class BudgetError(ValueError):
    pass


# Official CNY peak prices verified 2026-10-04. See CONTENT-BUDGET-PRICING.md.
# 1M context is conservatively bounded by 2**20; includes all message overhead.
PRICE = {'verified_on':'2026-10-04','input_hit_fen_per_million':4,
         'input_miss_fen_per_million':200,'output_fen_per_million':800,
         'input_token_upper_bound':1048576,'max_output_tokens':12000}
RESERVE_FEN = 220
FLASH = {'deepseek-v4-flash', 'deepseek-flash'}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',',':')).encode()


class BackfillBudget:
    def __init__(self, root, lock):
        self.root = Path(root).resolve()
        self.lock = lock
        self.path = self.root/'backfill-budget.json'
        self._check_lock()
        if self.path.is_symlink():
            raise BudgetError('backfill ledger must not be a symlink')
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
            if (self.data.get('schema_version') != 1 or self.data.get('limit_fen') != 10000
                    or self.data.get('price') != PRICE or not isinstance(self.data.get('entries'),dict)
                    or not isinstance(self.data.get('requests'),dict)):
                raise BudgetError('invalid or differently priced backfill ledger')
            self.summary()
        else:
            self.data = {'schema_version':1,'budget_id':'vitax-shared-K-D-backfill',
                         'limit_fen':10000,'price':PRICE,'entries':{},'requests':{}}
            self._save()

    def _check_lock(self):
        if self.lock.closed or Path(self.lock.name).resolve() != self.root/'refresh.lock':
            raise BudgetError('backfill requires the owner refresh lock')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _save(self):
        self._check_lock()
        temporary = self.path.with_name(self.path.name+'.'+uuid.uuid4().hex)
        with temporary.open('x') as stream:
            os.fchmod(stream.fileno(),0o600)
            stream.write(json.dumps(self.data,sort_keys=True,indent=2)+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,self.path)
        directory = os.open(self.root,os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def summary(self):
        spent, reserved = 0, 0
        for receipt in self.data['requests'].values():
            cost = receipt.get('cost_upper_bound_fen')
            if type(cost) is not int or cost < 0:
                raise BudgetError('invalid settled cost')
            spent += cost
        for entry in self.data['entries'].values():
            if entry.get('state') == 'unknown':
                if entry.get('reserved_fen') != RESERVE_FEN:
                    raise BudgetError('invalid reservation')
                reserved += entry['reserved_fen']
            elif entry.get('state') != 'settled' or entry.get('request_id') not in self.data['requests']:
                raise BudgetError('invalid backfill entry state')
        if spent+reserved > 10000:
            raise BudgetError('backfill ledger exceeds its shared limit')
        return {'limit_fen':10000,'settled_upper_bound_fen':spent,'reserved_fen':reserved,
                'available_fen':10000-spent-reserved}

    def call_key(self, identity, prompt):
        if (not isinstance(identity,dict) or identity.get('lane') not in ('K','D')
                or not isinstance(identity.get('source_revisions'),list) or not identity['source_revisions']
                or not all(isinstance(r,str) and r for r in identity['source_revisions'])
                or not isinstance(identity.get('stage'),str) or not identity['stage']
                or not isinstance(identity.get('recipe'),str) or not identity['recipe']):
            raise BudgetError('backfill requires source revisions, stage, recipe and K/D lane')
        fields = [sorted(identity['source_revisions']),identity['stage'],identity['recipe'],
                  hashlib.sha256(prompt.encode()).hexdigest()]
        # Lane is deliberately excluded: K and D must not buy the same call twice.
        return hashlib.sha256(_canonical(fields)).hexdigest()

    def pending(self, key):
        return key in self.data['entries']

    def reserve(self, key, identity, prompt, directory):
        self._check_lock()
        if key != self.call_key(identity,prompt) or self.pending(key):
            raise BudgetError('existing outcome requires cache recovery, never another request')
        for entry in self.data['entries'].values():
            previous = entry['identity']
            same_work = (sorted(previous['source_revisions'])==sorted(identity['source_revisions'])
                         and previous['stage']==identity['stage'] and previous['recipe']==identity['recipe'])
            if entry['state']=='unknown' and same_work:
                raise BudgetError('unknown source stage must be resolved before changing its prompt')
        directory = Path(directory).resolve()
        if not directory.is_relative_to(self.root/'native'):
            raise BudgetError('backfill cache must stay in the owner native root')
        if self.summary()['available_fen'] < RESERVE_FEN:
            raise BudgetError('insufficient shared backfill balance')
        saved_identity = {f:identity[f] for f in ('lane','source_revisions','stage','recipe')}
        self.data['entries'][key] = {'identity':saved_identity,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                                     'cache_path':str(directory),'state':'unknown',
                                     'reserved_fen':RESERVE_FEN,'attempts':1}
        # Persist before transport. A crash before/after dispatch remains unknown.
        self._save()

    def settle(self, key, result):
        self._check_lock()
        entry = self.data['entries'].get(key)
        usage = result.get('usage')
        if (entry is None or not isinstance(usage,dict) or usage.get('provider') != 'deepseek'
                or usage.get('receipt_type') != 'deepseek-chat.v1'
                or usage.get('requested_model') not in FLASH or usage.get('model') not in FLASH
                or type(usage.get('api_calls')) is not int or usage['api_calls'] != 1
                or not isinstance(usage.get('request_id'),str) or not usage['request_id']
                or not isinstance(result.get('text'),str)
                or usage.get('output_sha256') != hashlib.sha256(result['text'].encode()).hexdigest()):
            raise BudgetError('unknown billing outcome; reservation retained')
        fields = ('prompt_tokens','completion_tokens','total_tokens')
        if any(type(usage.get(f)) is not int or usage[f]<0 for f in fields):
            raise BudgetError('invalid actual token usage; reservation retained')
        prompt, output = usage['prompt_tokens'],usage['completion_tokens']
        if (usage['total_tokens'] != prompt+output or prompt > PRICE['input_token_upper_bound']
                or output > PRICE['max_output_tokens']):
            raise BudgetError('usage exceeds the reserved model bounds')
        hit, miss = usage.get('prompt_cache_hit_tokens'),usage.get('prompt_cache_miss_tokens')
        if hit is None and miss is None:
            hit, miss = 0, prompt
        elif (type(hit) is not int or type(miss) is not int or min(hit,miss)<0 or hit+miss != prompt):
            raise BudgetError('invalid cache usage; reservation retained')
        numerator = hit*4 + miss*200 + output*800
        cost = (numerator+999999)//1000000
        billing = {f:usage[f] for f in ('request_id','requested_model','model',*fields,'output_sha256')}
        billing.update(prompt_cache_hit_tokens=hit,prompt_cache_miss_tokens=miss)
        billing['cache_usage_observed'] = 'prompt_cache_hit_tokens' in usage
        request = usage['request_id']
        existing = self.data['requests'].get(request)
        if existing is not None and existing['billing'] != billing:
            raise BudgetError('request_id has conflicting usage; reservation retained')
        if entry['state']=='settled' and entry['request_id'] != request:
            raise BudgetError('a settled call cannot change request identity')
        if existing is None:
            self.data['requests'][request] = {'billing':billing,'cost_upper_bound_fen':cost,
                'basis':'peak_prices_actual_usage_rounded_up_to_fen', 'generation_ok':result.get('ok') is True}
        entry.update(state='settled',request_id=request,reserved_fen=0)
        self.summary()
        self._save()
