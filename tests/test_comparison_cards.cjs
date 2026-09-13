const {test} = require('node:test');
const assert = require('node:assert/strict');
const {fieldState,doclingObservations,markdownSignals,analyzeEvidence,validateBundle,mergeCards} =
  require('../src/docling_poc/comparison_cards.js');
const document = {id:'d1',sha256:'abc',runs:{docling:[{number:1}],tika:[{number:2}]}};
function card() {
  return {id:'c1',document_id:'d1',document_sha256:'abc',title:'신청 자격',kind:'headings',
    reason:'제목 수준',source_location:'1페이지',note:'원본 확인 필요',original_checked:false,
    docling:{format:'json',content:'{"label":"section_header","level":2}',
      run:1,source_file:'raw.json.gz',source_refs:['#/texts/0']},
    tika:{format:'markdown',content:'## 신청 자격\n  ',run:2,source_file:'content.md',source_refs:[]}};
}
const bundle = cards => ({schema:'docling_poc.feature_cards',version:1,cards});

test('field states and zero are preserved independently',()=>{
  assert.deepEqual([null,false,true,[],{},'',0].map(fieldState),
    ['null','false','true','빈 배열','빈 객체','빈 문자열','값 있음']);
  const o=doclingObservations({label:'text',formatting:{bold:false},prov:[]});
  assert.match(o.formatting.details,/false/);
  assert.match(o.location.details,/빈 배열/);
  assert.equal(o.headings.mode,'발췌에 없음');
});
test('unlevelled title and bold never invent heading level or hierarchy',()=>{
  const o=doclingObservations({label:'title',formatting:{bold:true}});
  assert.equal(o.headings.mode,'발췌에 없음');
  assert.equal(o.hierarchy.mode,'발췌에 없음');
});
test('group evidence resolves only supplied unique references',()=>{
  const o=doclingObservations({items:[
    {self_ref:'#/groups/3',label:'list',children:[{$ref:'#/texts/1'},{$ref:'#/texts/2'}]},
    {self_ref:'#/texts/1',label:'list_item',parent:{$ref:'#/groups/3'}},
  ]});
  assert.match(o.hierarchy.details,/list/);
  assert.match(o.hierarchy.details,/유일한 대상으로 확인 2개/);
  assert.match(o.hierarchy.details,/나머지 1개는 발췌 밖/);
});
test('table evidence retains column spans and row/header properties',()=>{
  const o=doclingObservations({label:'table',data:{num_rows:1,num_cols:2,
    table_cells:[{text:'항목',col_span:2,row_span:1,column_header:true}]}});
  assert.match(o.tables.details,/col_span/);assert.match(o.tables.details,/column_header/);
});
test('empty groups remain explicit empty data and dotted Tika keys are literal',()=>{
  assert.match(doclingObservations({groups:[]}).hierarchy.details,/빈 배열/);
  const o=analyzeEvidence('tika',{format:'json',content:'{"dc:title.version":"1"}'});
  assert.match(o.metadata.details,/dc:title.version/);
  assert.equal(o.location.mode,'판단 불가');
});
test('limited markdown scan excludes fenced, indented and inline code',()=>{
  const signals=markdownSignals('````\n# 코드\n```\n## 여전히 코드\n````\n'+
    '    # 들여쓴 코드\n`**코드**`\n\n## 실제 표기\n\n**강조**\n- 항목\n');
  assert.equal(signals.headings.length,1);
  assert.equal(signals.headings[0].level,2);
  assert.equal(signals.formatting.length,1);
  assert.equal(signals.lists.length,1);
});
test('Tika resource hierarchy is not converted to a document group',()=>{
  const evidence={format:'json',content:JSON.stringify({'tk:content':'본문',
    'tk:embedded-depth':1,'tk:resource-name':'embedded.docx'})};
  const o=analyzeEvidence('tika',evidence);
  assert.equal(o.hierarchy.mode,'발췌에 없음');
  assert.match(o.resources.details,/embedded-depth/);
  assert.match(o.resources.next,/본문 목록·제목 계층이 아닙니다/);
});
test('Tika image filename headings are only markup candidates',()=>{
  const o=analyzeEvidence('tika',{format:'markdown',content:'# image1.png'});
  assert.equal(o.headings.mode,'출력 마크업 · 표기 후보');
  assert.match(o.classification.next,/이미지 파일명/);
});
test('plain text and HTML do not claim parsed structure',()=>{
  assert.equal(analyzeEvidence('docling',{format:'text',content:'## 제목'}).headings.mode,'판단 불가');
  assert.equal(analyzeEvidence('tika',{format:'markdown',content:'<html><h1>제목</h1></html>'}).headings.mode,'판단 불가');
});
test('bundle validates atomically and preserves exact whitespace and source',()=>{
  const c=card(), before=structuredClone(c);
  assert.deepEqual(validateBundle(bundle([c]),[document]),[before]);
  for(const change of [{document_sha256:'wrong'},{kind:'unknown'},{original_checked:'yes'},
    {docling:null,tika:null}]) {
    assert.throws(()=>validateBundle(bundle([{...card(),...change}]),[document]));
  }
  const bad=card();bad.tika.content='bad JSON';bad.tika.format='json';
  assert.throws(()=>validateBundle(bundle([c,bad]),[document]));
  assert.deepEqual(c,before);
});
test('duplicate IDs and unknown run are rejected without changing existing cards',()=>{
  const c=card(),existing=[c];
  assert.throws(()=>mergeCards(existing,[card()]));assert.equal(existing.length,1);
  c.docling.run=99;assert.throws(()=>validateBundle(bundle([c]),[document]));
});
