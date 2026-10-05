"""Acceptance regressions using the actual SDK policy runner, no GPU or live DB."""
import asyncio
import json
from pathlib import Path
import numpy as np
import pytest
from backend.ai import agent, chatbot, rag
from backend.ai.location_extractor import geocode_location, resolve_geography
from backend.ai.severity_model import predict_severity, classify_report
from backend.ai.translator import validate_english_translation


@pytest.fixture
def local_generation(monkeypatch):
    calls=[]
    async def generate(name,instructions,payload,**kwargs):
        agent._check_context(instructions,payload)
        calls.append((name,payload))
        if 'citizen_report' in payload:
            message=payload['citizen_report']['message']
            return json.dumps({'english_translation':message,'summary':'A citizen requests help.',
                'extracted_location':'Chengannur','people_affected':12,'required_assistance':['Food']}),[]
        return '{"summary":"A citizen requests help."}',[]
    monkeypatch.setattr(agent,'_run_agent',generate)
    return calls


def test_all_seven_tools_execute_in_sdk_order_with_real_returns_handoff_guardrails_and_local_trace(local_generation):
    result=asyncio.run(agent.analyze_report('Twelve people need food in Chengannur.','', '',None,
        alerts=[{'id':7,'district':'Alappuzha','location':'Chengannur','active':True}],
        teams=[{'id':9,'name':'Local relief','district':'Alappuzha','available':True,'active_assignment_count':0}],
        clarification_answers={'landmark':'Near the public bus station'}))
    assert result['analysis_status']=='completed'
    assert result['tools_used']==list(agent.TOOL_ORDER)
    assert [row['name'] for row in result['tool_trace']]==list(agent.TOOL_ORDER)
    assert all(row['status']=='completed' for row in result['tool_trace'])
    assert result['tool_trace'][3]['output']['status']=='MATCH'
    assert result['alert_match']['matched_alert_ids']==[7]
    assert result['people_affected']==12
    assert result['district']=='Alappuzha'
    assert result['extracted_location']=='Chengannur'
    assert result['available_teams'][0]['id']==9
    assert result['geography']['taluk']=='Chengannur'
    assert result['geography']['ward'] is None
    assert result['clarification']['status']=='resolved'
    assert result['handoffs'][0]['to']=='Admin review packet'
    assert result['orchestration_provider']=='local_deterministic_policy'
    trace=json.dumps(result['local_trace'])
    assert 'function' in trace and 'guardrail' in trace and 'handoff' in trace
    assert result['original_message'] not in trace


def test_explicit_facts_win_and_unknown_count_is_never_defaulted(local_generation):
    supplied=asyncio.run(agent.analyze_report('Twelve people need food in Chengannur.','Aluva','Ernakulam',2))
    assert supplied['people_affected']==2 and supplied['people_source']=='citizen_supplied'
    assert supplied['extracted_location']=='Aluva' and supplied['district']=='Ernakulam'
    unknown=asyncio.run(agent.analyze_report('My family needs food in Chengannur.'))
    assert unknown['people_affected'] is None  # fake model's twelve lacks a text anchor
    assert 'people_affected' in unknown['clarification']['missing_fields']


def test_generation_failure_still_executes_read_only_pipeline_and_preserves_original(monkeypatch):
    async def unavailable(*args,**kwargs): raise ConnectionError('PRIVATE_DIAGNOSTIC')
    monkeypatch.setattr(agent,'_run_agent',unavailable)
    result=asyncio.run(agent.analyze_report('Children are trapped.','Aluva','Ernakulam',None))
    assert result['tools_used']==list(agent.TOOL_ORDER)
    assert result['severity']=='HIGH'
    assert result['analysis_status']=='unavailable'
    assert result['english_translation'] is None
    assert 'PRIVATE_DIAGNOSTIC' not in json.dumps(result)


@pytest.mark.parametrize('message',[
    'We are not trapped. Everyone is safe and no rescue is needed.',
    'People were rescued yesterday. Nobody is trapped now.',
    'The resident is not unconscious and is breathing normally.',
    'കുടുങ്ങിയിട്ടില്ല. രക്ഷിക്കേണ്ടതില്ല.',
    'No children are trapped.',
])
def test_negated_or_resolved_danger_is_not_affirmative_escalation(message):
    result=predict_severity(message)
    assert result['danger_flag'] is False
    assert result['severity']!='HIGH'


@pytest.mark.parametrize('message',[
    'Nobody is trapped here, but two children are drowning now.',
    'We are not injured. An unconscious person cannot breathe.',
    'ഇവിടെ പ്രശ്നമില്ല. രണ്ട് കുട്ടികൾ വെള്ളത്തിൽ കുടുങ്ങിയിരിക്കുന്നു.',
    'There is no power and children are trapped.',
    'Not all children are trapped; some need rescue.',
])
def test_mixed_current_danger_is_preserved(message):
    assert predict_severity(message)['danger_flag'] is True


def test_rule_score_never_describes_another_class():
    result=predict_severity('Information about shelters. One person is trapped.')
    if result['baseline_severity']!=result['severity']:
        assert result['confidence'] is None
    assert result['baseline_confidence'] is not None
    assert result['confidence_kind']=='uncalibrated_synthetic_classifier_probability'


def test_malayalam_helper_uses_translation_first_classification(monkeypatch):
    async def translate(*args,**kwargs):
        return json.dumps({'english_translation':'Two children need food in Chengannur.','summary':'Children need food.'}),[]
    monkeypatch.setattr(agent,'_run_agent',translate)
    result=asyncio.run(classify_report('ചെങ്ങന്നൂരിൽ രണ്ട് കുട്ടികൾക്ക് ഭക്ഷണം വേണം.'))
    assert result['severity_input']=='english_translation'
    assert result['translation_status']=='completed'
    assert result['severity']==predict_severity('Two children need food in Chengannur.')['severity']


def test_incompatible_artifact_is_not_deserialized(monkeypatch,tmp_path):
    import backend.ai.severity_model as severity
    copied=tmp_path/'changed_training.csv'
    copied.write_text(severity.DATASET.read_text(encoding='utf-8')+'\n',encoding='utf-8')
    monkeypatch.setattr(severity,'DATASET',copied)
    monkeypatch.setattr(severity.joblib,'load',lambda *args:pytest.fail('Hash mismatch must be checked before pickle load'))
    severity.get_model.cache_clear()
    try:
        result=predict_severity('Two children are trapped.')
        assert result['model_serving_mode']=='in_memory_training'
        assert result['artifact_status']=='missing_or_incompatible'
    finally:
        severity.get_model.cache_clear()


@pytest.mark.parametrize('text,original',[
    ('Four children need help.','2 children need help.'),
    ('കുട്ടികൾ കുടുങ്ങിയിരിക്കുന്നു.',None),
    ('The residents need rescue.','രക്ഷിക്കേണ്ടതില്ല. അപകടമില്ല.'),
])
def test_translation_rejects_changed_numbers_script_or_dropped_negation(text,original):
    with pytest.raises(ValueError): validate_english_translation(text,original)


def test_geography_alias_conflict_unknown_and_town_coordinate_provenance():
    row=geocode_location('ചെങ്ങന്നൂർ','ആലപ്പുഴ')
    assert row['resolved_location']=='Chengannur'
    assert row['latitude']==pytest.approx(9.3178608)
    assert row['coordinate_source_url'].endswith('/1682779066')
    assert row['coordinates_status']=='approximate_place_centroid' and row['ward'] is None
    assert geocode_location('Aluva','Alappuzha')['status']=='CONFLICT'
    assert geocode_location('UNKNOWN_PLACE','Ernakulam')['status']=='UNRESOLVED'
    assert geocode_location('Aluva and Chengannur')['status']=='AMBIGUOUS'


def test_duplicate_alias_translation_and_busy_team_suggestions_are_conservative():
    matches=agent.find_duplicates('Two children are trapped.','Aluva','Ernakulam',[
        {'id':1,'location':'ആലുവ','district':'എറണാകുളം','message':'കുട്ടികൾ കുടുങ്ങി','english_translation':'Two children are trapped.'},
        {'id':2,'location':'Chengannur','district':'Alappuzha','message':'Two children are trapped.'}])
    assert [row['id'] for row in matches]==[1]
    available=agent.list_available_teams([
        {'id':1,'available':True,'district':'Ernakulam','active_assignment_count':1},
        {'id':2,'available':True,'district':'Alappuzha'},
        {'id':3,'available':True,'district':'Ernakulam'}],'Ernakulam')
    assert [row['id'] for row in available]==[3]


def test_external_geocoder_never_receives_unconsented_or_personal_location(monkeypatch):
    import backend.ai.location_extractor as location
    monkeypatch.setattr(location.httpx,'AsyncClient',lambda **kwargs:pytest.fail('No external request is permitted'))
    assert asyncio.run(resolve_geography('Unknown public park','Ernakulam',geocoding_consent=False))['status']=='UNRESOLVED'
    monkeypatch.setattr(agent.settings,'ai_enabled',True)
    assert asyncio.run(resolve_geography('House 27 John home','Ernakulam',geocoding_consent=True))['geocoder_status']=='private_location_not_submitted'


def test_geocoding_dotenv_aliases_disable_external_lookup(monkeypatch,tmp_path):
    import backend.config as config
    import backend.ai.location_extractor as location
    monkeypatch.delenv('RESQ_GEOCODING_ENABLED',raising=False)
    monkeypatch.delenv('RESQ_GEOCODING_URL',raising=False)
    env_file=tmp_path/'.env'
    env_file.write_text('RESQ_GEOCODING_ENABLED=false\nRESQ_GEOCODING_URL=http://localhost:8080/search\n',encoding='utf-8')
    loaded=config.Settings(_env_file=env_file)
    assert loaded.geocoding_enabled is False
    assert loaded.geocoding_url=='http://localhost:8080/search'
    loaded.ai_enabled=True
    monkeypatch.setattr(config,'settings',loaded)
    monkeypatch.setattr(location.httpx,'AsyncClient',lambda **kwargs:pytest.fail('Disabled .env setting must stop external lookup'))
    result=asyncio.run(resolve_geography('Unknown public park','Ernakulam',geocoding_consent=True))
    assert result['status']=='UNRESOLVED' and result['latitude'] is None


@pytest.mark.parametrize('private_location',[
    'മേരിയുടെ വീട്ടിൽ, പുതിയ ഫ്ലാറ്റ്',
    'ഫോൺ, മൊബൈൽ, രഹസ്യ വിലാസം',
])
def test_external_geocoder_rejects_malayalam_household_and_contact_terms(monkeypatch,private_location):
    import backend.ai.location_extractor as location
    monkeypatch.setattr(agent.settings,'ai_enabled',True)
    monkeypatch.setattr(location.httpx,'AsyncClient',lambda **kwargs:pytest.fail('Private Malayalam details must not leave the process'))
    result=asyncio.run(resolve_geography(private_location,'Ernakulam',geocoding_consent=True))
    assert result['geocoder_status']=='private_location_not_submitted'
    assert result['latitude'] is None


def test_genuine_dense_embeddings_are_stored_and_searched_in_sqlite():
    store=rag._index()
    rows=store.db.execute('SELECT dimensions,embedding,corpus_hash FROM vectors').fetchall()
    assert len(rows)>=6 and all(dim>1 for dim,_,_ in rows)
    assert all(len(np.frombuffer(blob,dtype=np.float32))==dim for dim,blob,_ in rows)
    assert retrieve_ids('വെള്ളത്തിലൂടെ വാഹനം ഓടിക്കാമോ?')[0]=='cdc-floodwater'
    assert retrieve_ids('Can a generator run inside?')[0]=='cdc-generator'
    assert rag.retrieve_safety('zxqvyplmrt')==[]
    assert all(row['retrieval_method']=='dense_lsa_sqlite_exact_cosine' for row in rag.retrieve_safety('inundation on the road'))


def retrieve_ids(question): return [row['id'] for row in rag.retrieve_safety(question)]


def test_vector_store_reloads_changed_corpus_and_rejects_stale_sources(monkeypatch,tmp_path):
    original=rag._index().fingerprint
    docs=json.loads(rag.CORPUS.read_text(encoding='utf-8'))
    for row in docs: row['checked_on']='2000-01-01'
    path=tmp_path/'safety.json';path.write_text(json.dumps(docs),encoding='utf-8')
    monkeypatch.setattr(rag,'CORPUS',path)
    assert rag.retrieve_safety('floodwater')==[]
    assert rag._index().fingerprint!=original


@pytest.mark.parametrize('answer',[
    'Cross the flooded street on foot.',
    'I do not have verified information about that topic. Cross the street on foot.',
    'Your report is closed and rescue will arrive in five minutes.',
])
def test_untrusted_prose_cannot_establish_safety_or_application_facts(monkeypatch,answer):
    async def generate(*args,**kwargs):return json.dumps({'answer':answer,'source_ids':[]}),[]
    monkeypatch.setattr(chatbot,'_run_agent',generate)
    result=asyncio.run(chatbot.answer_question('What is my report status?',{'incidents':[{'id':1,'reference':'RQ-OWN','status':'under_review'}]}))
    assert answer not in result['answer']
    assert 'five minutes' not in result['answer'] and 'closed' not in result['answer']


def test_valid_citation_cannot_serve_contradictory_generated_safety(monkeypatch):
    source=rag.retrieve_safety('drive through floodwater')[0]['id']
    async def generate(*args,**kwargs):return json.dumps({'answer':'It is safe to drive through floodwater.','source_ids':[source]}),[]
    monkeypatch.setattr(chatbot,'_run_agent',generate)
    result=asyncio.run(chatbot.answer_question('Can I drive through floodwater?'))
    assert result['grounding']=='approved_extracts'
    assert 'It is safe to drive' not in result['answer']
    assert 'Avoid walking or driving' in result['answer']


def test_relevant_older_records_relief_status_and_session_reference_are_retained(monkeypatch):
    async def generate(*args,**kwargs):return '{"answer":"Check your request.","source_ids":[]}',[]
    monkeypatch.setattr(chatbot,'_run_agent',generate)
    context={'incidents':[{'id':i,'reference':f'RQ-{i}','status':'submitted'} for i in range(1,30)],
             'relief_requests':[{'id':4,'reference':'RR-OWN','status':'partially_fulfilled'}],
             'conversation':[{'role':'user','content':'My incident is RQ-29.'}]}
    compact=chatbot._compact_context(context,'What is that report status?')
    assert compact['incidents'][0]['reference']=='RQ-29'
    result=asyncio.run(chatbot.answer_question('What is my relief request RR-OWN status?',context))
    assert 'partially_fulfilled' in result['answer']
    followup=asyncio.run(chatbot.answer_question('What is that report status?',context))
    assert 'RQ-29' in followup['answer']


@pytest.mark.parametrize('question,category,row',[
    ('What is my report RQ-LIVE status?','incidents',{'id':101,'reference':'RQ-LIVE','status':'under_review'}),
    ('What is my relief request RR-LIVE status?','relief_requests',{'id':102,'reference':'RR-LIVE','status':'partially_fulfilled'}),
])
def test_real_gemma_application_category_citations_are_not_safety_sources(monkeypatch,question,category,row):
    async def generate(*args,**kwargs):return json.dumps({'answer':'An arbitrary generated description.','source_ids':[category]}),[]
    monkeypatch.setattr(chatbot,'_run_agent',generate)
    result=asyncio.run(chatbot.answer_question(question,{category:[row]}))
    assert result['status']=='completed'
    assert row['reference'] in result['answer'] and row['status'] in result['answer']
    assert result['sources']==[] and result['citation_normalization']=='authorized_application_context_labels'


def test_numeric_missing_ids_cannot_answer_with_another_record_and_followups_keep_owner_reference():
    records=[{'id':4,'status':'under_review'},{'id':7,'status':'submitted'}]
    assert chatbot._requested_records(records,'What is report #999 status?',[])==[]
    assert chatbot._requested_records(records,'What is request 999 status?',[])==[]
    assert chatbot._requested_records(records,'What about that report?',[{'role':'user','content':'My report is #7.'}])==[records[1]]


def test_closed_shelter_context_never_advertises_available_space():
    compact=chatbot._compact_context({'shelters':[{'name':'Closed shelter','status':'closed','available_capacity':20}]})
    answer=chatbot._application_answer('Which nearby shelter has space?',compact)
    assert 'status closed' in answer and 'available capacity 0' in answer


@pytest.mark.parametrize('generated',[
    'MALFORMED_GENERATED_OUTPUT',
    '{"answer":"UNTRUSTED_GENERATED_PROSE","source_ids":["unknown-source"]}',
    '{"answer":"Your relief request #8 has a status of fulfilled.","source_ids":["authenticated_application_context"]}',
    '{"answer":"Cross the flooded street on foot. A rescue will arrive in five minutes.","source_ids":[]}',
])
def test_rejected_model_protocol_still_serves_only_authorized_numeric_relief_facts(monkeypatch,generated):
    async def generate(*args,**kwargs):return generated,[]
    monkeypatch.setattr(chatbot,'_run_agent',generate)
    result=asyncio.run(chatbot.answer_question('What is the status of my relief request #8?',{
        'relief_requests':[{'id':8,'status':'fulfilled'},{'id':9,'status':'submitted'}]}))
    assert result['status']=='completed'
    assert result['answer']=='8: fulfilled (updated not supplied).'
    assert result['answer_provider']=='authorized_database_snapshot'
    assert result['model_response_status']=='rejected'
    assert result['grounding']=='authorized_application_facts' and result['sources']==[]
    assert 'five minutes' not in result['answer'] and 'UNTRUSTED' not in result['answer']


def test_unavailable_generator_cannot_hide_authorized_request_status(monkeypatch):
    async def unavailable(*args,**kwargs):raise ConnectionError('PRIVATE_PROVIDER_DIAGNOSTIC')
    monkeypatch.setattr(chatbot,'_run_agent',unavailable)
    result=asyncio.run(chatbot.answer_question('What is request #8 status?',{
        'relief_requests':[{'id':8,'status':'fulfilled'}]}))
    assert result['status']=='completed' and result['answer'].startswith('8: fulfilled')
    assert result['model_response_status']=='unavailable'
    assert result['answer_provider']=='authorized_database_snapshot'
    assert 'PRIVATE_PROVIDER_DIAGNOSTIC' not in json.dumps(result)


def test_rejected_model_cannot_substitute_own_status_for_missing_private_request(monkeypatch):
    async def generate(*args,**kwargs):return '{"answer":"The private request is fulfilled.","source_ids":["unknown-source"]}',[]
    monkeypatch.setattr(chatbot,'_run_agent',generate)
    result=asyncio.run(chatbot.answer_question('What is the status of my relief request #999?',{
        'relief_requests':[{'id':8,'status':'fulfilled'}]}))
    assert result['status']=='completed' and 'No matching relief request' in result['answer']
    assert 'fulfilled' not in result['answer'] and '8:' not in result['answer']
    assert result['sources']==[] and result['model_response_status']=='rejected'


@pytest.mark.parametrize('question',[
    'Can I drive through floodwater to submit my report?',
    'Is it safe to drink floodwater while my relief request is pending?',
])
def test_application_mentions_cannot_bypass_safety_guard_on_model_rejection(monkeypatch,question):
    async def generate(*args,**kwargs):return '{"answer":"UNTRUSTED_SAFETY_PROSE","source_ids":["unknown-source"]}',[]
    monkeypatch.setattr(chatbot,'_run_agent',generate)
    result=asyncio.run(chatbot.answer_question(question,{
        'incidents':[{'id':8,'status':'fulfilled'}],
        'relief_requests':[{'id':8,'status':'fulfilled'}]}))
    assert result['status']=='unavailable' and result['model_response_status']=='rejected'
    assert result.get('answer_provider')!='authorized_database_snapshot'
    assert 'UNTRUSTED_SAFETY_PROSE' not in result['answer'] and '8: fulfilled' not in result['answer']
    assert result['grounding']=='approved_extracts_fallback'


def test_exact_two_turn_request_discussion_uses_authorized_current_facts(monkeypatch):
    async def generate(*args,**kwargs):return '{"answer":"UNTRUSTED_MODEL_TEXT","source_ids":["authenticated_application_context"]}',[]
    monkeypatch.setattr(chatbot,'_run_agent',generate)
    context={'relief_requests':[{'id':10,'status':'fulfilled'},{'id':11,'status':'submitted'}]}
    first_question='What is the status of my relief request #10?'
    first=asyncio.run(chatbot.answer_question(first_question,context))
    context['conversation']=[{'role':'user','content':first_question},{'role':'assistant','content':first['answer']}]
    followup=asyncio.run(chatbot.answer_question('Which request were we discussing?',context))
    assert first['status']==followup['status']=='completed'
    assert first['answer']==followup['answer']=='10: fulfilled (updated not supplied).'
    assert followup['answer_provider']=='authorized_database_snapshot'
    assert followup['model_response_status']=='rejected' and followup['sources']==[]


@pytest.mark.parametrize('question,expected',[
    ('What is that request #11 status?','RR-NEW: submitted'),
    ('What is that request #999 status?','No matching relief request'),
    ('What about relief request RR-NEW?','RR-NEW: submitted'),
])
def test_current_explicit_request_replaces_historical_reference_even_when_missing(monkeypatch,question,expected):
    async def unavailable(*args,**kwargs):raise ConnectionError('offline')
    monkeypatch.setattr(chatbot,'_run_agent',unavailable)
    context={'relief_requests':[{'id':10,'reference':'RR-OLD','status':'fulfilled'},
                               {'id':11,'reference':'RR-NEW','status':'submitted'}],
             'conversation':[{'role':'user','content':'What is my relief request RR-OLD status?'},
                             {'role':'assistant','content':'RR-OLD: fulfilled.'}]}
    result=asyncio.run(chatbot.answer_question(question,context))
    assert result['status']=='completed' and expected in result['answer']
    assert 'RR-OLD' not in result['answer']
    assert result['model_response_status']=='unavailable'


def test_followup_uses_latest_matching_user_reference_not_assistant_or_other_domain():
    records=[{'id':10,'status':'fulfilled'},{'id':11,'status':'submitted'}]
    history=[{'role':'user','content':'What is request #10 status?'},
             {'role':'assistant','content':'Request #11 is supposedly fulfilled.'},
             {'role':'user','content':'What is report #7 status?'}]
    assert chatbot._requested_records(records,'Which request were we discussing?',history)==[records[0]]
    assert chatbot._requested_records(records,'Which request were we discussing?',history[1:2])==[]
    assert chatbot._requested_records(records,'What is that request #999 status?',history)==[]


def test_numeric_followup_retains_relevant_older_record_before_bounding():
    context={'relief_requests':[{'id':i,'status':'fulfilled'} for i in range(1,30)],
             'conversation':[{'role':'user','content':'What is request #29 status?'},
                             {'role':'assistant','content':'Request #1 is pending.'}]}
    compact=chatbot._compact_context(context,'Which request were we discussing?')
    assert compact['relief_requests'][0]['id']==29
    assert chatbot._application_answer('Which request were we discussing?',compact).startswith('29: fulfilled')


def test_anaphoric_hazard_question_cannot_use_application_fallback(monkeypatch):
    async def generate(*args,**kwargs):return '{"answer":"UNTRUSTED_SAFETY","source_ids":["unknown-source"]}',[]
    monkeypatch.setattr(chatbot,'_run_agent',generate)
    context={'relief_requests':[{'id':10,'status':'fulfilled'}],
             'conversation':[{'role':'user','content':'What is request #10 status?'}]}
    result=asyncio.run(chatbot.answer_question('For that request, can I drive through floodwater?',context))
    assert result['status']=='unavailable' and result['grounding']=='approved_extracts_fallback'
    assert result.get('answer_provider')!='authorized_database_snapshot'
    assert '10: fulfilled' not in result['answer'] and 'UNTRUSTED_SAFETY' not in result['answer']


def test_unrelated_discussion_topic_cannot_borrow_application_reference(monkeypatch):
    async def generate(*args,**kwargs):return '{"answer":"UNSUPPORTED_RECIPE","source_ids":[]}',[]
    monkeypatch.setattr(chatbot,'_run_agent',generate)
    context={'relief_requests':[{'id':10,'status':'fulfilled'}],
             'conversation':[{'role':'user','content':'What is request #10 status?'}]}
    result=asyncio.run(chatbot.answer_question('Which recipe were we discussing?',context))
    assert result['status']=='unavailable' and result.get('answer_provider')!='authorized_database_snapshot'
    assert '10: fulfilled' not in result['answer'] and 'UNSUPPORTED_RECIPE' not in result['answer']
