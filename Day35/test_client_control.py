"""Проверки управления агентом без API, Qdrant и загрузки моделей поиска."""

import ast
from enum import Enum
import json
import re
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import openai
from pydantic import BaseModel, Field


def isolated_agent():
    # Проверяем настоящие определения исходника. Импорт всего модуля создаёт
    # клиентов и загружает модели дня 28, которые этим тестам не нужны.
    path = Path(__file__).with_name("project_week_5.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {"ConfidenceLevel", "Citation", "AnswerPart", "RAGAnswer", "SearchDocuments",
             "AnswerPartDraft", "RAGDraft", "EvidenceBinding", "RequestPlan", "_plan_request",
             "_assemble_answer",
             "_validate_or_repair", "_review_refusal", "_refine_once",
             "_error", "_record_response", "_execute_calls", "_ensure_search",
             "_finish_answer", "call_client"}
    definitions = [node for node in tree.body
                   if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    scope = {"BaseModel": BaseModel, "Field": Field, "Enum": Enum,
             "json": json, "re": re, "time": time, "openai": openai}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), "exec"), scope)
    scope.update(history=[{"role": "developer", "content": "rules"}],
                 last_error=None, answer_validation_errors=[],
                 MODEL="test", MAX_STEPS=2, TOOLS=[],
                 SEARCH_TOOLS={"search_documents", "search_in_document"},
                 TOOL_MODELS={"search_documents": scope["SearchDocuments"]},
                 execute=Mock(return_value=json.dumps({"hits": [{"text": "evidence"}]})))
    return scope


class ClientControlTests(unittest.TestCase):
    def setUp(self):
        self.agent = isolated_agent()
        self.agent['_plan_request'] = Mock()
        self.agent['_review_refusal'] = Mock(side_effect=lambda r: r)
        self.agent['_refine_once'] = Mock(return_value=(None, None))

    def draft(self, facts=None, supported=False, **kwargs):
        return self.agent['RAGDraft'](parts=[self.agent['AnswerPartDraft'](
            question_part='question', supported=supported, answer='Answer or evidence limitation',
            facts=facts or [])], requires_document_search=True, confidence='high',
            follow_up_questions=[], **kwargs)

    def fact(self, source='s:1', entity='evidence', direct=True, text='Established fact'):
        return self.agent['EvidenceBinding'](fact=text, supports_request=direct,
                                            source_id=source, entity=entity)

    def response(self, draft=None, query=None, call_id='s'):
        output=[] if query is None else [SimpleNamespace(type='function_call',
            name='search_documents', call_id=call_id, arguments=json.dumps({'query':query}))]
        return SimpleNamespace(output=output, output_parsed=draft)

    def run_client(self, responses):
        parse=Mock(side_effect=responses)
        self.agent['raw_client']=SimpleNamespace(responses=SimpleNamespace(parse=parse))
        return self.agent['call_client']('question'), parse

    def add_hits(self, hits):
        self.agent['history'].extend([dict(role='user',content='question'),
            dict(type='function_call',call_id='s',name='search_documents'),
            dict(type='function_call_output',call_id='s',output=json.dumps({'hits':hits}))])

    def test_mandatory_search(self):
        (answer,calls),parse=self.run_client([self.response(query='keywords'),self.response(self.draft())])
        self.assertIsNotNone(answer)
        self.assertEqual(calls,['search_documents'])
        self.assertEqual(parse.call_args_list[0].kwargs['tool_choice']['name'],'search_documents')

    def test_budget_finalizes_without_tools(self):
        (answer,calls),parse=self.run_client([self.response(query='first',call_id='1'),
            self.response(query='second',call_id='2'),self.response(self.draft())])
        self.assertIsNotNone(answer)
        self.assertEqual(len(calls),2)
        self.assertEqual(parse.call_args.kwargs['tool_choice'],'none')

    def test_duplicate_does_not_execute_again(self):
        self.run_client([self.response(query='same',call_id='1'),
            self.response(query='same',call_id='2'),self.response(self.draft())])
        self.assertEqual(self.agent['execute'].call_count,1)

    def test_invalid_source_one_repair(self):
        (answer,_),parse=self.run_client([self.response(query='query'),
            self.response(self.draft([self.fact('invented')],True)),self.response(self.draft())])
        self.assertIsNotNone(answer)
        self.assertEqual(parse.call_count,3)
        self.assertEqual(len(self.agent['answer_validation_errors']),1)

    def test_failed_repair_preserves_error(self):
        bad=self.draft([self.fact('invented')],True)
        (answer,_),parse=self.run_client([self.response(query='query'),self.response(bad),self.response(bad)])
        self.assertIsNone(answer)
        self.assertIn('unknown source_id',self.agent['last_error']['message'])
        self.assertEqual(parse.call_count,3)

    def test_api_failure_returns_none(self):
        (answer,_),_=self.run_client([openai.APIConnectionError(request=Mock())])
        self.assertIsNone(answer)
        self.assertEqual(self.agent['last_error']['stage'],'api')

    def test_source_quote_copied_without_whitespace_changes(self):
        text='Pompey  the  Younger was an opponent.\n45\u00a0BC'
        self.add_hits([dict(source_id='s:1',doc_id='Augustus',text=text)])
        draft=self.draft([self.fact(entity='Pompey the Younger')],True)
        result=self.agent['_assemble_answer'](draft)
        self.assertEqual(result.citations[0].quote,text)
        self.assertEqual(result.parts[0].confirmed_facts,['Established fact'])

    def test_related_background_does_not_validate_premise(self):
        self.add_hits([dict(source_id='s:1',doc_id='Hannibal',text='Hannibal admired Alexander.')])
        draft=self.draft([self.fact(entity='Hannibal',direct=False)],False)
        result=self.agent['_assemble_answer'](draft)
        self.assertFalse(result.parts[0].supported)
        self.assertEqual(len(result.citations),1)
        self.assertEqual(result.confidence.value,'low')

    def test_source_for_namesake_rejected(self):
        self.add_hits([dict(source_id='s:1',doc_id='Caesar',text='Pompey fled to Egypt.')])
        with self.assertRaisesRegex(ValueError,'exact entity'):
            self.agent['_assemble_answer'](self.draft([self.fact(entity='Pompey the Younger')],True))

    def add_plan(self, target):
        plan=self.agent['RequestPlan'](question_parts=['question'],target_entities=[target],
            ambiguous=False,interpretation='',clarification_question='',search_query=target)
        self.agent['history'].append(dict(role='developer',content='REQUEST_PLAN:\n'+plan.model_dump_json()))

    def test_atia_description_is_not_part_of_name(self):
        self.add_hits([dict(source_id='s:1',doc_id='Augustus',text='His mother Atia protested because of his poor health.')])
        self.add_plan('Atia')
        draft=self.draft([self.fact(entity='Atia, mother of Octavius (Augustus)')],True)
        result=self.agent['_assemble_answer'](draft)
        self.assertEqual(result.parts[0].evidence_bindings[0]['entity'],'Atia')
        self.assertEqual(draft.parts[0].facts[0].entity,'Atia, mother of Octavius (Augustus)')

    def test_appositive_cannot_strip_requested_qualifier(self):
        self.add_hits([dict(source_id='s:1',doc_id='Caesar',text='Pompey fled to Egypt.')])
        self.add_plan('Pompey the Younger')
        with self.assertRaisesRegex(ValueError,'exact entity'):
            self.agent['_assemble_answer'](self.draft([self.fact(entity='Pompey, Roman commander')],True))

    def test_partial_name_cannot_match_another_word(self):
        self.add_hits([dict(source_id='s:1',doc_id='doc',text='Spatial information only.')])
        with self.assertRaisesRegex(ValueError,'exact entity'):
            self.agent['_assemble_answer'](self.draft([self.fact(entity='Atia')],True))

    def test_v10_atia_draft_with_original_retrieved_context(self):
        path=Path(__file__).parents[1]/'Day38/out_data/problem_cases_v10/runs.jsonl'
        if not path.exists(): self.skipTest('v10 fixture unavailable')
        row=json.loads(path.read_text(encoding='utf-8').splitlines()[0])
        draft=self.agent['RAGDraft'].model_validate(row['answer_validation_errors'][0]['draft'])
        normalize=lambda text:' '.join(text.casefold().split())
        text=next(c for c in row['retrieved_contexts']
                  if 'atia' in normalize(c) and 'poor health' in normalize(c))
        ids={f.source_id for p in draft.parts for f in p.facts}
        self.add_hits([dict(source_id=sid,doc_id='Augustus',text=text) for sid in ids])
        self.add_plan('Atia')
        result=self.agent['_assemble_answer'](draft)
        self.assertEqual(len(result.parts),2)
        self.assertTrue(all(p.supported for p in result.parts))
        self.assertTrue(all(b['entity']=='Atia' for p in result.parts for b in p.evidence_bindings))
        self.assertTrue(all(c.quote==text for c in result.citations))

    def test_previous_request_source_rejected(self):
        self.add_hits([dict(source_id='s:1',doc_id='doc',text='evidence')])
        self.agent['history'].append(dict(role='user',content='new request'))
        with self.assertRaisesRegex(ValueError,'unknown source_id'):
            self.agent['_assemble_answer'](self.draft([self.fact()],True))

    def test_refinement_query_required_and_budget_checked(self):
        refine=isolated_agent()['_refine_once']
        # Helper uses its own globals; no API is touched on these branches.
        self.assertEqual(refine(self.response(self.draft()),['search_documents'],None),(None,None))
        self.assertEqual(refine(self.response(self.draft(refinement_query='new')),
                                ['search_documents']*2,None),(None,None))

    def test_refinement_then_closed_finalization(self):
        real=isolated_agent()
        self.agent['_refine_once']=real['_refine_once']
        # Rebind the actual definition to this isolated scope.
        tree=ast.parse(Path(__file__).with_name('project_week_5.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_refine_once')
        exec(compile(ast.Module(body=[node],type_ignores=[]),'agent','exec'),self.agent)
        (answer,calls),parse=self.run_client([self.response(query='first',call_id='1'),
            self.response(self.draft(refinement_query='focused')),
            self.response(query='focused',call_id='2'),self.response(self.draft())])
        self.assertIsNotNone(answer)
        self.assertEqual(len(calls),2)
        self.assertEqual(parse.call_args.kwargs['tool_choice'],'none')

    def test_plan_preserves_ambiguity_and_language_instruction(self):
        agent=isolated_agent()
        agent['history'].append(dict(role='user',content='Tell me about a name'))
        plan=agent['RequestPlan'](answer_language='English',question_parts=['overview'],
            target_entities=['name'],ambiguous=True,interpretation='Provisional meaning',
            clarification_question='Which meaning?',search_query='name')
        parse=Mock(return_value=self.response(plan))
        agent['raw_client']=SimpleNamespace(responses=SimpleNamespace(parse=parse))
        agent['_plan_request']()
        result=agent['_assemble_answer'](self.draft())
        self.assertIn('Which meaning?',result.answer)
        self.assertIn('English',agent['history'][-1]['content'])
        self.assertEqual(parse.call_args.kwargs['tool_choice'],'none')

    def test_v9_drafts_can_be_migrated_without_duplicate_lists_or_copied_spans(self):
        path=Path(__file__).parents[1]/'Day38/out_data/problem_cases_v9/runs.jsonl'
        if not path.exists(): self.skipTest('v9 fixture unavailable')
        rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        for index in [0,1,3]:
            with self.subTest(case=index):
                agent=isolated_agent()
                row=rows[index]
                old=row['answer_validation_errors'][0]['draft']
                agent['history'].append(dict(role='user',content=row['question']))
                hits=[];parts=[]
                for part in old['parts']:
                    facts=[]
                    # Migration checks the new representation, not semantic correctness.
                    # Optional duplicated background is omitted; source text is never copied by a model.
                    for binding in part['evidence_bindings']:
                        normal=lambda t:' '.join(t.casefold().split())
                        text=next(c for c in row['retrieved_contexts'] if normal(binding['entity']) in normal(c))
                        sid=f's:{len(hits)+1}'
                        hits.append(dict(source_id=sid,doc_id='fixture',text=text))
                        facts.append(agent['EvidenceBinding'](fact=binding['fact'],
                            supports_request=part['supported'],entity=binding['entity'],source_id=sid))
                    parts.append(agent['AnswerPartDraft'](question_part=part['question_part'],
                        supported=part['supported'],answer=part['answer'],facts=facts,
                        evidence_gap=part['evidence_gap']))
                agent['history'].extend([dict(type='function_call',call_id='s',name='search_documents'),
                    dict(type='function_call_output',call_id='s',output=json.dumps({'hits':hits}))])
                draft=agent['RAGDraft'](parts=parts,requires_document_search=True,
                    confidence=old['confidence'],follow_up_questions=[])
                answer=agent['_assemble_answer'](draft)
                self.assertEqual(len(answer.parts),len(parts))
                for citation in answer.citations:
                    self.assertIn(citation.quote,row['retrieved_contexts'])


if __name__ == '__main__':
    unittest.main()
