"""No model simulation: combine two externally obtained validated judgments."""
import math

def decision(deterministic, invariant_ok, judges, infrastructure_ok=True, policy_ok=True):
    if not infrastructure_ok: return {'status':'RETRY_ERROR','score':None}
    if not policy_ok: return {'status':'POLICY_FAILURE','score':None}
    if not isinstance(deterministic,(int,float)) or isinstance(deterministic,bool) or not math.isfinite(deterministic) or not 0 <= deterministic <= 1:
        raise ValueError('invalid deterministic score')
    if not invariant_ok: return {'status':'FAIL_INVARIANT','score':None}
    valid = isinstance(judges,list) and len(judges)==2
    criteria = {'correctness','clarity'}
    if valid:
        for judge in judges:
            if not isinstance(judge,dict) or set(judge) != {'criteria','conflicts_with_tests','confidence'}:
                valid=False; break
            if type(judge['conflicts_with_tests']) is not bool or type(judge['confidence']) not in (int,float) or not math.isfinite(judge['confidence']) or not 0 <= judge['confidence'] <= 1:
                valid=False; break
            if not isinstance(judge['criteria'],dict) or set(judge['criteria']) != criteria:
                valid=False; break
            for item in judge['criteria'].values():
                if not isinstance(item,dict) or set(item) != {'level','evidence','reason'} or type(item['level']) is not int or not 0 <= item['level'] <= 4 or not all(isinstance(item[k],str) and 0 < len(item[k]) <= 2000 for k in ('evidence','reason')):
                    valid=False; break
    if not valid: return {'status':'REVIEW','score':None,'reason':'invalid or absent judge output'}
    semantic = sum(j['criteria'][c]['level'] for j in judges for c in criteria)/16
    score = 100*(.6*deterministic+.4*semantic)
    disagree = any(abs(judges[0]['criteria'][c]['level']-judges[1]['criteria'][c]['level']) > 1 for c in criteria)
    review = disagree or abs(score-60) <= 5 or any(j['conflicts_with_tests'] for j in judges)
    return {'status':'REVIEW' if review else ('PASS' if score >=60 else 'FAIL'), 'score':round(score,2),'D':deterministic,'S':semantic}
